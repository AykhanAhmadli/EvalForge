from __future__ import annotations

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from evalforge.config import get_settings
from evalforge.db import database_ready
from evalforge.enums import EvaluationRunStatus
from evalforge.metrics import list_metric_definitions

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API for repeatable LLM evaluations and regression checks.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.get("/health/ready", tags=["health"])
def ready(response: Response) -> dict[str, str]:
    if not database_ready():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "service": "api", "dependency": "database"}
    return {"status": "ready", "service": "api", "dependency": "database"}


@app.get("/api/v1/lifecycle", tags=["metadata"])
def lifecycle() -> dict[str, list[str]]:
    return {"evaluation_run_statuses": [status_value.value for status_value in EvaluationRunStatus]}


@app.get("/api/v1/metrics", tags=["metadata"])
def metrics() -> dict[str, list[dict[str, str]]]:
    return {"metrics": list_metric_definitions()}
