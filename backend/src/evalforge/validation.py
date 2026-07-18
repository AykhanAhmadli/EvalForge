from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    row_number: int
    message: str
    field: str | None = None


@dataclass(frozen=True)
class ParsedTestCase:
    row_number: int
    input: Any
    expected_output: Any
    metadata: dict[str, Any]
    tags: list[str]


@dataclass(frozen=True)
class ParsedDataset:
    source_format: str
    test_cases: list[ParsedTestCase]
    schema_fields: list[str]
    content_hash: str


VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*}}")


def extract_template_variables(template: str) -> list[str]:
    return sorted(set(VARIABLE_PATTERN.findall(template)))


def _parse_json_or_text(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _parse_csv_metadata(
    value: str, row_number: int
) -> tuple[dict[str, Any], ValidationIssue | None]:
    if not value.strip():
        return {}, None
    parsed = _parse_json_or_text(value)
    if not isinstance(parsed, dict):
        return {}, ValidationIssue(row_number, "metadata must be a JSON object", "metadata")
    return parsed, None


def _parse_tags(value: Any, row_number: int) -> tuple[list[str], ValidationIssue | None]:
    if value is None or value == "":
        return [], None
    parsed = _parse_json_or_text(value) if isinstance(value, str) else value
    if isinstance(parsed, str):
        return [tag.strip() for tag in parsed.split(",") if tag.strip()], None
    if isinstance(parsed, list) and all(isinstance(tag, str) and tag.strip() for tag in parsed):
        return [tag.strip() for tag in parsed], None
    return [], ValidationIssue(
        row_number, "tags must be a comma-separated string or JSON array", "tags"
    )


def _required_value(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _schema_fields(test_cases: Iterable[ParsedTestCase]) -> list[str]:
    fields: set[str] = {"expected_output", "metadata", "tags"}
    for test_case in test_cases:
        if isinstance(test_case.input, dict):
            fields.update(str(key) for key in test_case.input)
        else:
            fields.add("input")
    return sorted(fields)


def parse_dataset(content: bytes, source_format: str) -> ParsedDataset:
    normalized_format = source_format.lower()
    if normalized_format not in {"csv", "jsonl"}:
        raise ValueError("format must be csv or jsonl")
    if not content.strip():
        raise ValueError("dataset file is empty")

    if normalized_format == "csv":
        test_cases = _parse_csv(content)
    else:
        test_cases = _parse_jsonl(content)

    issues = [item for item in test_cases if isinstance(item, ValidationIssue)]
    if issues:
        raise DatasetValidationError(issues)
    parsed_cases = [item for item in test_cases if isinstance(item, ParsedTestCase)]
    if not parsed_cases:
        raise ValueError("dataset must contain at least one test case")
    return ParsedDataset(
        source_format=normalized_format,
        test_cases=parsed_cases,
        schema_fields=_schema_fields(parsed_cases),
        content_hash=hashlib.sha256(content).hexdigest(),
    )


def _parse_csv(content: bytes) -> list[ParsedTestCase | ValidationIssue]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV files must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = {field.strip() for field in (reader.fieldnames or []) if field}
    required = {"input", "expected_output"}
    missing_headers = sorted(required - fieldnames)
    if missing_headers:
        raise DatasetValidationError(
            [
                ValidationIssue(1, f"missing required column: {field}", field)
                for field in missing_headers
            ]
        )

    parsed: list[ParsedTestCase | ValidationIssue] = []
    for row_number, raw_row in enumerate(reader, start=2):
        row = {key.strip(): value for key, value in raw_row.items() if key}
        input_value = row.get("input")
        expected_value = row.get("expected_output")
        if not _required_value(input_value):
            parsed.append(ValidationIssue(row_number, "input is required", "input"))
            continue
        if not _required_value(expected_value):
            parsed.append(
                ValidationIssue(row_number, "expected_output is required", "expected_output")
            )
            continue
        assert isinstance(input_value, str)
        assert isinstance(expected_value, str)
        metadata, metadata_issue = _parse_csv_metadata(row.get("metadata", ""), row_number)
        if metadata_issue:
            parsed.append(metadata_issue)
            continue
        tags, tags_issue = _parse_tags(row.get("tags", ""), row_number)
        if tags_issue:
            parsed.append(tags_issue)
            continue
        parsed.append(
            ParsedTestCase(
                row_number=row_number,
                input=_parse_json_or_text(input_value),
                expected_output=_parse_json_or_text(expected_value),
                metadata=metadata,
                tags=tags,
            )
        )
    return parsed


def _parse_jsonl(content: bytes) -> list[ParsedTestCase | ValidationIssue]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("JSONL files must be UTF-8 encoded") from exc

    parsed: list[ParsedTestCase | ValidationIssue] = []
    for row_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            parsed.append(ValidationIssue(row_number, f"invalid JSON: {exc.msg}"))
            continue
        if not isinstance(row, dict):
            parsed.append(ValidationIssue(row_number, "each JSONL row must be an object"))
            continue
        if not _required_value(row.get("input")):
            parsed.append(ValidationIssue(row_number, "input is required", "input"))
            continue
        if not _required_value(row.get("expected_output")):
            parsed.append(
                ValidationIssue(row_number, "expected_output is required", "expected_output")
            )
            continue
        metadata = row.get("metadata", {})
        if not isinstance(metadata, dict):
            parsed.append(ValidationIssue(row_number, "metadata must be an object", "metadata"))
            continue
        tags, tags_issue = _parse_tags(row.get("tags", []), row_number)
        if tags_issue:
            parsed.append(tags_issue)
            continue
        parsed.append(
            ParsedTestCase(
                row_number=row_number,
                input=row["input"],
                expected_output=row["expected_output"],
                metadata=metadata,
                tags=tags,
            )
        )
    return parsed


class DatasetValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        super().__init__("dataset validation failed")


def dataset_fields(test_cases: Iterable[ParsedTestCase]) -> list[str]:
    return _schema_fields(test_cases)


def _has_field(value: Any, variable: str) -> bool:
    if variable in {"expected_output", "metadata", "tags"}:
        return True
    if not isinstance(value, dict):
        return variable == "input"
    current: Any = value
    for part in variable.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def validate_template_variables(
    variables: Iterable[str], test_cases: Iterable[ParsedTestCase]
) -> tuple[list[str], dict[int, list[str]]]:
    variable_list = sorted(set(variables))
    cases = list(test_cases)
    fields = dataset_fields(cases)
    missing_by_row = {
        case.row_number: [
            variable for variable in variable_list if not _has_field(case.input, variable)
        ]
        for case in cases
    }
    missing_by_row = {row: missing for row, missing in missing_by_row.items() if missing}
    return fields, missing_by_row
