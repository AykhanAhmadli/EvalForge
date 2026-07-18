const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  service: string;
  dependency?: string;
}

export interface LifecycleResponse {
  evaluation_run_statuses: string[];
}

export interface MetricDefinition {
  name: string;
  display_name: string;
  direction: "higher_is_better" | "lower_is_better";
  aggregation: "mean" | "sum";
  semantics: string;
}

export interface MetricsResponse {
  metrics: MetricDefinition[];
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description: string | null;
}

export interface EvaluationSuite {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
}

export interface Dataset {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  tags: string[];
}

export interface TestCase {
  id: string;
  dataset_version_id: string;
  row_number: number;
  input: unknown;
  expected_output: unknown;
  metadata: Record<string, unknown>;
  tags: string[];
}

export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version_number: number;
  source_format: "csv" | "jsonl" | "manual";
  row_count: number;
  schema_fields: string[];
  content_hash: string;
  created_by: string | null;
  test_cases?: TestCase[] | null;
}

export interface PromptVersion {
  id: string;
  prompt_template_id: string;
  version_number: number;
  template: string;
  variables: string[];
  created_by: string | null;
}

export interface PromptTemplate {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  tags: string[];
  versions?: PromptVersion[] | null;
}

export interface ModelConfiguration {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  provider: string;
  model_name: string;
  temperature: string | number;
  max_tokens: number;
  timeout_seconds: number;
  parameters: Record<string, unknown>;
}

export interface EvaluationAggregate {
  scope_type: string;
  scope_key: string;
  metric_name: string;
  value: string | number | null;
  sample_count: number;
  status: string;
  details: Record<string, unknown>;
}

export interface EvaluationRun {
  id: string;
  workspace_id: string;
  suite_id: string | null;
  dataset_version_id: string;
  prompt_version_id: string;
  model_configuration_id: string;
  status: string;
  requested_by: string | null;
  failure_reason: string | null;
  queued_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancel_requested_at: string | null;
  total_cases: number;
  completed_cases: number;
  failed_cases: number;
  metric_names: string[];
  aggregates: EvaluationAggregate[];
}

export interface EvaluationResult {
  id: string;
  run_id: string;
  test_case_id: string;
  output: Record<string, unknown>;
  status: string;
  latency_ms: number | null;
  token_usage: Record<string, number>;
  provider_trace_id: string | null;
  error_type: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface MetricResult {
  id: string;
  run_id: string;
  test_case_id: string | null;
  metric_name: string;
  value: string | number;
  status: string;
  details: Record<string, unknown>;
}

export interface RegressionRule {
  id: string;
  baseline_id: string;
  rule_type: string;
  metric_name: string | null;
  tag: string | null;
  operator: string;
  threshold: string | number;
}

export interface Baseline {
  id: string;
  workspace_id: string;
  name: string;
  evaluation_run_id: string;
  rules: RegressionRule[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    let message = `EvalForge API request failed: ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body.detail)
        message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // Keep the HTTP status when the API did not return JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health/live");
}

export function fetchLifecycle(): Promise<LifecycleResponse> {
  return request<LifecycleResponse>("/api/v1/lifecycle");
}

export function fetchMetrics(): Promise<MetricsResponse> {
  return request<MetricsResponse>("/api/v1/metrics");
}

export function fetchWorkspaces(): Promise<Workspace[]> {
  return request<Workspace[]>("/api/v1/workspaces");
}

export function fetchSuites(workspaceId: string): Promise<EvaluationSuite[]> {
  return request<EvaluationSuite[]>(`/api/v1/workspaces/${workspaceId}/suites`);
}

export function createSuite(
  workspaceId: string,
  body: { name: string; description?: string },
): Promise<EvaluationSuite> {
  return request<EvaluationSuite>(
    `/api/v1/workspaces/${workspaceId}/suites`,
    jsonInit("POST", body),
  );
}

export function fetchDatasets(workspaceId: string): Promise<Dataset[]> {
  return request<Dataset[]>(`/api/v1/workspaces/${workspaceId}/datasets`);
}

export function createDataset(
  workspaceId: string,
  body: { name: string; tags?: string[] },
): Promise<Dataset> {
  return request<Dataset>(`/api/v1/workspaces/${workspaceId}/datasets`, jsonInit("POST", body));
}

export function fetchDatasetVersions(datasetId: string): Promise<DatasetVersion[]> {
  return request<DatasetVersion[]>(`/api/v1/datasets/${datasetId}/versions`);
}

export function fetchDatasetPreview(
  versionId: string,
): Promise<{ version: DatasetVersion; test_cases: TestCase[] }> {
  return request(`/api/v1/dataset-versions/${versionId}/preview?limit=50`);
}

export function uploadDatasetVersion(datasetId: string, file: File): Promise<DatasetVersion> {
  const form = new FormData();
  form.append("file", file);
  return request<DatasetVersion>(`/api/v1/datasets/${datasetId}/versions/upload`, {
    method: "POST",
    body: form,
  });
}

export function fetchPromptTemplates(workspaceId: string): Promise<PromptTemplate[]> {
  return request<PromptTemplate[]>(`/api/v1/workspaces/${workspaceId}/prompt-templates`);
}

export function fetchPromptTemplate(templateId: string): Promise<PromptTemplate> {
  return request<PromptTemplate>(`/api/v1/prompt-templates/${templateId}`);
}

export function createPromptTemplate(
  workspaceId: string,
  body: { name: string; template: string },
): Promise<PromptTemplate> {
  return request<PromptTemplate>(
    `/api/v1/workspaces/${workspaceId}/prompt-templates`,
    jsonInit("POST", body),
  );
}

export function createPromptVersion(templateId: string, template: string): Promise<PromptVersion> {
  return request<PromptVersion>(
    `/api/v1/prompt-templates/${templateId}/versions`,
    jsonInit("POST", { template }),
  );
}

export function fetchModelConfigurations(workspaceId: string): Promise<ModelConfiguration[]> {
  return request<ModelConfiguration[]>(`/api/v1/workspaces/${workspaceId}/model-configurations`);
}

export function createModelConfiguration(
  workspaceId: string,
  body: Record<string, unknown>,
): Promise<ModelConfiguration> {
  return request<ModelConfiguration>(
    `/api/v1/workspaces/${workspaceId}/model-configurations`,
    jsonInit("POST", body),
  );
}

export function fetchRuns(workspaceId: string): Promise<EvaluationRun[]> {
  return request<EvaluationRun[]>(`/api/v1/workspaces/${workspaceId}/evaluation-runs`);
}

export function fetchRun(runId: string): Promise<EvaluationRun> {
  return request<EvaluationRun>(`/api/v1/evaluation-runs/${runId}`);
}

export function fetchRunResults(runId: string): Promise<EvaluationResult[]> {
  return request<EvaluationResult[]>(`/api/v1/evaluation-runs/${runId}/results`);
}

export function fetchMetricResults(runId: string): Promise<MetricResult[]> {
  return request<MetricResult[]>(`/api/v1/evaluation-runs/${runId}/metric-results`);
}

export function createRun(
  workspaceId: string,
  body: Record<string, unknown>,
): Promise<EvaluationRun> {
  return request<EvaluationRun>(
    `/api/v1/workspaces/${workspaceId}/evaluation-runs`,
    jsonInit("POST", body),
  );
}

export function cancelRun(runId: string): Promise<EvaluationRun> {
  return request<EvaluationRun>(`/api/v1/evaluation-runs/${runId}/cancel`, jsonInit("POST", {}));
}

export function fetchBaselines(workspaceId: string): Promise<Baseline[]> {
  return request<Baseline[]>(`/api/v1/workspaces/${workspaceId}/baselines`);
}

export function createBaseline(
  workspaceId: string,
  body: { name: string; evaluation_run_id: string },
): Promise<Baseline> {
  return request<Baseline>(`/api/v1/workspaces/${workspaceId}/baselines`, jsonInit("POST", body));
}

export function createRegressionRule(
  baselineId: string,
  body: {
    rule_type: string;
    metric_name?: string;
    tag?: string;
    operator: string;
    threshold: number;
  },
): Promise<RegressionRule> {
  return request<RegressionRule>(`/api/v1/baselines/${baselineId}/rules`, jsonInit("POST", body));
}

export function deleteRegressionRule(ruleId: string): Promise<void> {
  return request<void>(`/api/v1/regression-rules/${ruleId}`, { method: "DELETE" });
}

export function deleteBaseline(baselineId: string): Promise<void> {
  return request<void>(`/api/v1/baselines/${baselineId}`, { method: "DELETE" });
}
