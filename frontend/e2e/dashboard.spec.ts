import { expect, test } from "@playwright/test";

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
  source_format: "jsonl",
  row_count: 2,
  schema_fields: ["question"],
  content_hash: "hash",
  created_by: "seed",
};
const promptVersion = {
  id: "prompt-version-1",
  prompt_template_id: "prompt-1",
  version_number: 1,
  template: "Answer {{ question }}",
  variables: ["question"],
  created_by: "seed",
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
  name: "Deterministic Fake",
  slug: "deterministic-fake",
  provider: "fake",
  model_name: "evalforge-fake-v1",
  temperature: 0,
  max_tokens: 256,
  timeout_seconds: 30,
  parameters: {},
};
const testCases = [
  {
    id: "case-1",
    dataset_version_id: version.id,
    row_number: 1,
    input: { question: "hello" },
    expected_output: "hello",
    metadata: {},
    tags: ["demo"],
  },
  {
    id: "case-2",
    dataset_version_id: version.id,
    row_number: 2,
    input: { question: "world" },
    expected_output: "world",
    metadata: {},
    tags: ["demo"],
  },
];
const runOne = {
  id: "run-1",
  workspace_id: workspace.id,
  suite_id: null,
  dataset_version_id: version.id,
  prompt_version_id: promptVersion.id,
  model_configuration_id: model.id,
  status: "completed",
  requested_by: null,
  failure_reason: null,
  queued_at: "2026-07-18T10:00:00Z",
  started_at: "2026-07-18T10:00:01Z",
  completed_at: "2026-07-18T10:00:02Z",
  cancelled_at: null,
  cancel_requested_at: null,
  total_cases: 2,
  completed_cases: 2,
  failed_cases: 0,
  metric_names: ["exact_match", "latency_ms"],
  aggregates: [
    {
      scope_type: "run",
      scope_key: "run-1",
      metric_name: "exact_match",
      value: 0.5,
      sample_count: 2,
      status: "valid",
      details: {},
    },
    {
      scope_type: "run",
      scope_key: "run-1",
      metric_name: "latency_ms",
      value: 4,
      sample_count: 2,
      status: "valid",
      details: {},
    },
  ],
};
const runTwo = {
  ...runOne,
  id: "run-2",
  status: "partially_failed",
  failed_cases: 1,
  completed_cases: 1,
  aggregates: [
    {
      scope_type: "run",
      scope_key: "run-2",
      metric_name: "exact_match",
      value: 0.25,
      sample_count: 1,
      status: "partial",
      details: {},
    },
    {
      scope_type: "run",
      scope_key: "run-2",
      metric_name: "latency_ms",
      value: 8,
      sample_count: 1,
      status: "valid",
      details: {},
    },
  ],
};

test("covers dataset, prompt, run, comparison, export, and regression workflows", async ({
  page,
}) => {
  let runs = [runOne, runTwo];
  let runPolls = 0;
  let baseline = null as {
    id: string;
    workspace_id: string;
    name: string;
    evaluation_run_id: string;
    rules: unknown[];
  } | null;
  await page.route("**/health/live", async (route) =>
    route.fulfill({ json: { status: "ok", service: "api" } }),
  );
  await page.route("**/api/v1/workspaces", async (route) => route.fulfill({ json: [workspace] }));
  await page.route("**/api/v1/workspaces/workspace-1/datasets", async (route) =>
    route.fulfill({ json: [dataset] }),
  );
  await page.route("**/api/v1/datasets/dataset-1/versions", async (route) =>
    route.fulfill({ json: [version] }),
  );
  await page.route("**/api/v1/dataset-versions/version-1/preview**", async (route) =>
    route.fulfill({ json: { version, test_cases: testCases } }),
  );
  await page.route("**/api/v1/datasets/dataset-1/versions/upload", async (route) =>
    route.fulfill({ status: 201, json: { ...version, version_number: 2, id: "version-2" } }),
  );
  await page.route("**/api/v1/workspaces/workspace-1/prompt-templates", async (route) =>
    route.fulfill({ json: [prompt] }),
  );
  await page.route("**/api/v1/prompt-templates/prompt-1", async (route) =>
    route.fulfill({ json: prompt }),
  );
  await page.route("**/api/v1/prompt-templates/prompt-1/versions", async (route) =>
    route.fulfill({
      status: 201,
      json: {
        ...promptVersion,
        id: "prompt-version-2",
        version_number: 2,
        template: "Answer carefully {{ question }}",
      },
    }),
  );
  await page.route("**/api/v1/workspaces/workspace-1/model-configurations", async (route) =>
    route.fulfill({ json: [model] }),
  );
  await page.route("**/api/v1/metrics", async (route) =>
    route.fulfill({
      json: {
        metrics: [
          {
            name: "exact_match",
            display_name: "Exact Match",
            direction: "higher_is_better",
            aggregation: "mean",
            semantics: "Equality",
          },
          {
            name: "latency_ms",
            display_name: "Latency",
            direction: "lower_is_better",
            aggregation: "mean",
            semantics: "Milliseconds",
          },
        ],
      },
    }),
  );
  await page.route("**/api/v1/workspaces/workspace-1/evaluation-runs", async (route) => {
    if (route.request().method() === "POST") {
      runs = [
        { ...runOne, id: "run-3", status: "queued", completed_cases: 0, failed_cases: 0 },
        ...runs,
      ];
      await route.fulfill({ status: 201, json: runs[0] });
    } else await route.fulfill({ json: runs });
  });
  await page.route("**/api/v1/evaluation-runs/run-3", async (route) => {
    runPolls += 1;
    await route.fulfill({
      json:
        runPolls < 2
          ? { ...runs[0], status: "running" }
          : { ...runs[0], status: "completed", completed_cases: 2 },
    });
  });
  await page.route("**/api/v1/evaluation-runs/*/results", async (route) =>
    route.fulfill({
      json: [
        {
          id: "result-1",
          run_id: "run-1",
          test_case_id: "case-1",
          output: { text: "hello" },
          status: "completed",
          latency_ms: 4,
          token_usage: { total_tokens: 3 },
          provider_trace_id: "fake",
          error_type: null,
          error_message: null,
          started_at: null,
          completed_at: null,
        },
        {
          id: "result-2",
          run_id: "run-1",
          test_case_id: "case-2",
          output: { text: "wrong" },
          status: "completed",
          latency_ms: 4,
          token_usage: { total_tokens: 3 },
          provider_trace_id: "fake",
          error_type: null,
          error_message: null,
          started_at: null,
          completed_at: null,
        },
      ],
    }),
  );
  await page.route("**/api/v1/evaluation-runs/*/metric-results", async (route) =>
    route.fulfill({
      json: [
        {
          id: "metric-1",
          run_id: "run-1",
          test_case_id: "case-1",
          metric_name: "exact_match",
          value: 1,
          status: "valid",
          details: {},
        },
        {
          id: "metric-2",
          run_id: "run-1",
          test_case_id: "case-2",
          metric_name: "exact_match",
          value: 0,
          status: "valid",
          details: {},
        },
      ],
    }),
  );
  await page.route("**/api/v1/workspaces/workspace-1/baselines", async (route) => {
    if (route.request().method() === "POST") {
      baseline = {
        id: "baseline-1",
        workspace_id: workspace.id,
        name: "Release baseline",
        evaluation_run_id: "run-1",
        rules: [],
      };
      await route.fulfill({ status: 201, json: baseline });
    } else await route.fulfill({ json: baseline ? [baseline] : [] });
  });
  await page.route("**/api/v1/baselines/baseline-1/rules", async (route) => {
    baseline = {
      ...baseline!,
      rules: [
        {
          id: "rule-1",
          baseline_id: "baseline-1",
          metric_name: "exact_match",
          operator: "<",
          threshold: 0.9,
        },
      ],
    };
    await route.fulfill({ status: 201, json: baseline.rules[0] });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.screenshot({ path: "../docs/screenshots/overview.png", fullPage: true });
  const navigation = page.locator('[aria-label="Primary navigation"]');

  await navigation.getByRole("button", { name: /Datasets/ }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "cases.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("input,expected_output\nhello,hello"),
  });
  await expect(page.getByText("Dataset management")).toBeVisible();

  await navigation.getByRole("button", { name: /Prompts/ }).click();
  await page.getByRole("button", { name: "Select prompt Answer" }).click();
  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible();
  await page.getByRole("textbox").last().fill("Answer carefully {{ question }}");
  await page.getByRole("button", { name: "Add version" }).click();

  await navigation.getByRole("button", { name: /Evaluation runs/ }).click();
  await page.getByRole("combobox", { name: "Dataset", exact: true }).click();
  await page.getByRole("option", { name: "Support set" }).click();
  await page.getByRole("combobox", { name: "Dataset version", exact: true }).click();
  await page.getByRole("option", { name: /v1/ }).click();
  await page.getByRole("combobox", { name: "Prompt", exact: true }).click();
  await page.getByRole("option", { name: "Answer" }).click();
  await page.getByRole("combobox", { name: "Prompt version", exact: true }).click();
  await page.getByRole("option", { name: /v1/ }).click();
  await page.getByRole("combobox", { name: "Model configuration", exact: true }).click();
  await page.getByRole("option", { name: /Deterministic Fake/ }).click();
  await page.getByRole("button", { name: "Run evaluation" }).click();
  await expect(page.getByText("running")).toBeVisible();

  await navigation.getByRole("button", { name: /Compare runs/ }).click();
  await page.getByLabel(/run-1/).check();
  await page.getByLabel(/run-2/).check();
  await expect(page.getByText("Overall score").first()).toBeVisible();
  await page.getByRole("button", { name: "Export CSV" }).click();
  await page.getByRole("button", { name: "Export JSON" }).click();
  await page.screenshot({ path: "../docs/screenshots/comparison.png", fullPage: true });

  await navigation.getByRole("button", { name: /Regression rules/ }).click();
  await page.getByLabel("Baseline name").fill("Release baseline");
  await page.getByLabel("Completed run").click();
  await page.getByRole("option", { name: /run-1/ }).click();
  await page.getByRole("button", { name: "Save baseline" }).click();
  await expect(page.getByText("Release baseline")).toBeVisible();
  await page.getByRole("button", { name: "Add rule" }).click();
  await expect(page.getByText("exact_match")).toBeVisible();
});
