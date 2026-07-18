from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from evalforge.config import get_settings
from evalforge.db import get_session
from evalforge.models import (
    Dataset,
    DatasetVersion,
    EvaluationSuite,
    ModelConfiguration,
    PromptTemplate,
    PromptVersion,
    TestCase,
    Workspace,
)
from evalforge.providers import available_provider_names
from evalforge.schemas import (
    DatasetCreate,
    DatasetResponse,
    DatasetUpdate,
    DatasetVersionCreate,
    DatasetVersionPreviewResponse,
    DatasetVersionResponse,
    EvaluationSuiteCreate,
    EvaluationSuiteResponse,
    EvaluationSuiteUpdate,
    ModelConfigurationCreate,
    ModelConfigurationResponse,
    ModelConfigurationUpdate,
    ModelProviderResponse,
    PromptComparisonResponse,
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    PromptValidationResponse,
    PromptVersionCreate,
    PromptVersionResponse,
    TestCaseResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from evalforge.validation import (
    DatasetValidationError,
    ParsedTestCase,
    dataset_fields,
    extract_template_variables,
    parse_dataset,
    validate_template_variables,
)
from evalforge_api.security import (
    ApiPrincipal,
    ensure_resource_access,
    filter_workspace_rows,
    require_api_key,
)

router = APIRouter(prefix="/api/v1", tags=["management"])


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def conflict(message: str = "An object with the same name already exists") -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def not_found(kind: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind} not found")


def commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise conflict() from exc


def get_or_404(session: Session, model: type[Any], object_id: UUID, kind: str) -> Any:
    value = session.get(model, object_id)
    if value is None:
        raise not_found(kind)
    ensure_resource_access(session, value)
    return value


def _test_case_response(test_case: TestCase) -> TestCaseResponse:
    return TestCaseResponse(
        id=test_case.id,
        dataset_version_id=test_case.dataset_version_id,
        row_number=test_case.row_number,
        input=test_case.input,
        expected_output=test_case.expected_output,
        metadata=test_case.row_metadata,
        tags=test_case.tags,
    )


def _version_response(
    version: DatasetVersion, test_cases: list[TestCase] | None = None
) -> DatasetVersionResponse:
    return DatasetVersionResponse(
        id=version.id,
        dataset_id=version.dataset_id,
        version_number=version.version_number,
        source_format=version.source_format,  # type: ignore[arg-type]
        row_count=version.row_count,
        schema_fields=version.schema_fields,
        content_hash=version.content_hash,
        created_by=version.created_by,
        test_cases=[_test_case_response(case) for case in test_cases]
        if test_cases is not None
        else None,
    )


def _next_version_number(session: Session, dataset_id: UUID) -> int:
    latest = session.scalar(
        select(func.max(DatasetVersion.version_number)).where(
            DatasetVersion.dataset_id == dataset_id
        )
    )
    return int(latest or 0) + 1


def _create_version(
    session: Session,
    dataset: Dataset,
    *,
    source_format: str,
    content_hash: str,
    schema_fields: list[str],
    test_cases: Iterable[ParsedTestCase],
    created_by: str | None,
) -> DatasetVersion:
    parsed_cases = list(test_cases)
    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=_next_version_number(session, dataset.id),
        source_format=source_format,
        row_count=len(parsed_cases),
        schema_fields=schema_fields,
        content_hash=content_hash,
        created_by=created_by,
    )
    session.add(version)
    session.flush()
    session.add_all(
        [
            TestCase(
                dataset_version_id=version.id,
                row_number=case.row_number,
                input=case.input,
                expected_output=case.expected_output,
                row_metadata=case.metadata,
                tags=case.tags,
            )
            for case in parsed_cases
        ]
    )
    commit(session)
    session.refresh(version)
    return version


def _parsed_cases(test_cases: Iterable[TestCase]) -> list[ParsedTestCase]:
    return [
        ParsedTestCase(
            row_number=case.row_number,
            input=case.input,
            expected_output=case.expected_output,
            metadata=case.row_metadata,
            tags=case.tags,
        )
        for case in test_cases
    ]


def _safe_parameters(value: Any) -> Any:
    secret_parts = (
        "authorization",
        "bearer",
        "credential",
        "key",
        "password",
        "secret",
        "token",
    )
    if isinstance(value, dict):
        return {
            key: _safe_parameters(item)
            for key, item in value.items()
            if not any(part in key.lower() for part in secret_parts)
        }
    if isinstance(value, list):
        return [_safe_parameters(item) for item in value]
    return value


def _model_response(configuration: ModelConfiguration) -> ModelConfigurationResponse:
    return ModelConfigurationResponse(
        id=configuration.id,
        workspace_id=configuration.workspace_id,
        name=configuration.name,
        slug=configuration.slug,
        provider=configuration.provider,
        model_name=configuration.model_name,
        temperature=configuration.temperature,
        max_tokens=configuration.max_tokens,
        timeout_seconds=configuration.timeout_seconds,
        parameters=_safe_parameters(configuration.parameters),
    )


def _validate_suite_references(
    session: Session,
    workspace_id: UUID,
    *,
    dataset_version_id: UUID | None,
    prompt_version_id: UUID | None,
    model_configuration_id: UUID | None,
) -> None:
    if dataset_version_id is not None:
        version = get_or_404(session, DatasetVersion, dataset_version_id, "dataset version")
        dataset = get_or_404(session, Dataset, version.dataset_id, "dataset")
        if dataset.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="dataset is not in this workspace")
    if prompt_version_id is not None:
        version = get_or_404(session, PromptVersion, prompt_version_id, "prompt version")
        template = get_or_404(
            session, PromptTemplate, version.prompt_template_id, "prompt template"
        )
        if template.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="prompt is not in this workspace")
    if model_configuration_id is not None:
        model = get_or_404(
            session, ModelConfiguration, model_configuration_id, "model configuration"
        )
        if model.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="model is not in this workspace")


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    session: Session = Depends(get_session),
    principal: ApiPrincipal = Depends(require_api_key),
) -> Workspace:
    if principal.workspace_ids is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="workspace creation requires administrative provisioning",
        )
    workspace = Workspace(
        name=payload.name,
        slug=payload.slug or slugify(payload.name),
        description=payload.description,
    )
    session.add(workspace)
    commit(session)
    session.refresh(workspace)
    return workspace


@router.get("/workspaces", response_model=list[WorkspaceResponse])
def list_workspaces(
    session: Session = Depends(get_session),
    principal: ApiPrincipal = Depends(require_api_key),
) -> list[Workspace]:
    rows = list(session.scalars(select(Workspace).order_by(Workspace.name)).all())
    return filter_workspace_rows(rows, principal)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace_id: UUID, session: Session = Depends(get_session)) -> Workspace:
    return get_or_404(session, Workspace, workspace_id, "workspace")


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: UUID, payload: WorkspaceUpdate, session: Session = Depends(get_session)
) -> Workspace:
    workspace = get_or_404(session, Workspace, workspace_id, "workspace")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workspace, field, value)
    commit(session)
    session.refresh(workspace)
    return workspace


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(workspace_id: UUID, session: Session = Depends(get_session)) -> Response:
    workspace = get_or_404(session, Workspace, workspace_id, "workspace")
    session.delete(workspace)
    commit(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workspaces/{workspace_id}/suites",
    response_model=EvaluationSuiteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_suite(
    workspace_id: UUID,
    payload: EvaluationSuiteCreate,
    session: Session = Depends(get_session),
) -> EvaluationSuite:
    get_or_404(session, Workspace, workspace_id, "workspace")
    _validate_suite_references(
        session,
        workspace_id,
        dataset_version_id=payload.dataset_version_id,
        prompt_version_id=payload.prompt_version_id,
        model_configuration_id=payload.model_configuration_id,
    )
    suite = EvaluationSuite(
        workspace_id=workspace_id,
        name=payload.name,
        slug=payload.slug or slugify(payload.name),
        description=payload.description,
        dataset_version_id=payload.dataset_version_id,
        prompt_version_id=payload.prompt_version_id,
        model_configuration_id=payload.model_configuration_id,
        metric_names=payload.metric_names,
        metric_options=payload.metric_options,
    )
    session.add(suite)
    commit(session)
    session.refresh(suite)
    return suite


@router.get("/workspaces/{workspace_id}/suites", response_model=list[EvaluationSuiteResponse])
def list_suites(
    workspace_id: UUID, session: Session = Depends(get_session)
) -> list[EvaluationSuite]:
    get_or_404(session, Workspace, workspace_id, "workspace")
    return list(
        session.scalars(
            select(EvaluationSuite)
            .where(EvaluationSuite.workspace_id == workspace_id)
            .order_by(EvaluationSuite.name)
        ).all()
    )


@router.get("/suites/{suite_id}", response_model=EvaluationSuiteResponse)
def get_suite(suite_id: UUID, session: Session = Depends(get_session)) -> EvaluationSuite:
    return get_or_404(session, EvaluationSuite, suite_id, "evaluation suite")


@router.patch("/suites/{suite_id}", response_model=EvaluationSuiteResponse)
def update_suite(
    suite_id: UUID, payload: EvaluationSuiteUpdate, session: Session = Depends(get_session)
) -> EvaluationSuite:
    suite = get_or_404(session, EvaluationSuite, suite_id, "evaluation suite")
    changes = payload.model_dump(exclude_unset=True)
    _validate_suite_references(
        session,
        suite.workspace_id,
        dataset_version_id=changes.get("dataset_version_id", suite.dataset_version_id),
        prompt_version_id=changes.get("prompt_version_id", suite.prompt_version_id),
        model_configuration_id=changes.get("model_configuration_id", suite.model_configuration_id),
    )
    for field, value in changes.items():
        setattr(suite, field, value)
    commit(session)
    session.refresh(suite)
    return suite


@router.delete("/suites/{suite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suite(suite_id: UUID, session: Session = Depends(get_session)) -> Response:
    suite = get_or_404(session, EvaluationSuite, suite_id, "evaluation suite")
    session.delete(suite)
    commit(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workspaces/{workspace_id}/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(
    workspace_id: UUID, payload: DatasetCreate, session: Session = Depends(get_session)
) -> Dataset:
    get_or_404(session, Workspace, workspace_id, "workspace")
    dataset = Dataset(
        workspace_id=workspace_id,
        name=payload.name,
        slug=payload.slug or slugify(payload.name),
        description=payload.description,
        tags=payload.tags,
    )
    session.add(dataset)
    commit(session)
    session.refresh(dataset)
    return dataset


@router.get("/workspaces/{workspace_id}/datasets", response_model=list[DatasetResponse])
def list_datasets(workspace_id: UUID, session: Session = Depends(get_session)) -> list[Dataset]:
    get_or_404(session, Workspace, workspace_id, "workspace")
    return list(
        session.scalars(
            select(Dataset).where(Dataset.workspace_id == workspace_id).order_by(Dataset.name)
        ).all()
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: UUID, session: Session = Depends(get_session)) -> Dataset:
    return get_or_404(session, Dataset, dataset_id, "dataset")


@router.patch("/datasets/{dataset_id}", response_model=DatasetResponse)
def update_dataset(
    dataset_id: UUID, payload: DatasetUpdate, session: Session = Depends(get_session)
) -> Dataset:
    dataset = get_or_404(session, Dataset, dataset_id, "dataset")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dataset, field, value)
    commit(session)
    session.refresh(dataset)
    return dataset


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: UUID, session: Session = Depends(get_session)) -> Response:
    dataset = get_or_404(session, Dataset, dataset_id, "dataset")
    session.delete(dataset)
    commit(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/datasets/{dataset_id}/versions",
    response_model=DatasetVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_dataset_version(
    dataset_id: UUID,
    payload: DatasetVersionCreate,
    session: Session = Depends(get_session),
) -> DatasetVersionResponse:
    dataset = get_or_404(session, Dataset, dataset_id, "dataset")
    parsed = [
        ParsedTestCase(
            row_number=index,
            input=test_case.input,
            expected_output=test_case.expected_output,
            metadata=test_case.metadata,
            tags=test_case.tags,
        )
        for index, test_case in enumerate(payload.test_cases, start=1)
    ]
    canonical = json.dumps([case.__dict__ for case in parsed], sort_keys=True, default=str).encode()
    version = _create_version(
        session,
        dataset,
        source_format="manual",
        content_hash=hashlib.sha256(canonical).hexdigest(),
        schema_fields=dataset_fields(parsed),
        test_cases=parsed,
        created_by=payload.created_by,
    )
    cases = list(
        session.scalars(
            select(TestCase)
            .where(TestCase.dataset_version_id == version.id)
            .order_by(TestCase.row_number)
        ).all()
    )
    return _version_response(version, cases)


@router.post(
    "/datasets/{dataset_id}/versions/upload",
    response_model=DatasetVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset_version(
    dataset_id: UUID,
    file: UploadFile = File(...),
    file_format: Literal["csv", "jsonl"] | None = Form(default=None),
    created_by: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> DatasetVersionResponse:
    dataset = get_or_404(session, Dataset, dataset_id, "dataset")
    settings = get_settings()
    filename = (file.filename or "").lower()
    suffix = filename.rsplit(".", 1)[-1] if "." in filename else ""
    suffix_format = "jsonl" if suffix in {"jsonl", "ndjson"} else suffix
    if file_format is None and suffix_format not in {"csv", "jsonl"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="upload filename must end in .csv, .jsonl, or .ndjson",
        )
    if (
        file_format is not None
        and suffix_format in {"csv", "jsonl"}
        and suffix_format != file_format
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="file format does not match the filename extension",
        )
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="dataset upload exceeds the configured size limit",
        )
    inferred_format: str | None = file_format
    if inferred_format is None:
        inferred_format = suffix_format
    try:
        parsed_dataset = parse_dataset(content, inferred_format or "")
    except DatasetValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": str(exc),
                "errors": [
                    {
                        "row_number": issue.row_number,
                        "field": issue.field,
                        "message": issue.message,
                    }
                    for issue in exc.issues
                ],
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    version = _create_version(
        session,
        dataset,
        source_format=parsed_dataset.source_format,
        content_hash=parsed_dataset.content_hash,
        schema_fields=parsed_dataset.schema_fields,
        test_cases=parsed_dataset.test_cases,
        created_by=created_by,
    )
    cases = list(
        session.scalars(
            select(TestCase)
            .where(TestCase.dataset_version_id == version.id)
            .order_by(TestCase.row_number)
        ).all()
    )
    return _version_response(version, cases)


@router.get("/datasets/{dataset_id}/versions", response_model=list[DatasetVersionResponse])
def list_dataset_versions(
    dataset_id: UUID, session: Session = Depends(get_session)
) -> list[DatasetVersionResponse]:
    get_or_404(session, Dataset, dataset_id, "dataset")
    versions = session.scalars(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.version_number.desc())
    ).all()
    return [_version_response(version) for version in versions]


@router.get("/dataset-versions/{version_id}", response_model=DatasetVersionPreviewResponse)
def get_dataset_version(
    version_id: UUID, session: Session = Depends(get_session)
) -> DatasetVersionPreviewResponse:
    version = get_or_404(session, DatasetVersion, version_id, "dataset version")
    cases = list(
        session.scalars(
            select(TestCase)
            .where(TestCase.dataset_version_id == version.id)
            .order_by(TestCase.row_number)
        ).all()
    )
    return DatasetVersionPreviewResponse(
        version=_version_response(version),
        test_cases=[_test_case_response(case) for case in cases],
    )


@router.get("/dataset-versions/{version_id}/preview", response_model=DatasetVersionPreviewResponse)
def preview_dataset_version(
    version_id: UUID,
    limit: int = Query(default=20, ge=1, le=500),
    session: Session = Depends(get_session),
) -> DatasetVersionPreviewResponse:
    version = get_or_404(session, DatasetVersion, version_id, "dataset version")
    cases = list(
        session.scalars(
            select(TestCase)
            .where(TestCase.dataset_version_id == version.id)
            .order_by(TestCase.row_number)
            .limit(limit)
        ).all()
    )
    return DatasetVersionPreviewResponse(
        version=_version_response(version),
        test_cases=[_test_case_response(case) for case in cases],
    )


@router.get("/dataset-versions/{version_id}/export")
def export_dataset_version(version_id: UUID, session: Session = Depends(get_session)) -> Response:
    version = get_or_404(session, DatasetVersion, version_id, "dataset version")
    cases = session.scalars(
        select(TestCase)
        .where(TestCase.dataset_version_id == version.id)
        .order_by(TestCase.row_number)
    ).all()
    body = "".join(
        json.dumps(
            {
                "input": case.input,
                "expected_output": case.expected_output,
                "metadata": case.row_metadata,
                "tags": case.tags,
            },
            sort_keys=True,
        )
        + "\n"
        for case in cases
    )
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="dataset-v{version.version_number}.jsonl"'
        },
    )


@router.post(
    "/workspaces/{workspace_id}/prompt-templates",
    response_model=PromptTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_prompt_template(
    workspace_id: UUID,
    payload: PromptTemplateCreate,
    session: Session = Depends(get_session),
) -> PromptTemplateResponse:
    get_or_404(session, Workspace, workspace_id, "workspace")
    template = PromptTemplate(
        workspace_id=workspace_id,
        name=payload.name,
        slug=payload.slug or slugify(payload.name),
        description=payload.description,
        tags=payload.tags,
    )
    session.add(template)
    session.flush()
    session.add(
        PromptVersion(
            prompt_template_id=template.id,
            version_number=1,
            template=payload.template,
            variables=extract_template_variables(payload.template),
            created_by=payload.created_by,
        )
    )
    commit(session)
    session.refresh(template)
    versions = list(
        session.scalars(
            select(PromptVersion)
            .where(PromptVersion.prompt_template_id == template.id)
            .order_by(PromptVersion.version_number)
        ).all()
    )
    return PromptTemplateResponse(
        id=template.id,
        workspace_id=template.workspace_id,
        name=template.name,
        slug=template.slug,
        description=template.description,
        tags=template.tags,
        versions=[PromptVersionResponse.model_validate(version) for version in versions],
    )


@router.get(
    "/workspaces/{workspace_id}/prompt-templates", response_model=list[PromptTemplateResponse]
)
def list_prompt_templates(
    workspace_id: UUID, session: Session = Depends(get_session)
) -> list[PromptTemplateResponse]:
    get_or_404(session, Workspace, workspace_id, "workspace")
    templates = session.scalars(
        select(PromptTemplate)
        .where(PromptTemplate.workspace_id == workspace_id)
        .order_by(PromptTemplate.name)
    ).all()
    return [
        PromptTemplateResponse(
            id=template.id,
            workspace_id=template.workspace_id,
            name=template.name,
            slug=template.slug,
            description=template.description,
            tags=template.tags,
        )
        for template in templates
    ]


@router.get("/prompt-templates/{template_id}", response_model=PromptTemplateResponse)
def get_prompt_template(
    template_id: UUID, session: Session = Depends(get_session)
) -> PromptTemplateResponse:
    template = get_or_404(session, PromptTemplate, template_id, "prompt template")
    versions = session.scalars(
        select(PromptVersion)
        .where(PromptVersion.prompt_template_id == template.id)
        .order_by(PromptVersion.version_number)
    ).all()
    return PromptTemplateResponse(
        id=template.id,
        workspace_id=template.workspace_id,
        name=template.name,
        slug=template.slug,
        description=template.description,
        tags=template.tags,
        versions=[PromptVersionResponse.model_validate(version) for version in versions],
    )


@router.patch("/prompt-templates/{template_id}", response_model=PromptTemplateResponse)
def update_prompt_template(
    template_id: UUID,
    payload: PromptTemplateUpdate,
    session: Session = Depends(get_session),
) -> PromptTemplateResponse:
    template = get_or_404(session, PromptTemplate, template_id, "prompt template")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    commit(session)
    session.refresh(template)
    return get_prompt_template(template_id, session)


@router.delete("/prompt-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt_template(template_id: UUID, session: Session = Depends(get_session)) -> Response:
    template = get_or_404(session, PromptTemplate, template_id, "prompt template")
    session.delete(template)
    commit(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/prompt-templates/{template_id}/versions",
    response_model=PromptVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_prompt_version(
    template_id: UUID,
    payload: PromptVersionCreate,
    session: Session = Depends(get_session),
) -> PromptVersion:
    get_or_404(session, PromptTemplate, template_id, "prompt template")
    latest = session.scalar(
        select(func.max(PromptVersion.version_number)).where(
            PromptVersion.prompt_template_id == template_id
        )
    )
    version = PromptVersion(
        prompt_template_id=template_id,
        version_number=int(latest or 0) + 1,
        template=payload.template,
        variables=extract_template_variables(payload.template),
        created_by=payload.created_by,
    )
    session.add(version)
    commit(session)
    session.refresh(version)
    return version


@router.get("/prompt-templates/{template_id}/versions", response_model=list[PromptVersionResponse])
def list_prompt_versions(
    template_id: UUID, session: Session = Depends(get_session)
) -> list[PromptVersion]:
    get_or_404(session, PromptTemplate, template_id, "prompt template")
    return list(
        session.scalars(
            select(PromptVersion)
            .where(PromptVersion.prompt_template_id == template_id)
            .order_by(PromptVersion.version_number)
        ).all()
    )


@router.get("/prompt-versions/{version_id}", response_model=PromptVersionResponse)
def get_prompt_version(version_id: UUID, session: Session = Depends(get_session)) -> PromptVersion:
    return get_or_404(session, PromptVersion, version_id, "prompt version")


@router.post("/prompt-versions/{version_id}/validate", response_model=PromptValidationResponse)
def validate_prompt_version(
    version_id: UUID, dataset_version_id: UUID, session: Session = Depends(get_session)
) -> PromptValidationResponse:
    version = get_or_404(session, PromptVersion, version_id, "prompt version")
    dataset_version = get_or_404(session, DatasetVersion, dataset_version_id, "dataset version")
    cases = session.scalars(
        select(TestCase)
        .where(TestCase.dataset_version_id == dataset_version.id)
        .order_by(TestCase.row_number)
    ).all()
    parsed_cases = _parsed_cases(cases)
    fields, missing = validate_template_variables(version.variables, parsed_cases)
    return PromptValidationResponse(
        prompt_version_id=version.id,
        dataset_version_id=dataset_version.id,
        valid=not missing,
        required_variables=version.variables,
        dataset_fields=fields,
        missing_variables_by_row=missing,
    )


@router.get("/prompt-templates/{template_id}/compare", response_model=PromptComparisonResponse)
def compare_prompt_versions(
    template_id: UUID,
    base_version_id: UUID,
    candidate_version_id: UUID,
    session: Session = Depends(get_session),
) -> PromptComparisonResponse:
    get_or_404(session, PromptTemplate, template_id, "prompt template")
    base = get_or_404(session, PromptVersion, base_version_id, "base prompt version")
    candidate = get_or_404(session, PromptVersion, candidate_version_id, "candidate prompt version")
    if base.prompt_template_id != template_id or candidate.prompt_template_id != template_id:
        raise HTTPException(status_code=400, detail="prompt versions must belong to the template")
    diff = "".join(
        difflib.unified_diff(
            base.template.splitlines(keepends=True),
            candidate.template.splitlines(keepends=True),
            fromfile=f"version-{base.version_number}",
            tofile=f"version-{candidate.version_number}",
        )
    )
    return PromptComparisonResponse(
        prompt_template_id=template_id,
        base_version_id=base.id,
        candidate_version_id=candidate.id,
        base_variables=base.variables,
        candidate_variables=candidate.variables,
        changed_variables=sorted(set(base.variables) ^ set(candidate.variables)),
        unified_diff=diff,
    )


@router.post(
    "/workspaces/{workspace_id}/model-configurations",
    response_model=ModelConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_model_configuration(
    workspace_id: UUID,
    payload: ModelConfigurationCreate,
    session: Session = Depends(get_session),
) -> ModelConfigurationResponse:
    get_or_404(session, Workspace, workspace_id, "workspace")
    if payload.provider not in available_provider_names():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unsupported provider: {payload.provider}",
        )
    configuration = ModelConfiguration(
        workspace_id=workspace_id,
        name=payload.name,
        slug=payload.slug or slugify(payload.name),
        provider=payload.provider,
        model_name=payload.model_name,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        timeout_seconds=payload.timeout_seconds,
        parameters=payload.parameters,
    )
    session.add(configuration)
    commit(session)
    session.refresh(configuration)
    return _model_response(configuration)


@router.get(
    "/workspaces/{workspace_id}/model-configurations",
    response_model=list[ModelConfigurationResponse],
)
def list_model_configurations(
    workspace_id: UUID, session: Session = Depends(get_session)
) -> list[ModelConfigurationResponse]:
    get_or_404(session, Workspace, workspace_id, "workspace")
    configurations = session.scalars(
        select(ModelConfiguration)
        .where(ModelConfiguration.workspace_id == workspace_id)
        .order_by(ModelConfiguration.name)
    ).all()
    return [_model_response(configuration) for configuration in configurations]


@router.get("/model-configurations/{configuration_id}", response_model=ModelConfigurationResponse)
def get_model_configuration(
    configuration_id: UUID, session: Session = Depends(get_session)
) -> ModelConfigurationResponse:
    configuration = get_or_404(session, ModelConfiguration, configuration_id, "model configuration")
    return _model_response(configuration)


@router.patch("/model-configurations/{configuration_id}", response_model=ModelConfigurationResponse)
def update_model_configuration(
    configuration_id: UUID,
    payload: ModelConfigurationUpdate,
    session: Session = Depends(get_session),
) -> ModelConfigurationResponse:
    configuration = get_or_404(session, ModelConfiguration, configuration_id, "model configuration")
    changes = payload.model_dump(exclude_unset=True)
    provider = changes.get("provider", configuration.provider)
    if provider not in available_provider_names():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unsupported provider: {provider}",
        )
    for field, value in changes.items():
        setattr(configuration, field, value)
    commit(session)
    session.refresh(configuration)
    return _model_response(configuration)


@router.delete("/model-configurations/{configuration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_configuration(
    configuration_id: UUID, session: Session = Depends(get_session)
) -> Response:
    configuration = get_or_404(session, ModelConfiguration, configuration_id, "model configuration")
    session.delete(configuration)
    commit(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/model-providers", response_model=list[ModelProviderResponse])
def list_model_providers() -> list[ModelProviderResponse]:
    import os

    return [
        ModelProviderResponse(name="fake", configured=True),
        ModelProviderResponse(name="openai", configured=bool(os.getenv("OPENAI_API_KEY"))),
    ]
