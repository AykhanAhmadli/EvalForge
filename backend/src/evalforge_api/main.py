from __future__ import annotations

import json

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from evalforge.config import get_settings
from evalforge.db import database_ready
from evalforge.enums import EvaluationRunStatus
from evalforge.metrics import list_metric_definitions
from evalforge_api.evaluations import router as evaluations_router
from evalforge_api.management import router as management_router
from evalforge_api.security import require_api_key

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "API for repeatable LLM evaluations and regression checks. "
        "Manage immutable dataset and prompt versions, safe model configurations, "
        "and the evaluation domain from one workspace-aware API."
    ),
    openapi_tags=[
        {"name": "health", "description": "Process and dependency health checks."},
        {"name": "metadata", "description": "Lifecycle states and metric definitions."},
        {"name": "management", "description": "Workspace, dataset, prompt, and model management."},
        {
            "name": "evaluations",
            "description": "Queued evaluation runs, results, metrics, and pricing.",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestSecurityMiddleware:
    def __init__(self, app: ASGIApp, max_request_bytes: int) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes

    @staticmethod
    async def _send_error(send: Send, status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        try:
            request_size = int(content_length) if content_length else 0
        except ValueError:
            await self._send_error(send, 400, "invalid content-length header")
            return
        if request_size > self.max_request_bytes:
            await self._send_error(send, 413, "request body exceeds the configured size limit")
            return

        received_bytes = 0

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_request_bytes:
                    raise RequestTooLarge
            return message

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                )
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, limited_receive, secure_send)
        except RequestTooLarge:
            await self._send_error(send, 413, "request body exceeds the configured size limit")


class RequestTooLarge(Exception):
    pass


app.add_middleware(RequestSecurityMiddleware, max_request_bytes=settings.max_request_bytes)

app.include_router(management_router, dependencies=[Depends(require_api_key)])
app.include_router(evaluations_router, dependencies=[Depends(require_api_key)])


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
