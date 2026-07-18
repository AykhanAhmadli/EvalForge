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
  direction: string;
  semantics: string;
}

export interface MetricsResponse {
  metrics: MetricDefinition[];
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`EvalForge API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health/live");
}

export function fetchLifecycle(): Promise<LifecycleResponse> {
  return getJson<LifecycleResponse>("/api/v1/lifecycle");
}

export function fetchMetrics(): Promise<MetricsResponse> {
  return getJson<MetricsResponse>("/api/v1/metrics");
}
