from __future__ import annotations

import httpx
import typer
from rich.console import Console

app = typer.Typer(help="Command-line tools for the EvalForge API.")
console = Console()
error_console = Console(stderr=True)


@app.command()
def health(api_url: str = typer.Option("http://localhost:8000", help="EvalForge API URL.")) -> None:
    """Check API liveness."""
    response = httpx.get(f"{api_url.rstrip('/')}/health/live", timeout=5.0)
    response.raise_for_status()
    console.print(response.json())


@app.command()
def gate() -> None:
    """Run a CI regression gate against stored evaluation runs."""
    error_console.print(
        "The regression gate is not available yet: candidate and baseline run "
        "comparison has not been exposed by the API.",
        style="yellow",
    )
    raise typer.Exit(code=2)
