from __future__ import annotations

from enum import StrEnum


class EvaluationRunStatus(StrEnum):
    draft = "draft"
    queued = "queued"
    provisioning = "provisioning"
    running = "running"
    scoring = "scoring"
    completed = "completed"
    partially_failed = "partially_failed"
    failed = "failed"
    cancelled = "cancelled"
    canceled = "canceled"


class EvaluationItemStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class JobKind(StrEnum):
    evaluation_run = "evaluation.run"
