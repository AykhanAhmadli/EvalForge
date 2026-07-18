from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from evalforge.db import database_ready
from evalforge_api.main import app

pytestmark = pytest.mark.skipif(not database_ready(), reason="PostgreSQL is not running")

client = TestClient(app)


@pytest.fixture
def workspace_id() -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={
            "name": "API Test Workspace",
            "slug": f"api-test-{uuid4().hex[:12]}",
        },
    )
    assert response.status_code == 201, response.text
    workspace_id = response.json()["id"]
    yield workspace_id
    delete_response = client.delete(f"/api/v1/workspaces/{workspace_id}")
    assert delete_response.status_code == 204, delete_response.text


def test_dataset_upload_preview_export_and_immutability(workspace_id: str) -> None:
    dataset_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        json={"name": "Support Questions", "tags": ["regression"]},
    )
    assert dataset_response.status_code == 201, dataset_response.text
    dataset_id = dataset_response.json()["id"]

    content = "\n".join(
        [
            json.dumps(
                {
                    "input": {"question": "What is 2 + 2?"},
                    "expected_output": "4",
                    "metadata": {"source": "test"},
                    "tags": ["math"],
                }
            ),
            json.dumps(
                {
                    "input": {"question": "What is the capital of France?"},
                    "expected_output": "Paris",
                }
            ),
        ]
    )
    upload_response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/upload",
        files={"file": ("cases.jsonl", content.encode(), "application/x-ndjson")},
    )
    assert upload_response.status_code == 201, upload_response.text
    version = upload_response.json()
    assert version["version_number"] == 1
    assert version["row_count"] == 2
    assert version["test_cases"][0]["metadata"] == {"source": "test"}

    preview_response = client.get(f"/api/v1/dataset-versions/{version['id']}/preview?limit=1")
    assert preview_response.status_code == 200
    assert len(preview_response.json()["test_cases"]) == 1

    export_response = client.get(f"/api/v1/dataset-versions/{version['id']}/export")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("application/x-ndjson")
    first_exported_row = json.loads(export_response.text.splitlines()[0])
    assert first_exported_row["expected_output"] == "4"

    second_version_response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        json={"test_cases": [{"input": {"question": "What is 3 + 3?"}, "expected_output": "6"}]},
    )
    assert second_version_response.status_code == 201
    assert second_version_response.json()["version_number"] == 2
    original_response = client.get(f"/api/v1/dataset-versions/{version['id']}")
    assert original_response.json()["version"]["row_count"] == 2


def test_dataset_validation_reports_row_numbers(workspace_id: str) -> None:
    dataset_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets", json={"name": "Invalid Cases"}
    )
    dataset_id = dataset_response.json()["id"]
    upload_response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/upload",
        files={
            "file": (
                "invalid.csv",
                b"input,expected_output\nhello,\nworld,ok\n",
                "text/csv",
            )
        },
    )
    assert upload_response.status_code == 422
    detail = upload_response.json()["detail"]
    assert detail["errors"] == [
        {"row_number": 2, "field": "expected_output", "message": "expected_output is required"}
    ]


def test_prompt_validation_and_model_secret_protection(workspace_id: str) -> None:
    dataset_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets", json={"name": "Prompt Cases"}
    )
    dataset_id = dataset_response.json()["id"]
    version_response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        json={
            "test_cases": [
                {"input": {"question": "hello"}, "expected_output": "hi"},
                {"input": {"question": "goodbye"}, "expected_output": "bye"},
            ]
        },
    )
    version_id = version_response.json()["id"]

    template_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/prompt-templates",
        json={"name": "Answer", "template": "Answer: {{ question }}"},
    )
    assert template_response.status_code == 201
    template = template_response.json()
    prompt_version_id = template["versions"][0]["id"]
    validation_response = client.post(
        f"/api/v1/prompt-versions/{prompt_version_id}/validate",
        params={"dataset_version_id": version_id},
    )
    assert validation_response.json()["valid"] is True

    second_prompt_response = client.post(
        f"/api/v1/prompt-templates/{template['id']}/versions",
        json={"template": "Answer: {{ missing }}"},
    )
    second_prompt_id = second_prompt_response.json()["id"]
    invalid_response = client.post(
        f"/api/v1/prompt-versions/{second_prompt_id}/validate",
        params={"dataset_version_id": version_id},
    )
    assert invalid_response.json()["valid"] is False
    assert invalid_response.json()["missing_variables_by_row"] == {
        "1": ["missing"],
        "2": ["missing"],
    }

    comparison_response = client.get(
        f"/api/v1/prompt-templates/{template['id']}/compare",
        params={
            "base_version_id": prompt_version_id,
            "candidate_version_id": second_prompt_id,
        },
    )
    assert "missing" in comparison_response.json()["unified_diff"]

    secret_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/model-configurations",
        json={
            "name": "Bad Secret",
            "provider": "fake",
            "model_name": "fake-v1",
            "parameters": {"api_key": "must-not-be-accepted"},
        },
    )
    assert secret_response.status_code == 422

    model_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/model-configurations",
        json={
            "name": "Safe Fake",
            "provider": "fake",
            "model_name": "fake-v1",
            "parameters": {"top_p": 0.9},
        },
    )
    assert model_response.status_code == 201, model_response.text
    assert model_response.json()["parameters"] == {"top_p": 0.9}
