from __future__ import annotations

import csv
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from evalforge_cli.client import (
    CLIError,
    EvalForgeClient,
    UnreachableServerError,
    client_from_environment,
    workspace_from_environment,
)

app = typer.Typer(help="Command-line tools for EvalForge CI and evaluation runs.")
console = Console()
error_console = Console(stderr=True)

TERMINAL_STATUSES = {"completed", "partially_failed", "failed", "cancelled", "canceled"}


def _emit(payload: Any, json_output: bool, summary: str) -> None:
    if json_output:
        typer.echo(json.dumps(payload, default=str, sort_keys=True))
    else:
        console.print(summary)


def _error(message: str, *, json_output: bool, code: int) -> None:
    if json_output:
        typer.echo(json.dumps({"status": "error", "message": message}, sort_keys=True))
    else:
        error_console.print(message, style="red")
    raise typer.Exit(code=code)


def _close(client: EvalForgeClient) -> None:
    client.close()


def wait_for_run(
    client: EvalForgeClient,
    run_id: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    deadline = monotonic() + timeout_seconds
    while True:
        run = client.get_run(run_id)
        status = str(run.get("status", "unknown"))
        if status in TERMINAL_STATUSES:
            return run
        if monotonic() >= deadline:
            raise TimeoutError(f"run {run_id} did not finish within {timeout_seconds:g} seconds")
        sleep(max(0.0, poll_seconds))


def _run_exit_code(status: str) -> int:
    return 0 if status == "completed" else 2


@app.command()
def health(
    api_url: str | None = typer.Option(None, envvar="EVALFORGE_API_URL", help="EvalForge API URL."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON for automation."),
) -> None:
    """Check API liveness using the configured CI credentials."""
    try:
        client = client_from_environment(api_url)
        try:
            payload = client.health()
        finally:
            _close(client)
    except UnreachableServerError as exc:
        _error(str(exc), json_output=json_output, code=3)
    except CLIError as exc:
        _error(str(exc), json_output=json_output, code=2)
    _emit(payload, json_output, f"EvalForge API: {payload.get('status', 'unknown')}")


@app.command()
def run(
    suite_id: str = typer.Argument(..., help="Configured evaluation suite ID."),
    workspace_id: str | None = typer.Option(None, envvar="EVALFORGE_WORKSPACE_ID"),
    api_url: str | None = typer.Option(None, envvar="EVALFORGE_API_URL"),
    json_output: bool = typer.Option(False, "--json", help="Print JSON for automation."),
) -> None:
    """Queue a configured evaluation suite and print its run ID."""
    try:
        client = client_from_environment(api_url)
        try:
            payload = client.start_suite(workspace_from_environment(workspace_id), suite_id)
        finally:
            _close(client)
    except UnreachableServerError as exc:
        _error(str(exc), json_output=json_output, code=3)
    except CLIError as exc:
        _error(str(exc), json_output=json_output, code=2)
    _emit(
        payload,
        json_output,
        f"Queued run {payload.get('id', 'unknown')} ({payload.get('status', 'unknown')})",
    )


@app.command()
def wait(
    run_id: str = typer.Argument(..., help="Evaluation run ID."),
    timeout_seconds: float = typer.Option(300.0, min=0.1, help="Maximum wait time."),
    poll_seconds: float = typer.Option(2.0, min=0.0, help="Polling interval."),
    api_url: str | None = typer.Option(None, envvar="EVALFORGE_API_URL"),
    json_output: bool = typer.Option(False, "--json", help="Print JSON for automation."),
) -> None:
    """Wait for a run and fail for failed, partial, or cancelled execution."""
    try:
        client = client_from_environment(api_url)
        try:
            payload = wait_for_run(
                client,
                run_id,
                timeout_seconds=timeout_seconds,
                poll_seconds=poll_seconds,
            )
        finally:
            _close(client)
    except UnreachableServerError as exc:
        _error(str(exc), json_output=json_output, code=3)
    except TimeoutError as exc:
        _error(str(exc), json_output=json_output, code=2)
    except CLIError as exc:
        _error(str(exc), json_output=json_output, code=2)
    status = str(payload.get("status", "unknown"))
    _emit(payload, json_output, f"Run {run_id}: {status}")
    if status != "completed":
        raise typer.Exit(code=_run_exit_code(status))


@app.command()
def compare(
    run_id: str = typer.Argument(..., help="Candidate evaluation run ID."),
    baseline_id: str | None = typer.Option(None, envvar="EVALFORGE_BASELINE_ID"),
    api_url: str | None = typer.Option(None, envvar="EVALFORGE_API_URL"),
    json_output: bool = typer.Option(False, "--json", help="Print JSON for automation."),
) -> None:
    """Compare a completed run with a baseline and enforce its rules."""
    if not baseline_id:
        _error("EVALFORGE_BASELINE_ID is required", json_output=json_output, code=2)
    resolved_baseline_id = baseline_id
    assert resolved_baseline_id is not None
    try:
        client = client_from_environment(api_url)
        try:
            payload = client.compare(resolved_baseline_id, run_id)
        finally:
            _close(client)
    except UnreachableServerError as exc:
        _error(str(exc), json_output=json_output, code=3)
    except CLIError as exc:
        _error(str(exc), json_output=json_output, code=2)
    status = str(payload.get("status", "unknown"))
    violations = payload.get("violations") or []
    summary = f"Comparison {status}: {len(violations)} rule violation(s)"
    _emit(payload, json_output, summary)
    if payload.get("regression_detected") or status != "passed":
        raise typer.Exit(code=1)


@app.command()
def export(
    run_id: str = typer.Argument(..., help="Evaluation run ID."),
    format: str = typer.Option("json", "--format", case_sensitive=False),
    output: str = typer.Option("-", "--output", help="Output path, or - for stdout."),
    api_url: str | None = typer.Option(None, envvar="EVALFORGE_API_URL"),
    json_output: bool = typer.Option(False, "--json", help="Print an export summary as JSON."),
) -> None:
    """Export stored case results as JSON or CSV without inventing values."""
    if format.lower() not in {"json", "csv"}:
        _error("--format must be json or csv", json_output=json_output, code=2)
    try:
        client = client_from_environment(api_url)
        try:
            results = client.export_results(run_id)
        finally:
            _close(client)
    except UnreachableServerError as exc:
        _error(str(exc), json_output=json_output, code=3)
    except CLIError as exc:
        _error(str(exc), json_output=json_output, code=2)

    if format.lower() == "json":
        content = json.dumps(results, default=str, indent=2) + "\n"
    else:
        columns = ["id", "test_case_id", "status", "output", "latency_ms", "token_usage", "error"]
        rows = []
        for result in results:
            rows.append(
                {
                    "id": result.get("id"),
                    "test_case_id": result.get("test_case_id"),
                    "status": result.get("status"),
                    "output": json.dumps(result.get("output"), default=str, sort_keys=True),
                    "latency_ms": result.get("latency_ms"),
                    "token_usage": json.dumps(
                        result.get("token_usage"), default=str, sort_keys=True
                    ),
                    "error": result.get("error_message"),
                }
            )
        writer_buffer = _StringListWriter()
        writer = csv.DictWriter(writer_buffer, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        content = "".join(writer_buffer.parts)
    if output == "-":
        if json_output:
            typer.echo(
                json.dumps({"run_id": run_id, "format": format.lower(), "count": len(results)})
            )
        else:
            sys.stdout.write(content)
    else:
        Path(output).write_text(content, encoding="utf-8")
        _emit(
            {"run_id": run_id, "format": format.lower(), "count": len(results), "output": output},
            json_output,
            f"Exported {len(results)} result(s) to {output}",
        )


class _StringListWriter:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def write(self, value: str) -> int:
        self.parts.append(value)
        return len(value)


if __name__ == "__main__":
    app()
