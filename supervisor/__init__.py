"""
Supervisor agent package.

Immediate mode (Phase 3): processes user replies in real-time.
Weekly mode (Phase 5): pattern sweep over last 7 days of feedback.
"""

from supervisor.immediate import SupervisorResult, run_immediate_supervisor

__all__ = ["SupervisorResult", "run_immediate_supervisor"]
