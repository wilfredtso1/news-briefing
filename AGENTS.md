# Concurrent Agent Build Plan

> Read CLAUDE.md fully before starting work. This file defines your scope, file ownership, and integration seams.
> Read the plan at /Users/wilfredtso/.claude/plans/piped-bouncing-bentley.md for full implementation detail.

---

## Status at Plan Creation

- **Phases 1–6**: Complete and E2E tested
- **Immediate Fixes + CodeChangeAgent**: Not started (this plan)

---

## Agent A — Source Coverage + Onboarding

**Branch**: `feat/source-coverage-onboarding`

### Build
- `tools/db.py`: Add `update_source_type(sender_email, source_type)` after `update_source_trust_weight()` (~line 131)
- `source_classifier.py`: Add `crew@morningbrew.com` and `markets@axios.com` to `KNOWN_NEWS_BRIEF_SENDERS`; import `get_source_by_email`; add DB lookup block after line 110 (after KNOWN_LONG_FORM_SENDERS check, before List-Unsubscribe check) — if DB has a type for this sender, use it and return; wrap in try/except, fall through to heuristic on failure
- `pipeline/onboarding.py`: Import `update_source_type`; add `"source_type_corrections"` field to `_PARSE_REPLY_PROMPT` JSON schema; add 4th bullet to `_format_setup_email()` instructions ("Move any source between lists if I got it wrong"); apply corrections in `process_onboarding_reply()` after deprioritize loop

### Files you own
```
tools/db.py          ← add update_source_type() only
source_classifier.py
pipeline/onboarding.py
tests/test_source_classifier.py
tests/test_onboarding.py
```

### Files to stay out of
```
supervisor/
pipeline/synthesizer.py
pipeline/daily_brief.py
pipeline/topic_gap_fill.py
schema.sql
config.py
main.py
```

### Tests required
- `crew@morningbrew.com` → `news_brief` even with long body
- `markets@axios.com` → `news_brief`
- DB lookup returning `news_brief` overrides long-body heuristic result
- DB lookup returning `long_form` overrides short-body result
- DB returns `None` → heuristic runs normally
- DB throws exception → falls through to heuristic, no crash
- DB lookup NOT called for known senders (assert mock not called)
- `process_onboarding_reply` calls `update_source_type` for each valid correction
- Invalid type string in correction → silently skipped
- `_format_setup_email` body includes instruction to move sources between lists

### Definition of done
- All tests pass
- `source_classifier.py` DB lookup wrapped in try/except
- `upsert_newsletter_source` ON CONFLICT clause leaves `type` unchanged (already correct — verify in tests)

---

## Agent B — Synthesis Style Notes + Topic Gap Fill

**Branch**: `feat/synthesis-gap-fill`

### Build
- `pipeline/synthesizer.py`: Import `get_config`; extract `_SYNTHESIS_SYSTEM_BASE` and `_REFORMAT_SYSTEM_BASE` as module-level string constants; add `_build_system(base, style_notes)` helper; in `synthesize_clusters()` read `synthesis_style_notes` from agent_config ONCE at top; pass to `_synthesize_cluster` → `_synthesize_single` / `_synthesize_multi`; each synthesize function builds dynamic prompt if notes non-empty, uses static chain if empty
- `pipeline/topic_gap_fill.py` (new): `gap_fill_topics(stories, run_id)` — reads `web_search_topics` from agent_config, finds uncovered topics, runs TavilySearchResults(max_results=3) per topic, appends SynthesizedStory objects; uses `_normalise_topic` from synthesizer; wraps each search in try/except (skip topic on failure); returns original + additions
- `pipeline/daily_brief.py`: Import `gap_fill_topics`; add call between enricher (line 137) and ranker (line 139): `synthesized = gap_fill_topics(synthesized, run_id=run_id)`
- `schema.sql`: Append two rows to agent_config seed: `('synthesis_style_notes', '[]', 'system')` and `('web_search_topics', '[]', 'system')`
- `migrations/004_agent_config_style_topics.sql` (new): INSERT both keys with ON CONFLICT DO NOTHING; include rollback comment

### Files you own
```
pipeline/synthesizer.py
pipeline/topic_gap_fill.py    ← new file
pipeline/daily_brief.py
schema.sql
migrations/004_agent_config_style_topics.sql   ← new file
tests/test_synthesizer.py
tests/test_topic_gap_fill.py   ← new file
```

### Files to stay out of
```
supervisor/
source_classifier.py
tools/db.py
pipeline/onboarding.py
config.py
main.py
```

### Tests required
- Style notes injected into system prompt for both single-source and multi-source synthesis paths
- Empty style notes → static module-level chain used unchanged
- `get_config("synthesis_style_notes")` called once per `synthesize_clusters()` call, not once per story
- `web_search_topics` topic already covered → Tavily not called for it
- Uncovered topic → Tavily called, result appended as SynthesizedStory with `source_newsletters=["Web Search: {topic}"]`
- Tavily raises → graceful skip, other topics still processed
- Empty Tavily results → no story added
- Gap-fill stories appended AFTER newsletter stories (order preserved)
- `gap_fill_topics` returns input unchanged when `web_search_topics` is empty/None

### Definition of done
- All tests pass
- `topic_gap_fill.py` under 80 lines
- Migration file includes rollback comment

---

## Agent C — Supervisor Expansion

**Branch**: `feat/supervisor-expansion`

### Build
- `supervisor/immediate.py`:
  - Expand `LOW_RISK_CONFIG_KEYS` to include `"synthesis_style_notes"` and `"web_search_topics"`
  - Update `_EXTRACT_PROMPT` with 3 new keys: `synthesis_style_notes`, `web_search_topics`, `source_reclassify`
  - Update `_CLASSIFY_PROMPT` with new type: `"code_change_approval"`
  - Update `validate_change_node`: add `elif proposed_key == "source_reclassify": risk_level = "source"` and `elif proposed_key == "unknown" and len(state.get("raw_reply","")) > 50: risk_level = "code_change"`
  - Import `update_source_type` from `tools.db`
  - Add `reclassify_source_node`: validates type is news_brief/long_form, calls `update_source_type`, self-logs via `insert_feedback_event` + `mark_feedback_applied`, returns to END
  - Add `trigger_code_change_node`: spawns daemon thread calling `run_code_change_agent` (lazy import from `supervisor.code_change_agent`), returns immediately
  - Add `approve_code_change_node`: runs `subprocess.run(["git", "push"], ...)` with `cwd=os.getenv("RAILWAY_GIT_REPO_DIR", "/app")`
  - Update `route_after_validate`: add `"source" → "reclassify_source"`, `"code_change" → "trigger_code_change"`
  - Update `route_after_acknowledge`: add `"code_change_approval" → "approve_code_change"`
  - Add nodes + edges to graph builder
- `supervisor/weekly.py`:
  - Expand `LOW_RISK_CONFIG_KEYS` identically
  - Update `_ANALYZE_PROMPT` to mention the two new keys in the low_risk_changes section

### Files you own
```
supervisor/immediate.py
supervisor/weekly.py
tests/test_supervisor_immediate.py
tests/test_supervisor_weekly.py
```

### Files to stay out of
```
supervisor/code_change_agent.py   ← Agent D owns this
source_classifier.py
tools/db.py
pipeline/
config.py
main.py
```

### Note on code_change_agent import
`trigger_code_change_node` must lazy-import `run_code_change_agent` inside the function body (not at module top) so the module loads even before `supervisor/code_change_agent.py` exists. Tests should mock `supervisor.immediate.run_code_change_agent` or patch the lazy import.

### Tests required
- `synthesis_style_notes` in `LOW_RISK_CONFIG_KEYS` (both immediate + weekly)
- `web_search_topics` in `LOW_RISK_CONFIG_KEYS` (both immediate + weekly)
- `synthesis_style_notes` feedback → `set_config` called, in `config_delta`
- `web_search_topics` feedback → `set_config` called
- `source_reclassify` with valid value → `update_source_type` called, action_taken set
- `source_reclassify` with invalid type → no DB call, no raise
- Unknown key + short reply (≤50 chars) → no code change triggered, no thread spawned
- Unknown key + long reply (>50 chars) → code change thread spawned
- `code_change_approval` reply → `git push` subprocess called
- Weekly: `synthesis_style_notes` change applied via `apply_changes_node`

### Definition of done
- All 388 existing tests continue to pass + new tests pass
- `trigger_code_change_node` lazy-imports code_change_agent (not at module top)

---

## Agent D — CodeChangeAgent

**Branch**: `feat/code-change-agent`

### Build
- `config.py`: Add `code_change_notify_email: str | None = None` to Config dataclass (after all required fields); in `_load()` add `code_change_notify_email=os.getenv("CODE_CHANGE_NOTIFY_EMAIL") or os.getenv("ALERT_EMAIL")`; do NOT add to required list; do NOT change alerts.py (it reads ALERT_EMAIL directly from os.environ)
- `supervisor/code_change_agent.py` (new): LangGraph agent using `claude-opus-4-6` with 4 tools:
  - `read_file(path)`: validate .py extension + under PROJECT_ROOT
  - `write_file(path, content)`: validate prefix in `("pipeline/", "supervisor/", "tools/")` AND path not in `frozenset({"schema.sql", "main.py", "config.py"})` AND not under `migrations/`; write to temp path; track modified files for diff generation
  - `run_bash(command)`: only `"pytest tests/"` permitted; raises ValueError otherwise
  - `send_diff_email(body)`: reads `settings.code_change_notify_email`; raises if None; sends via GmailService with subject `"product input required for news briefing"`
  - LangGraph flow: `START → understand_and_plan → implement_loop → run_tests_gate → send_diff → END`; max 3 revise loops; if tests still fail after 3 → send failure email
  - Public entry: `run_code_change_agent(raw_reply, digest_id, run_id) -> None` — wraps graph invoke; logs errors; sends failure email on exception

### Files you own
```
supervisor/code_change_agent.py   ← new file
config.py
tests/test_code_change_agent.py   ← new file
```

### Files to stay out of
```
supervisor/immediate.py   ← Agent C owns this
supervisor/weekly.py
pipeline/
tools/db.py
source_classifier.py
main.py
```

### Tests required
- `write_file` raises for `schema.sql`
- `write_file` raises for `main.py`
- `write_file` raises for `migrations/004.sql`
- `write_file` succeeds for `pipeline/topic_gap_fill.py` (mock `open`)
- `run_bash` raises for any command other than `pytest tests/`
- `run_bash` calls subprocess correctly for `pytest tests/`
- `run_code_change_agent` does NOT send email when tests fail
- `run_code_change_agent` sends email with exact subject `"product input required for news briefing"` when tests pass
- `send_diff_email` raises when `code_change_notify_email` is None

### Definition of done
- All tests pass
- `write_file` tool uses strict path validation before any file I/O
- Agent invoked in a daemon thread — verified by `trigger_code_change_node` test in Agent C's test suite

---

## Coordination Rules

1. **No agent touches `main.py`**
2. **No agent touches `schema.sql` except Agent B** (append-only, two rows)
3. **No agent touches `tools/db.py` except Agent A** (add `update_source_type` only)
4. **No agent touches `config.py` except Agent D** (add one optional field only)
5. Agents A, B, C can run fully in parallel — zero file conflicts
6. Agent D can run in parallel; C and D share the contract `run_code_change_agent(raw_reply, digest_id, run_id)` — D implements it, C's `trigger_code_change_node` lazy-imports it
7. Conflicts go to the human. Do not attempt merges autonomously.

---

## Integration Sprint (after all 4 branches)

Merge order: A → B → C → D

1. Run `migrations/004_agent_config_style_topics.sql` against Supabase
2. Full test suite: `pytest tests/ -v` — expect 430+ passing
3. E2E: daily brief dry-run — confirm Morning Brew + Axios Markets in `brief_messages`
4. E2E: reply "add sports headlines" → `web_search_topics: ["sports"]` applied
5. E2E: reply "write shorter stories" → `synthesis_style_notes: [...]` applied
6. E2E: reply "include Morning Brew in the daily brief" → `update_source_type` called
7. E2E: substantive unknown feedback → CodeChangeAgent email arrives with subject "product input required for news briefing"
