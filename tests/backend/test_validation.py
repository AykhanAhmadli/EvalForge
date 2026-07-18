from __future__ import annotations

import json

import pytest

from evalforge.validation import (
    DatasetValidationError,
    extract_template_variables,
    parse_dataset,
    validate_template_variables,
)


def test_parse_csv_accepts_json_input_and_reports_schema() -> None:
    parsed = parse_dataset(
        (
            b"input,expected_output,metadata,tags\n"
            b'"{""question"": ""2 + 2""}",4,"{""source"": ""unit""}",math\n'
        ),
        "csv",
    )

    assert parsed.source_format == "csv"
    assert parsed.schema_fields == ["expected_output", "metadata", "question", "tags"]
    assert parsed.test_cases[0].input == {"question": "2 + 2"}
    assert parsed.test_cases[0].metadata == {"source": "unit"}
    assert parsed.test_cases[0].tags == ["math"]


def test_parse_jsonl_requires_input_and_expected_output() -> None:
    with pytest.raises(DatasetValidationError) as exc_info:
        parse_dataset(
            (json.dumps({"input": {"question": "hello"}}) + "\n").encode(),
            "jsonl",
        )

    assert exc_info.value.issues[0].row_number == 1
    assert exc_info.value.issues[0].field == "expected_output"


def test_prompt_variables_are_extracted_and_checked_per_row() -> None:
    variables = extract_template_variables("{{ question }} / {{ customer.name }} / {{ question }}")
    parsed = parse_dataset(
        (
            json.dumps(
                {"input": {"question": "hello", "customer": {"name": "A"}}, "expected_output": "hi"}
            )
            + "\n"
            + json.dumps({"input": {"question": "bye"}, "expected_output": "bye"})
        ).encode(),
        "jsonl",
    )

    fields, missing = validate_template_variables(variables, parsed.test_cases)

    assert fields == ["customer", "expected_output", "metadata", "question", "tags"]
    assert missing == {2: ["customer.name"]}
