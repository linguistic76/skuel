"""
User learning state — ADR-048 properties held on the User node, outside the model.
=================================================================================

Two exponential moving averages a completion teaches, each written by its own
handler through a backend map write and read raw beside it; the ``User`` model
declares none of them (they are its ``NODE_STATE``, ``core/models/node_state.py``).
Each writer refuses a key outside its set.

See: /docs/decisions/ADR-048-adaptive-learning-loop.md
"""

from typing import Final

#: A learner's actual-over-estimated task duration ratio, how many completions taught
#: it, and when it last moved: ``TaskEventHandlerService._calibrate_duration`` writes
#: them (``TasksBackend.update_user_learning_state``) and reads them back
#: (``get_user_learning_state``).
TASK_DURATION_LEARNING_PROPERTIES: Final[frozenset[str]] = frozenset(
    {"task_duration_ratio", "task_completion_count", "task_duration_updated_at"}
)

#: A teacher's average hours to feedback, how many reviews taught it, and when it last
#: moved: the learning-loop handler writes them
#: (``UserEntryBackend.update_teacher_feedback_state``) and reads them back
#: (``get_teacher_feedback_state``).
TEACHER_FEEDBACK_PROPERTIES: Final[frozenset[str]] = frozenset(
    {"feedback_ema_hours", "feedback_sample_count", "feedback_updated_at"}
)
