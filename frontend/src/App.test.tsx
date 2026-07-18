import "@testing-library/jest-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, test, vi } from "vitest";

import * as api from "./api";
import { App } from "./App";
import { PromptsPage } from "./dashboard";

vi.mock("./api", () => ({
  fetchBaselines: vi.fn(),
  fetchDatasetPreview: vi.fn(),
  fetchDatasetVersions: vi.fn(),
  fetchDatasets: vi.fn(),
  fetchHealth: vi.fn(),
  fetchMetricResults: vi.fn(),
  fetchMetrics: vi.fn(),
  fetchModelConfigurations: vi.fn(),
  fetchPromptTemplate: vi.fn(),
  fetchPromptTemplates: vi.fn(),
  fetchRun: vi.fn(),
  fetchRunResults: vi.fn(),
  fetchRuns: vi.fn(),
  fetchSuites: vi.fn(),
  fetchWorkspaces: vi.fn(),
  createBaseline: vi.fn(),
  createDataset: vi.fn(),
  createModelConfiguration: vi.fn(),
  createPromptTemplate: vi.fn(),
  createPromptVersion: vi.fn(),
  createRegressionRule: vi.fn(),
  createRun: vi.fn(),
  createSuite: vi.fn(),
  uploadDatasetVersion: vi.fn(),
}));

const workspace = { id: "workspace-1", name: "Local Workspace", slug: "local", description: null };
const dataset = {
  id: "dataset-1",
  workspace_id: workspace.id,
  name: "Support set",
  slug: "support-set",
  description: null,
  tags: ["demo"],
};
const version = {
  id: "version-1",
  dataset_id: dataset.id,
  version_number: 1,
  source_format: "jsonl" as const,
  row_count: 2,
  schema_fields: ["question"],
  content_hash: "hash",
  created_by: "test",
};
const promptVersion = {
  id: "prompt-version-1",
  prompt_template_id: "prompt-1",
  version_number: 1,
  template: "Answer {{ question }}",
  variables: ["question"],
  created_by: "test",
};
const prompt = {
  id: "prompt-1",
  workspace_id: workspace.id,
  name: "Answer",
  slug: "answer",
  description: null,
  tags: [],
  versions: [promptVersion],
};
const model = {
  id: "model-1",
  workspace_id: workspace.id,
  name: "Fake",
  slug: "fake",
  provider: "fake",
  model_name: "evalforge-fake-v1",
  temperature: 0,
  max_tokens: 256,
  timeout_seconds: 30,
  parameters: {},
};

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

function renderPrompts() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <PromptsPage workspaceId={workspace.id} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.location.hash = "";
  vi.resetAllMocks();
  vi.mocked(api.fetchWorkspaces).mockResolvedValue([workspace]);
  vi.mocked(api.fetchHealth).mockResolvedValue({ status: "ok", service: "api" });
  vi.mocked(api.fetchRuns).mockResolvedValue([]);
  vi.mocked(api.fetchDatasets).mockResolvedValue([dataset]);
  vi.mocked(api.fetchDatasetVersions).mockResolvedValue([version]);
  vi.mocked(api.fetchDatasetPreview).mockResolvedValue({ version, test_cases: [] });
  vi.mocked(api.fetchPromptTemplates).mockResolvedValue([prompt]);
  vi.mocked(api.fetchPromptTemplate).mockResolvedValue(prompt);
  vi.mocked(api.fetchModelConfigurations).mockResolvedValue([model]);
  vi.mocked(api.fetchSuites).mockResolvedValue([]);
  vi.mocked(api.fetchMetrics).mockResolvedValue({
    metrics: [
      {
        name: "exact_match",
        display_name: "Exact Match",
        direction: "higher_is_better",
        aggregation: "mean",
        semantics: "Equality",
      },
    ],
  });
  vi.mocked(api.fetchBaselines).mockResolvedValue([]);
});

describe("EvalForge dashboard", () => {
  test("loads the seeded workspace overview", async () => {
    renderApp();
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByText("Local Workspace")).toBeInTheDocument();
    expect(screen.getByText("No evaluations yet")).toBeInTheDocument();
  });

  test("uploads a dataset version from the dataset page", async () => {
    vi.mocked(api.uploadDatasetVersion).mockResolvedValue(version);
    renderApp();
    fireEvent.click((await screen.findAllByRole("button", { name: /Datasets/ }))[0]);
    expect(await screen.findByRole("heading", { name: "Dataset management" })).toBeInTheDocument();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [new File(["input,expected_output\nhello,hi"], "cases.csv", { type: "text/csv" })],
      },
    });
    await waitFor(() =>
      expect(api.uploadDatasetVersion).toHaveBeenCalledWith(dataset.id, expect.any(File)),
    );
  });

  test("creates a prompt version and queues a run", async () => {
    vi.mocked(api.createPromptVersion).mockResolvedValue({
      ...promptVersion,
      id: "prompt-version-2",
      version_number: 2,
    });
    renderPrompts();
    fireEvent.click(await screen.findByRole("button", { name: "Select prompt Answer" }));
    await screen.findByRole("heading", { name: "Answer" });
    const editor = screen.getAllByRole("textbox").at(-1) as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: "Answer carefully {{ question }}" } });
    fireEvent.click(screen.getByRole("button", { name: "Add version" }));
    await waitFor(() =>
      expect(api.createPromptVersion).toHaveBeenCalledWith(
        prompt.id,
        "Answer carefully {{ question }}",
      ),
    );
  });
});
