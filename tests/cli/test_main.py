from __future__ import annotations

import json

from typer.testing import CliRunner

from evalforge_cli import main
from evalforge_cli.client import UnreachableServerError

runner = CliRunner()


class FakeClient:
    def __init__(self, *, statuses: list[str] | None = None) -> None:
        self.statuses = statuses or ["completed"]
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def health(self) -> dict[str, str]:
        return {"status": "ok", "service": "api"}

    def start_suite(self, workspace_id: str, suite_id: str) -> dict[str, str]:
        assert workspace_id == "workspace-1"
        assert suite_id == "suite-1"
        return {"id": "run-1", "status": "queued"}

    def get_run(self, run_id: str) -> dict[str, str]:
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"id": run_id, "status": status}

    def compare(self, baseline_id: str, candidate_run_id: str) -> dict[str, object]:
        return {
            "baseline_id": baseline_id,
            "candidate_run_id": candidate_run_id,
            "status": "passed",
            "regression_detected": False,
            "violations": [],
        }

    def export_results(self, run_id: str) -> list[dict[str, object]]:
        return [
            {
                "id": "result-1",
                "test_case_id": "case-1",
                "status": "completed",
                "output": {"text": "ok"},
            }
        ]


def fake_factory(client: FakeClient):
    return lambda _api_url=None: client


def test_run_and_wait_passing_json(monkeypatch) -> None:
    client = FakeClient(statuses=["queued", "completed"])
    monkeypatch.setattr(main, "client_from_environment", fake_factory(client))
    run_result = runner.invoke(
        main.app, ["run", "suite-1", "--workspace-id", "workspace-1", "--json"]
    )
    wait_result = runner.invoke(main.app, ["wait", "run-1", "--poll-seconds", "0", "--json"])

    assert run_result.exit_code == 0
    assert json.loads(run_result.stdout)["id"] == "run-1"
    assert wait_result.exit_code == 0
    assert json.loads(wait_result.stdout)["status"] == "completed"


def test_wait_fails_for_cancelled_and_partially_failed_runs(monkeypatch) -> None:
    for status in ("cancelled", "partially_failed"):
        client = FakeClient(statuses=[status])
        monkeypatch.setattr(main, "client_from_environment", fake_factory(client))
        result = runner.invoke(main.app, ["wait", "run-1", "--json"])
        assert result.exit_code == 2
        assert json.loads(result.stdout)["status"] == status


def test_compare_returns_nonzero_when_rules_fail(monkeypatch) -> None:
    client = FakeClient()
    client.compare = lambda _baseline, _candidate: {
        "status": "failed",
        "regression_detected": True,
        "violations": [{"message": "score decreased"}],
    }
    monkeypatch.setattr(main, "client_from_environment", fake_factory(client))
    result = runner.invoke(main.app, ["compare", "run-1", "--baseline-id", "baseline-1", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["regression_detected"] is True


def test_timeout_and_unreachable_server_are_nonzero(monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr(main, "client_from_environment", fake_factory(client))
    monkeypatch.setattr(
        main,
        "wait_for_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("timed out")),
    )
    timed_out = runner.invoke(main.app, ["wait", "run-1", "--json"])
    assert timed_out.exit_code == 2
    assert json.loads(timed_out.stdout)["status"] == "error"

    def unreachable(_api_url=None):
        raise UnreachableServerError("server unavailable")

    monkeypatch.setattr(main, "client_from_environment", unreachable)
    unavailable = runner.invoke(
        main.app, ["run", "suite-1", "--workspace-id", "workspace-1", "--json"]
    )
    assert unavailable.exit_code == 3
    assert json.loads(unavailable.stdout)["status"] == "error"


def test_export_writes_json_and_csv(monkeypatch, tmp_path) -> None:
    client = FakeClient()
    monkeypatch.setattr(main, "client_from_environment", fake_factory(client))
    json_path = tmp_path / "results.json"
    csv_path = tmp_path / "results.csv"
    json_result = runner.invoke(main.app, ["export", "run-1", "--output", str(json_path)])
    csv_result = runner.invoke(
        main.app, ["export", "run-1", "--format", "csv", "--output", str(csv_path)]
    )
    assert json_result.exit_code == 0
    assert json.loads(json_path.read_text())[0]["id"] == "result-1"
    assert csv_result.exit_code == 0
    assert "result-1" in csv_path.read_text()
