"""
CodeChangeAgent — LangGraph agent that reads feedback from the user,
plans and implements structural code changes, runs tests, and emails a diff
for approval before anything is committed.

Uses claude-opus-4-6 for complex reasoning over the codebase.

Entry point: run_code_change_agent(raw_reply, digest_id, run_id)
Called from trigger_code_change_node in supervisor/immediate.py via a daemon thread.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, TypedDict

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

log = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent

# Only these directory prefixes may be written by the agent
ALLOWED_WRITE_PREFIXES = ("pipeline/", "supervisor/", "tools/")

# These specific files are never writable even if they match a prefix
DISALLOWED_WRITE_PATHS = frozenset({"schema.sql", "main.py", "config.py"})

_MAX_REVISE_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class CodeChangeState(TypedDict):
    raw_reply: str
    digest_id: str
    run_id: str
    planned_changes: List[str]
    files_modified: List[str]
    test_result: Optional[str]    # pytest stdout
    tests_passed: bool
    diff: str
    attempts: int
    # Internal — list of LangChain messages for the tool-calling loop
    messages: list


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def read_file(path: str) -> str:
    """Read any .py file in the project."""
    if not path.endswith(".py"):
        raise ValueError(f"Only .py files may be read. Got: {path!r}")
    full_path = PROJECT_ROOT / path
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {path!r}")
    if not full_path.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError(f"Path escapes project root: {path!r}")
    return full_path.read_text(encoding="utf-8")


@tool
def write_file(path: str, content: str) -> str:
    """Write a .py file. Only pipeline/, supervisor/, tools/ directories are allowed."""
    # Must not be a disallowed path (by basename or full relative path)
    basename = Path(path).name
    if path in DISALLOWED_WRITE_PATHS or basename in DISALLOWED_WRITE_PATHS:
        raise ValueError(f"Writing to {path!r} is not permitted.")

    # Must not be under migrations/
    if path.startswith("migrations/"):
        raise ValueError(f"Writing to migrations/ is not permitted. Got: {path!r}")

    # Must start with an allowed prefix
    if not any(path.startswith(prefix) for prefix in ALLOWED_WRITE_PREFIXES):
        raise ValueError(
            f"Write path {path!r} is not allowed. "
            f"Must start with one of: {ALLOWED_WRITE_PREFIXES}"
        )

    full_path = PROJECT_ROOT / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    log.info("code_change_agent_wrote_file", path=path)
    return f"Written: {path}"


@tool
def run_bash(command: str) -> str:
    """Run a shell command. Only 'pytest tests/' is permitted."""
    if command.strip() != "pytest tests/":
        raise ValueError(
            f"Only 'pytest tests/' is permitted. Got: {command!r}"
        )
    result = subprocess.run(
        ["pytest", "tests/"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=300,
    )
    output = result.stdout + result.stderr
    return output


@tool
def send_diff_email(body: str) -> str:
    """Send a diff to the user for approval via email."""
    from config import settings
    from gmail_service import GmailService

    notify = settings.code_change_notify_email
    if not notify:
        raise ValueError(
            "CODE_CHANGE_NOTIFY_EMAIL is not set — cannot send diff email. "
            "Set CODE_CHANGE_NOTIFY_EMAIL or ALERT_EMAIL in your environment."
        )
    gmail = GmailService()
    gmail.send_message(
        to=notify,
        subject="product input required for news briefing",
        body=body,
    )
    log.info("code_change_diff_email_sent", to=notify)
    return f"Diff email sent to {notify}"


_TOOLS = [read_file, write_file, run_bash, send_diff_email]
_TOOL_NODE = ToolNode(_TOOLS)

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

_llm = ChatAnthropic(model="claude-opus-4-6").bind_tools(_TOOLS)

_SYSTEM_PROMPT = """You are the CodeChangeAgent for the news-briefing-agent project.

Your job:
1. Read the user's feedback to understand what structural change is needed.
2. Plan a concrete, minimal set of file changes (list each file and what to do).
3. Implement the changes using read_file and write_file.
4. Run tests with run_bash("pytest tests/") and iterate if they fail (max 3 attempts).
5. Once tests pass, generate a clear diff summary and send it with send_diff_email.

Rules:
- Only edit .py files in pipeline/, supervisor/, or tools/.
- Never touch main.py, config.py, schema.sql, or migrations/.
- Keep changes minimal — address the user's request only.
- If tests still fail after 3 attempts, stop without sending a success email.
"""


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def understand_and_plan(state: CodeChangeState) -> dict:
    """Initial node: analyse the raw_reply and produce a plan."""
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"The user sent this feedback:\n\n{state['raw_reply']}\n\n"
            "First, read relevant source files to understand the codebase, then "
            "produce a concrete list of changes you will make."
        )),
    ]
    response = _llm.invoke(messages)
    messages.append(response)

    # Extract a simple text plan from the response content
    plan_text = response.content if isinstance(response.content, str) else str(response.content)
    planned = [line.strip() for line in plan_text.splitlines() if line.strip()]

    return {
        "planned_changes": planned,
        "messages": messages,
    }


def implement_loop(state: CodeChangeState) -> dict:
    """Tool-calling loop: implement changes using read_file/write_file."""
    messages = state["messages"]
    files_modified: list[str] = list(state.get("files_modified", []))

    # Add a prompt to implement based on previous plan (or test failure context)
    if state.get("attempts", 0) == 0:
        messages = messages + [
            HumanMessage(content="Now implement the planned changes using the available tools.")
        ]
    else:
        messages = messages + [
            HumanMessage(content=(
                f"Tests failed (attempt {state['attempts']}/{_MAX_REVISE_ATTEMPTS}):\n\n"
                f"{state.get('test_result', '')}\n\n"
                "Fix the issues and re-implement."
            ))
        ]

    # Agentic loop — continue until no more tool calls
    while True:
        response = _llm.invoke(messages)
        messages = messages + [response]

        if not response.tool_calls:
            break

        tool_results = _TOOL_NODE.invoke({"messages": messages})
        messages = tool_results["messages"]

        # Track files written
        for tc in response.tool_calls:
            if tc["name"] == "write_file":
                path = tc["args"].get("path", "")
                if path and path not in files_modified:
                    files_modified.append(path)

    return {
        "messages": messages,
        "files_modified": files_modified,
    }


def run_tests_gate(state: CodeChangeState) -> dict:
    """Run pytest and record whether tests passed."""
    result = subprocess.run(
        ["pytest", "tests/"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=300,
    )
    output = result.stdout + result.stderr
    passed = result.returncode == 0
    log.info(
        "code_change_agent_tests_run",
        run_id=state["run_id"],
        passed=passed,
        attempt=state.get("attempts", 0) + 1,
    )
    return {
        "test_result": output,
        "tests_passed": passed,
        "attempts": state.get("attempts", 0) + 1,
    }


def _route_after_tests(state: CodeChangeState) -> str:
    if state["tests_passed"]:
        return "send_diff"
    if state["attempts"] >= _MAX_REVISE_ATTEMPTS:
        return "send_failure"
    return "implement_loop"


def send_diff(state: CodeChangeState) -> dict:
    """Build a diff summary and email it for approval."""
    files_str = "\n".join(f"  - {f}" for f in state.get("files_modified", []))
    body = (
        f"Code change proposal for your news briefing agent.\n\n"
        f"Triggered by feedback (digest {state['digest_id']}, run {state['run_id']}):\n"
        f"{state['raw_reply']}\n\n"
        f"Files modified:\n{files_str}\n\n"
        f"Test output:\n{state.get('test_result', 'N/A')}\n\n"
        f"Reply 'approved' to apply this change."
    )
    from config import settings
    from gmail_service import GmailService

    notify = settings.code_change_notify_email
    if notify:
        try:
            gmail = GmailService()
            gmail.send_message(
                to=notify,
                subject="product input required for news briefing",
                body=body,
            )
            log.info("code_change_diff_email_sent", run_id=state["run_id"], to=notify)
        except Exception as exc:
            log.error("code_change_diff_email_failed", run_id=state["run_id"], error=str(exc))
    else:
        log.warning("code_change_notify_email_not_set", run_id=state["run_id"])

    return {"diff": body}


def send_failure(state: CodeChangeState) -> dict:
    """Send a failure notification (tests never passed after max attempts)."""
    from config import settings
    from gmail_service import GmailService

    notify = settings.code_change_notify_email
    body = (
        f"CodeChangeAgent could not produce passing changes after {_MAX_REVISE_ATTEMPTS} attempts.\n\n"
        f"Triggered by feedback (digest {state['digest_id']}, run {state['run_id']}):\n"
        f"{state['raw_reply']}\n\n"
        f"Last test output:\n{state.get('test_result', 'N/A')}"
    )
    if notify:
        try:
            gmail = GmailService()
            gmail.send_message(
                to=notify,
                subject="code change agent failed — news briefing",
                body=body,
            )
        except Exception as exc:
            log.error("code_change_failure_email_failed", run_id=state["run_id"], error=str(exc))
    log.warning("code_change_agent_gave_up", run_id=state["run_id"], attempts=state["attempts"])
    return {}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    builder = StateGraph(CodeChangeState)

    builder.add_node("understand_and_plan", understand_and_plan)
    builder.add_node("implement_loop", implement_loop)
    builder.add_node("run_tests_gate", run_tests_gate)
    builder.add_node("send_diff", send_diff)
    builder.add_node("send_failure", send_failure)

    builder.add_edge(START, "understand_and_plan")
    builder.add_edge("understand_and_plan", "implement_loop")
    builder.add_edge("implement_loop", "run_tests_gate")
    builder.add_conditional_edges(
        "run_tests_gate",
        _route_after_tests,
        {
            "send_diff": "send_diff",
            "send_failure": "send_failure",
            "implement_loop": "implement_loop",
        },
    )
    builder.add_edge("send_diff", END)
    builder.add_edge("send_failure", END)

    return builder.compile()


_graph = _build_graph()


# ---------------------------------------------------------------------------
# Failure email helper (called from run_code_change_agent on exception)
# ---------------------------------------------------------------------------

def _send_failure_email(raw_reply: str, error: Exception, run_id: str) -> None:
    """Send a plain failure alert. Best-effort — never raises."""
    try:
        from config import settings
        from gmail_service import GmailService

        notify = settings.code_change_notify_email
        if not notify:
            return
        body = (
            f"CodeChangeAgent crashed unexpectedly.\n\n"
            f"Run ID: {run_id}\n"
            f"Error: {type(error).__name__}: {error}\n\n"
            f"Triggered by feedback:\n{raw_reply}"
        )
        gmail = GmailService()
        gmail.send_message(
            to=notify,
            subject="code change agent failed — news briefing",
            body=body,
        )
    except Exception as inner:
        log.error("code_change_failure_notification_failed", run_id=run_id, error=str(inner))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_code_change_agent(raw_reply: str, digest_id: str, run_id: str) -> None:
    """
    Non-blocking entry point. Called from trigger_code_change_node in a daemon thread.

    Invokes the LangGraph agent with initial state. On exception, logs the error
    and sends a failure notification email.
    """
    log.info("code_change_agent_started", digest_id=digest_id, run_id=run_id)
    try:
        _graph.invoke({
            "raw_reply": raw_reply,
            "digest_id": digest_id,
            "run_id": run_id,
            "planned_changes": [],
            "files_modified": [],
            "test_result": None,
            "tests_passed": False,
            "diff": "",
            "attempts": 0,
            "messages": [],
        })
    except Exception as exc:
        log.error("code_change_agent_failed", run_id=run_id, error=str(exc))
        _send_failure_email(raw_reply, exc, run_id)
