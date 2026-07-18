import { ReactNode, useEffect, useMemo, useState } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  FormGroup,
  IconButton,
  InputLabel,
  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Toolbar,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createBaseline,
  createDataset,
  createModelConfiguration,
  createPromptTemplate,
  createPromptVersion,
  createRegressionRule,
  createRun,
  createSuite,
  cancelRun,
  EvaluationResult,
  EvaluationRun,
  fetchBaselines,
  fetchDatasetPreview,
  fetchDatasetVersions,
  fetchDatasets,
  fetchHealth,
  fetchMetricResults,
  fetchMetrics,
  fetchModelConfigurations,
  fetchPromptTemplate,
  fetchPromptTemplates,
  fetchRun,
  fetchRunResults,
  fetchRuns,
  fetchSuites,
  fetchWorkspaces,
  MetricDefinition,
  MetricResult,
  uploadDatasetVersion,
} from "./api";

type Page =
  "overview" | "suites" | "datasets" | "prompts" | "models" | "runs" | "compare" | "regressions";

const navItems: { key: Page; label: string; description: string }[] = [
  { key: "overview", label: "Overview", description: "Workspace health and recent activity" },
  { key: "suites", label: "Evaluation suites", description: "Organize repeatable checks" },
  { key: "datasets", label: "Datasets", description: "Upload and inspect immutable versions" },
  { key: "prompts", label: "Prompts", description: "Edit templates and version history" },
  { key: "models", label: "Model configurations", description: "Provider adapters and settings" },
  { key: "runs", label: "Evaluation runs", description: "Create, monitor, and inspect runs" },
  { key: "compare", label: "Compare runs", description: "Find quality and operational changes" },
  { key: "regressions", label: "Regression rules", description: "Baselines and CI thresholds" },
];

const terminalStatuses = new Set([
  "completed",
  "partially_failed",
  "failed",
  "cancelled",
  "canceled",
]);

const regressionRuleTypes = [
  ["minimum_overall_score", "Minimum overall score", ">="],
  ["maximum_score_decrease", "Maximum score decrease", "<="],
  ["maximum_failed_cases", "Maximum failed cases", "<="],
  ["maximum_p95_latency", "Maximum p95 latency", "<="],
  ["maximum_estimated_cost", "Maximum estimated cost", "<="],
  ["per_metric_threshold", "Per-metric threshold", ""],
] as const;

function safeText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined || value === null) return "Not available";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatMetric(value: string | number | null | undefined, suffix = ""): string {
  if (value === null || value === undefined) return "Not available";
  const number = Number(value);
  return Number.isFinite(number)
    ? `${number.toFixed(number < 1 ? 3 : 1)}${suffix}`
    : "Not available";
}

function statusColor(status: string): "default" | "success" | "warning" | "error" | "info" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "partially_failed") return "error";
  if (status === "cancelled" || status === "canceled") return "warning";
  if (status === "running") return "info";
  return "default";
}

function PageTitle({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      justifyContent="space-between"
      gap={2}
      sx={{ mb: 3 }}
    >
      <Box>
        <Typography variant="h4" component="h1" gutterBottom>
          {title}
        </Typography>
        <Typography color="text.secondary">{description}</Typography>
      </Box>
      {action}
    </Stack>
  );
}

function ErrorState({ message }: { message: string }) {
  return <Alert severity="error">{message}</Alert>;
}

function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
      <Typography variant="h6" gutterBottom>
        {title}
      </Typography>
      <Typography color="text.secondary" sx={{ mb: action ? 2 : 0 }}>
        {description}
      </Typography>
      {action}
    </Paper>
  );
}

function LoadingState() {
  return (
    <Stack alignItems="center" sx={{ py: 8 }}>
      <CircularProgress aria-label="Loading" />
    </Stack>
  );
}

function StatusChip({ status }: { status: string }) {
  return (
    <Chip
      label={status.replaceAll("_", " ")}
      color={statusColor(status)}
      size="small"
      variant="outlined"
    />
  );
}

function AppShell({
  page,
  setPage,
  children,
  workspaceName,
}: {
  page: Page;
  setPage: (page: Page) => void;
  children: ReactNode;
  workspaceName: string;
}) {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("md"));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawer = (
    <Box sx={{ width: 260, pt: 2 }}>
      <Box sx={{ px: 2.5, pb: 2 }}>
        <Typography variant="h6">EvalForge</Typography>
        <Typography variant="caption" color="text.secondary">
          {workspaceName}
        </Typography>
      </Box>
      <Divider />
      <List aria-label="Primary navigation" sx={{ px: 1, py: 1 }}>
        {navItems.map((item) => (
          <ListItemButton
            key={item.key}
            selected={page === item.key}
            onClick={() => {
              setPage(item.key);
              setDrawerOpen(false);
            }}
            sx={{ borderRadius: 1, mb: 0.5 }}
          >
            <ListItemText
              primary={item.label}
              secondary={item.description}
              primaryTypographyProps={{ fontWeight: 700 }}
            />
          </ListItemButton>
        ))}
      </List>
    </Box>
  );
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar
        position="fixed"
        color="inherit"
        elevation={0}
        sx={{ borderBottom: 1, borderColor: "divider", zIndex: theme.zIndex.drawer + 1 }}
      >
        <Toolbar>
          {mobile ? (
            <IconButton
              edge="start"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
            >
              <MenuIcon />
            </IconButton>
          ) : null}
          <Typography sx={{ flexGrow: 1, ml: mobile ? 1 : 0 }} fontWeight={800}>
            Evaluation workspace
          </Typography>
          <Chip label="API-backed" size="small" color="success" variant="outlined" />
        </Toolbar>
      </AppBar>
      {mobile ? (
        <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
          {drawer}
        </Drawer>
      ) : (
        <Drawer
          variant="permanent"
          sx={{
            width: 260,
            flexShrink: 0,
            [`& .MuiDrawer-paper`]: { width: 260, boxSizing: "border-box" },
          }}
        >
          {drawer}
        </Drawer>
      )}
      <Box component="main" sx={{ ml: mobile ? 0 : "260px", pt: 10, px: { xs: 2, md: 4 }, pb: 5 }}>
        {children}
      </Box>
    </Box>
  );
}

function OverviewPage({
  workspaceId,
  setPage,
}: {
  workspaceId: string;
  setPage: (page: Page) => void;
}) {
  const runs = useQuery({ queryKey: ["runs", workspaceId], queryFn: () => fetchRuns(workspaceId) });
  const datasets = useQuery({
    queryKey: ["datasets", workspaceId],
    queryFn: () => fetchDatasets(workspaceId),
  });
  const prompts = useQuery({
    queryKey: ["prompts", workspaceId],
    queryFn: () => fetchPromptTemplates(workspaceId),
  });
  const models = useQuery({
    queryKey: ["models", workspaceId],
    queryFn: () => fetchModelConfigurations(workspaceId),
  });
  if (runs.isLoading || datasets.isLoading || prompts.isLoading || models.isLoading)
    return <LoadingState />;
  if (runs.isError || datasets.isError || prompts.isError || models.isError)
    return <ErrorState message="Workspace data could not be loaded." />;
  const runItems = runs.data ?? [];
  return (
    <>
      <PageTitle
        title="Overview"
        description="A factual view of the local evaluation workspace."
        action={
          <Button variant="contained" onClick={() => setPage("runs")}>
            Create evaluation run
          </Button>
        }
      />
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" },
          gap: 2,
          mb: 4,
        }}
      >
        {[
          ["Datasets", datasets.data?.length ?? 0, "datasets"],
          ["Prompt templates", prompts.data?.length ?? 0, "prompts"],
          ["Model configurations", models.data?.length ?? 0, "models"],
          ["Evaluation runs", runItems.length, "runs"],
        ].map(([label, value, target]) => (
          <Card key={String(label)}>
            <CardContent>
              <Typography color="text.secondary" variant="body2">
                {label}
              </Typography>
              <Typography variant="h3" sx={{ mt: 1 }}>
                {value}
              </Typography>
              <Button size="small" onClick={() => setPage(target as Page)}>
                Open {String(label).toLowerCase()}
              </Button>
            </CardContent>
          </Card>
        ))}
      </Box>
      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="h6">Recent runs</Typography>
          <Button onClick={() => setPage("compare")}>Compare runs</Button>
        </Stack>
        {runItems.length === 0 ? (
          <EmptyState
            title="No evaluations yet"
            description="Create a run from a dataset version, prompt version, and model configuration."
          />
        ) : (
          <RunTable runs={runItems.slice(0, 6)} onSelect={() => setPage("runs")} />
        )}
      </Paper>
    </>
  );
}

function RunTable({
  runs,
  onSelect,
}: {
  runs: EvaluationRun[];
  onSelect: (run: EvaluationRun) => void;
}) {
  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Status</TableCell>
            <TableCell>Run</TableCell>
            <TableCell>Progress</TableCell>
            <TableCell>Created</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {runs.map((run) => (
            <TableRow key={run.id} hover onClick={() => onSelect(run)} sx={{ cursor: "pointer" }}>
              <TableCell>
                <StatusChip status={run.status} />
              </TableCell>
              <TableCell>
                <Typography fontFamily="monospace" fontSize="0.8rem">
                  {run.id.slice(0, 8)}
                </Typography>
              </TableCell>
              <TableCell>
                {run.completed_cases} / {run.total_cases} cases
                {run.failed_cases ? ` · ${run.failed_cases} failed` : ""}
              </TableCell>
              <TableCell>
                {run.queued_at ? new Date(run.queued_at).toLocaleString() : "Not available"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function SuitesPage({ workspaceId }: { workspaceId: string }) {
  const client = useQueryClient();
  const suites = useQuery({
    queryKey: ["suites", workspaceId],
    queryFn: () => fetchSuites(workspaceId),
  });
  const [name, setName] = useState("");
  const mutation = useMutation({
    mutationFn: () => createSuite(workspaceId, { name }),
    onSuccess: () => {
      setName("");
      void client.invalidateQueries({ queryKey: ["suites", workspaceId] });
    },
  });
  if (suites.isLoading) return <LoadingState />;
  if (suites.isError) return <ErrorState message="Evaluation suites could not be loaded." />;
  return (
    <>
      <PageTitle
        title="Evaluation suites"
        description="Keep related datasets, prompts, and runs together."
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
        <Stack
          component="form"
          direction={{ xs: "column", sm: "row" }}
          gap={2}
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) mutation.mutate();
          }}
        >
          <TextField
            label="Suite name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            size="small"
            required
            fullWidth
          />
          <Button type="submit" variant="contained" disabled={mutation.isPending}>
            {mutation.isPending ? "Creating..." : "Create suite"}
          </Button>
        </Stack>
      </Paper>
      {mutation.isError ? <ErrorState message={mutation.error.message} /> : null}
      {suites.data?.length ? (
        <Box
          sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}
        >
          {suites.data.map((suite) => (
            <Card key={suite.id}>
              <CardContent>
                <Typography variant="h6">{suite.name}</Typography>
                <Typography color="text.secondary">
                  {suite.description || "No description"}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {suite.slug}
                </Typography>
              </CardContent>
            </Card>
          ))}
        </Box>
      ) : (
        <EmptyState
          title="No suites"
          description="Create a suite to give a set of evaluations a name and home."
        />
      )}
    </>
  );
}

function DatasetsPage({ workspaceId }: { workspaceId: string }) {
  const client = useQueryClient();
  const datasets = useQuery({
    queryKey: ["datasets", workspaceId],
    queryFn: () => fetchDatasets(workspaceId),
  });
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [previewId, setPreviewId] = useState("");
  const versions = useQuery({
    queryKey: ["dataset-versions", selectedId],
    queryFn: () => fetchDatasetVersions(selectedId),
    enabled: Boolean(selectedId),
  });
  const preview = useQuery({
    queryKey: ["dataset-preview", previewId],
    queryFn: () => fetchDatasetPreview(previewId),
    enabled: Boolean(previewId),
  });
  const createMutation = useMutation({
    mutationFn: () => createDataset(workspaceId, { name }),
    onSuccess: () => {
      setName("");
      void client.invalidateQueries({ queryKey: ["datasets", workspaceId] });
    },
  });
  const uploadMutation = useMutation({
    mutationFn: ({ datasetId, file }: { datasetId: string; file: File }) =>
      uploadDatasetVersion(datasetId, file),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["dataset-versions", selectedId] });
    },
  });
  if (datasets.isLoading) return <LoadingState />;
  if (datasets.isError) return <ErrorState message="Datasets could not be loaded." />;
  return (
    <>
      <PageTitle
        title="Dataset management"
        description="Upload CSV or JSONL files and inspect immutable versions."
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
        <Stack
          component="form"
          direction={{ xs: "column", sm: "row" }}
          gap={2}
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) createMutation.mutate();
          }}
        >
          <TextField
            label="New dataset name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            size="small"
            required
            fullWidth
          />
          <Button type="submit" variant="contained" disabled={createMutation.isPending}>
            Create dataset
          </Button>
        </Stack>
      </Paper>
      {datasets.data?.length ? (
        <Stack spacing={2}>
          {datasets.data.map((dataset) => (
            <Card key={dataset.id} variant={selectedId === dataset.id ? undefined : "outlined"}>
              <CardContent>
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  justifyContent="space-between"
                  gap={2}
                >
                  <Box>
                    <Typography variant="h6">{dataset.name}</Typography>
                    <Typography color="text.secondary">
                      {dataset.description || "No description"}
                    </Typography>
                    <Stack direction="row" gap={1} sx={{ mt: 1 }} flexWrap="wrap">
                      {dataset.tags.map((tag) => (
                        <Chip key={tag} label={tag} size="small" />
                      ))}
                    </Stack>
                  </Box>
                  <Stack direction="row" gap={1} alignItems="center">
                    <Button
                      onClick={() => setSelectedId(selectedId === dataset.id ? "" : dataset.id)}
                    >
                      {selectedId === dataset.id ? "Hide versions" : "View versions"}
                    </Button>
                    <Button
                      component="label"
                      variant="outlined"
                      disabled={uploadMutation.isPending}
                    >
                      Upload CSV/JSONL
                      <input
                        hidden
                        type="file"
                        accept=".csv,.jsonl,application/json,text/csv"
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (file) uploadMutation.mutate({ datasetId: dataset.id, file });
                          event.target.value = "";
                        }}
                      />
                    </Button>
                  </Stack>
                </Stack>
                {selectedId === dataset.id ? (
                  <Box sx={{ mt: 2 }}>
                    <Divider sx={{ mb: 2 }} />
                    {versions.isLoading ? (
                      <LinearProgress />
                    ) : versions.isError ? (
                      <ErrorState message="Dataset versions could not be loaded." />
                    ) : versions.data?.length ? (
                      <TableContainer>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Version</TableCell>
                              <TableCell>Rows</TableCell>
                              <TableCell>Format</TableCell>
                              <TableCell />
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {versions.data.map((version) => (
                              <TableRow key={version.id}>
                                <TableCell>v{version.version_number}</TableCell>
                                <TableCell>{version.row_count}</TableCell>
                                <TableCell>{version.source_format}</TableCell>
                                <TableCell>
                                  <Button size="small" onClick={() => setPreviewId(version.id)}>
                                    Preview
                                  </Button>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography color="text.secondary">
                        No versions yet. Upload a file to create one.
                      </Typography>
                    )}
                  </Box>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </Stack>
      ) : (
        <EmptyState
          title="No datasets"
          description="Create a dataset, then upload a CSV or JSONL version."
        />
      )}
      {uploadMutation.isError ? (
        <Alert sx={{ mt: 2 }} severity="error">
          {uploadMutation.error.message}
        </Alert>
      ) : null}
      <Dialog open={Boolean(previewId)} onClose={() => setPreviewId("")} fullWidth maxWidth="md">
        <DialogTitle>Dataset preview</DialogTitle>
        <DialogContent>
          {preview.isLoading ? (
            <LoadingState />
          ) : preview.isError ? (
            <ErrorState message="Preview could not be loaded." />
          ) : (
            <Stack spacing={1}>
              {preview.data?.test_cases.map((testCase) => (
                <Paper variant="outlined" key={testCase.id} sx={{ p: 2 }}>
                  <Typography variant="caption" color="text.secondary">
                    Row {testCase.row_number}
                  </Typography>
                  <Typography
                    component="pre"
                    sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit" }}
                  >
                    Input: {safeText(testCase.input)}
                    {"\n"}Expected: {safeText(testCase.expected_output)}
                  </Typography>
                </Paper>
              ))}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewId("")}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export function PromptsPage({ workspaceId }: { workspaceId: string }) {
  const client = useQueryClient();
  const templates = useQuery({
    queryKey: ["prompts", workspaceId],
    queryFn: () => fetchPromptTemplates(workspaceId),
  });
  const [selectedId, setSelectedId] = useState("");
  const detail = useQuery({
    queryKey: ["prompt", selectedId],
    queryFn: () => fetchPromptTemplate(selectedId),
    enabled: Boolean(selectedId),
  });
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("Answer briefly: {{ question }}");
  const [newVersion, setNewVersion] = useState("");
  const createMutation = useMutation({
    mutationFn: () => createPromptTemplate(workspaceId, { name, template }),
    onSuccess: (created) => {
      setName("");
      setSelectedId(created.id);
      void client.invalidateQueries({ queryKey: ["prompts", workspaceId] });
    },
  });
  const versionMutation = useMutation({
    mutationFn: () => createPromptVersion(selectedId, newVersion),
    onSuccess: () => {
      setNewVersion("");
      void client.invalidateQueries({ queryKey: ["prompt", selectedId] });
    },
  });
  if (templates.isLoading) return <LoadingState />;
  if (templates.isError) return <ErrorState message="Prompt templates could not be loaded." />;
  return (
    <>
      <PageTitle
        title="Prompt editor"
        description="Create prompt templates and preserve every version for comparison."
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
        <Stack
          component="form"
          spacing={2}
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim() && template.trim()) createMutation.mutate();
          }}
        >
          <Stack direction={{ xs: "column", sm: "row" }} gap={2}>
            <TextField
              label="Template name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              fullWidth
            />
            <Button type="submit" variant="contained" disabled={createMutation.isPending}>
              Create template
            </Button>
          </Stack>
          <TextField
            label="Prompt template"
            value={template}
            onChange={(event) => setTemplate(event.target.value)}
            multiline
            minRows={3}
            fullWidth
            helperText="Use variables such as {{ question }}."
          />
        </Stack>
      </Paper>
      {templates.data?.length ? (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "280px 1fr" }, gap: 2 }}>
          <Paper variant="outlined">
            <List>
              {templates.data.map((item) => (
                <ListItemButton
                  key={item.id}
                  selected={selectedId === item.id}
                  onClick={() => setSelectedId(item.id)}
                  aria-label={`Select prompt ${item.name}`}
                >
                  <ListItemText primary={item.name} secondary={item.slug} />
                </ListItemButton>
              ))}
            </List>
          </Paper>
          <Paper variant="outlined" sx={{ p: 3 }}>
            {!selectedId ? (
              <EmptyState
                title="Select a prompt"
                description="Choose a template to inspect its editor and version history."
              />
            ) : detail.isLoading ? (
              <LoadingState />
            ) : detail.isError ? (
              <ErrorState message="Prompt details could not be loaded." />
            ) : (
              <Stack spacing={3}>
                <Box>
                  <Typography variant="h6">{detail.data?.name}</Typography>
                  <Typography color="text.secondary">
                    Variables are extracted and validated against dataset versions by the API.
                  </Typography>
                </Box>
                {detail.data?.versions?.map((version) => (
                  <Box key={version.id}>
                    <Stack direction="row" justifyContent="space-between">
                      <Typography fontWeight={700}>Version {version.version_number}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {version.variables.length ? version.variables.join(", ") : "No variables"}
                      </Typography>
                    </Stack>
                    <TextField
                      value={version.template}
                      fullWidth
                      multiline
                      minRows={3}
                      InputProps={{ readOnly: true }}
                      sx={{ mt: 1 }}
                    />
                  </Box>
                ))}
                <Divider />
                <Stack
                  component="form"
                  spacing={2}
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (newVersion.trim()) versionMutation.mutate();
                  }}
                >
                  <Typography variant="subtitle1" fontWeight={700}>
                    Create next version
                  </Typography>
                  <TextField
                    label="New prompt version"
                    value={newVersion}
                    onChange={(event) => setNewVersion(event.target.value)}
                    multiline
                    minRows={3}
                    required
                    fullWidth
                  />
                  <Button
                    type="submit"
                    variant="contained"
                    sx={{ alignSelf: "flex-start" }}
                    disabled={versionMutation.isPending}
                  >
                    Add version
                  </Button>
                </Stack>
              </Stack>
            )}
          </Paper>
        </Box>
      ) : (
        <EmptyState
          title="No prompt templates"
          description="Create a named prompt to start a version history."
        />
      )}
    </>
  );
}

function ModelsPage({ workspaceId }: { workspaceId: string }) {
  const client = useQueryClient();
  const models = useQuery({
    queryKey: ["models", workspaceId],
    queryFn: () => fetchModelConfigurations(workspaceId),
  });
  const [name, setName] = useState("");
  const [modelName, setModelName] = useState("evalforge-fake-v1");
  const [provider, setProvider] = useState("fake");
  const mutation = useMutation({
    mutationFn: () =>
      createModelConfiguration(workspaceId, {
        name,
        provider,
        model_name: modelName,
        temperature: 0,
        max_tokens: 256,
        timeout_seconds: 30,
        parameters: {},
      }),
    onSuccess: () => {
      setName("");
      void client.invalidateQueries({ queryKey: ["models", workspaceId] });
    },
  });
  if (models.isLoading) return <LoadingState />;
  if (models.isError) return <ErrorState message="Model configurations could not be loaded." />;
  return (
    <>
      <PageTitle
        title="Model configurations"
        description="Select provider adapters without exposing credentials in the browser."
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
        <Stack
          component="form"
          direction={{ xs: "column", sm: "row" }}
          gap={2}
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) mutation.mutate();
          }}
        >
          <TextField
            label="Configuration name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
          <FormControl sx={{ minWidth: 150 }}>
            <InputLabel id="provider-label">Provider</InputLabel>
            <Select
              labelId="provider-label"
              label="Provider"
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
            >
              <MenuItem value="fake">fake</MenuItem>
              <MenuItem value="openai">openai</MenuItem>
            </Select>
          </FormControl>
          <TextField
            label="Model name"
            value={modelName}
            onChange={(event) => setModelName(event.target.value)}
            required
            fullWidth
          />
          <Button type="submit" variant="contained">
            Add configuration
          </Button>
        </Stack>
      </Paper>
      {models.data?.length ? (
        <Box
          sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}
        >
          {models.data.map((model) => (
            <Card key={model.id}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="h6">{model.name}</Typography>
                  <Chip
                    label={model.provider}
                    size="small"
                    color={model.provider === "fake" ? "success" : "default"}
                  />
                </Stack>
                <Typography color="text.secondary">{model.model_name}</Typography>
                <Typography variant="body2" sx={{ mt: 2 }}>
                  Temperature {model.temperature} · Max tokens {model.max_tokens} · Timeout{" "}
                  {model.timeout_seconds}s
                </Typography>
              </CardContent>
            </Card>
          ))}
        </Box>
      ) : (
        <EmptyState
          title="No model configurations"
          description="Add the deterministic fake adapter for local demonstrations or configure an external adapter through environment variables."
        />
      )}
    </>
  );
}

function RunsPage({
  workspaceId,
  setPage,
}: {
  workspaceId: string;
  setPage: (page: Page) => void;
}) {
  const client = useQueryClient();
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: fetchMetrics });
  const runs = useQuery({ queryKey: ["runs", workspaceId], queryFn: () => fetchRuns(workspaceId) });
  const datasets = useQuery({
    queryKey: ["datasets", workspaceId],
    queryFn: () => fetchDatasets(workspaceId),
  });
  const prompts = useQuery({
    queryKey: ["prompts", workspaceId],
    queryFn: () => fetchPromptTemplates(workspaceId),
  });
  const models = useQuery({
    queryKey: ["models", workspaceId],
    queryFn: () => fetchModelConfigurations(workspaceId),
  });
  const [datasetId, setDatasetId] = useState("");
  const [promptId, setPromptId] = useState("");
  const [modelId, setModelId] = useState("");
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([
    "exact_match",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "estimated_cost",
  ]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const versions = useQuery({
    queryKey: ["dataset-versions", datasetId],
    queryFn: () => fetchDatasetVersions(datasetId),
    enabled: Boolean(datasetId),
  });
  const prompt = useQuery({
    queryKey: ["prompt", promptId],
    queryFn: () => fetchPromptTemplate(promptId),
    enabled: Boolean(promptId),
  });
  const [datasetVersionId, setDatasetVersionId] = useState("");
  const [promptVersionId, setPromptVersionId] = useState("");
  const createMutation = useMutation({
    mutationFn: () =>
      createRun(workspaceId, {
        dataset_version_id: datasetVersionId,
        prompt_version_id: promptVersionId,
        model_configuration_id: modelId,
        metrics: selectedMetrics,
      }),
    onSuccess: (created) => {
      setSelectedRunId(created.id);
      void client.invalidateQueries({ queryKey: ["runs", workspaceId] });
    },
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelRun(selectedRunId),
    onSuccess: (updated) => {
      client.setQueryData(["run", selectedRunId], updated);
      void client.invalidateQueries({ queryKey: ["runs", workspaceId] });
    },
  });
  const run = useQuery({
    queryKey: ["run", selectedRunId],
    queryFn: () => fetchRun(selectedRunId),
    enabled: Boolean(selectedRunId),
    refetchInterval: (query) => {
      const status = query.state.data?.status ?? runStatus(runs.data, selectedRunId);
      return selectedRunId && !terminalStatuses.has(status) ? 2000 : false;
    },
  });
  const results = useQuery({
    queryKey: ["run-results", selectedRunId],
    queryFn: () => fetchRunResults(selectedRunId),
    enabled: Boolean(selectedRunId),
    refetchInterval: selectedRunId && !terminalStatuses.has(run.data?.status ?? "") ? 2000 : false,
  });
  useEffect(() => {
    if (!run.data) return;
    client.setQueryData<EvaluationRun[]>(["runs", workspaceId], (current) =>
      current?.map((item) => (item.id === run.data.id ? run.data : item)),
    );
  }, [client, run.data, workspaceId]);
  if (
    metrics.isLoading ||
    runs.isLoading ||
    datasets.isLoading ||
    prompts.isLoading ||
    models.isLoading
  )
    return <LoadingState />;
  if (metrics.isError || runs.isError || datasets.isError || prompts.isError || models.isError)
    return <ErrorState message="Run setup data could not be loaded." />;
  const toggleMetric = (name: string) =>
    setSelectedMetrics((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    );
  return (
    <>
      <PageTitle
        title="Evaluation runs"
        description="Create a run from immutable inputs, then follow stored progress and results."
        action={<Button onClick={() => setPage("compare")}>Compare completed runs</Button>}
      />
      <Paper variant="outlined" sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Run creation
        </Typography>
        {datasets.data?.length && prompts.data?.length && models.data?.length ? (
          <Stack spacing={2}>
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" },
                gap: 2,
              }}
            >
              <FormControl fullWidth>
                <InputLabel id="run-dataset-label">Dataset</InputLabel>
                <Select
                  labelId="run-dataset-label"
                  label="Dataset"
                  value={datasetId}
                  onChange={(event) => {
                    setDatasetId(event.target.value);
                    setDatasetVersionId("");
                  }}
                >
                  {datasets.data.map((dataset) => (
                    <MenuItem key={dataset.id} value={dataset.id}>
                      {dataset.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel id="run-prompt-label">Prompt</InputLabel>
                <Select
                  labelId="run-prompt-label"
                  label="Prompt"
                  value={promptId}
                  onChange={(event) => {
                    setPromptId(event.target.value);
                    setPromptVersionId("");
                  }}
                >
                  {prompts.data.map((item) => (
                    <MenuItem key={item.id} value={item.id}>
                      {item.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel id="run-model-label">Model configuration</InputLabel>
                <Select
                  labelId="run-model-label"
                  label="Model configuration"
                  value={modelId}
                  onChange={(event) => setModelId(event.target.value)}
                >
                  {models.data.map((item) => (
                    <MenuItem key={item.id} value={item.id}>
                      {item.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" },
                gap: 2,
              }}
            >
              <FormControl fullWidth disabled={!datasetId}>
                <InputLabel id="run-version-label">Dataset version</InputLabel>
                <Select
                  labelId="run-version-label"
                  label="Dataset version"
                  value={datasetVersionId}
                  onChange={(event) => setDatasetVersionId(event.target.value)}
                >
                  {versions.data?.map((version) => (
                    <MenuItem key={version.id} value={version.id}>
                      v{version.version_number} · {version.row_count} rows
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl fullWidth disabled={!promptId}>
                <InputLabel id="run-prompt-version-label">Prompt version</InputLabel>
                <Select
                  labelId="run-prompt-version-label"
                  label="Prompt version"
                  value={promptVersionId}
                  onChange={(event) => setPromptVersionId(event.target.value)}
                >
                  {prompt.data?.versions?.map((version) => (
                    <MenuItem key={version.id} value={version.id}>
                      v{version.version_number} · {version.variables.join(", ") || "no variables"}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Metrics
              </Typography>
              <FormGroup row>
                {metrics.data?.metrics.map((metric) => (
                  <FormControlLabel
                    key={metric.name}
                    control={
                      <Checkbox
                        checked={selectedMetrics.includes(metric.name)}
                        onChange={() => toggleMetric(metric.name)}
                      />
                    }
                    label={metric.display_name}
                  />
                ))}
              </FormGroup>
            </Box>
            <Button
              variant="contained"
              onClick={() => createMutation.mutate()}
              disabled={
                createMutation.isPending ||
                !datasetVersionId ||
                !promptVersionId ||
                !modelId ||
                selectedMetrics.length === 0
              }
            >
              {createMutation.isPending ? "Queueing..." : "Run evaluation"}
            </Button>
            {createMutation.isError ? (
              <Alert severity="error">{createMutation.error.message}</Alert>
            ) : null}
          </Stack>
        ) : (
          <EmptyState
            title="Run setup is incomplete"
            description="Create at least one dataset, prompt template, and model configuration first."
            action={<Button onClick={() => setPage("datasets")}>Open setup</Button>}
          />
        )}
      </Paper>
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Run monitor
        </Typography>
        {runs.data?.length ? (
          <Stack spacing={1}>
            {runs.data.map((item) => (
              <Card
                key={item.id}
                variant={selectedRunId === item.id ? undefined : "outlined"}
                onClick={() => setSelectedRunId(item.id)}
                sx={{ cursor: "pointer" }}
              >
                <CardContent>
                  <Stack
                    direction={{ xs: "column", sm: "row" }}
                    justifyContent="space-between"
                    gap={1}
                  >
                    <Stack direction="row" gap={1} alignItems="center">
                      <StatusChip status={item.status} />
                      <Typography fontFamily="monospace" fontSize="0.85rem">
                        {item.id.slice(0, 12)}
                      </Typography>
                    </Stack>
                    <Typography>
                      {item.completed_cases} / {item.total_cases} cases
                      {item.failed_cases ? ` · ${item.failed_cases} failed` : ""}
                    </Typography>
                  </Stack>
                  {selectedRunId === item.id && item.status === "running" ? (
                    <LinearProgress sx={{ mt: 2 }} />
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </Stack>
        ) : (
          <EmptyState
            title="No runs"
            description="A queued run will appear here with live progress."
          />
        )}
      </Paper>
      {selectedRunId && run.isLoading ? <LoadingState /> : null}
      {selectedRunId && run.isError ? (
        <ErrorState message="The selected evaluation run could not be loaded." />
      ) : null}
      {selectedRunId && run.data ? (
        <RunDetail
          run={run.data}
          results={results.data ?? []}
          resultsError={results.isError}
          onCancel={
            run.data.status === "queued" || run.data.status === "running"
              ? () => cancelMutation.mutate()
              : undefined
          }
          cancelPending={cancelMutation.isPending}
        />
      ) : null}
    </>
  );
}

function runStatus(runs: EvaluationRun[] | undefined, id: string): string {
  return runs?.find((run) => run.id === id)?.status ?? "queued";
}

function RunDetail({
  run,
  results,
  resultsError,
  onCancel,
  cancelPending,
}: {
  run: EvaluationRun;
  results: EvaluationResult[];
  resultsError: boolean;
  onCancel?: () => void;
  cancelPending: boolean;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 3, mt: 3 }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        gap={2}
        sx={{ mb: 2 }}
      >
        <Box>
          <Typography variant="h6">Run {run.id.slice(0, 12)}</Typography>
          <Typography color="text.secondary">
            Stored provider output and case-level state.
          </Typography>
        </Box>
        <Stack direction="row" gap={1} alignItems="center">
          <StatusChip status={run.status} />
          {onCancel ? (
            <Button size="small" variant="outlined" onClick={onCancel} disabled={cancelPending}>
              {cancelPending ? "Cancelling..." : "Cancel run"}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      {run.failure_reason ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {run.failure_reason}
        </Alert>
      ) : null}
      {run.status === "running" || run.status === "queued" ? (
        <LinearProgress
          variant="determinate"
          value={run.total_cases ? (run.completed_cases / run.total_cases) * 100 : 0}
          sx={{ mb: 2 }}
        />
      ) : null}
      {resultsError ? (
        <ErrorState message="Case results could not be loaded." />
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Case</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Output</TableCell>
                <TableCell>Latency</TableCell>
                <TableCell>Tokens</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {results.length ? (
                results.map((result) => (
                  <TableRow key={result.id}>
                    <TableCell>{result.test_case_id.slice(0, 8)}</TableCell>
                    <TableCell>
                      <StatusChip status={result.status} />
                      {result.error_message ? (
                        <Typography variant="caption" display="block" color="error">
                          {result.error_message}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell
                      sx={{ maxWidth: 360, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                    >
                      {safeText(result.output?.text)}
                    </TableCell>
                    <TableCell>{formatMetric(result.latency_ms, " ms")}</TableCell>
                    <TableCell>{result.token_usage?.total_tokens ?? "Not available"}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5}>
                    <Typography color="text.secondary">
                      Results will appear after the worker stores the first case.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Paper>
  );
}

function ComparePage({ workspaceId }: { workspaceId: string }) {
  const runs = useQuery({ queryKey: ["runs", workspaceId], queryFn: () => fetchRuns(workspaceId) });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: fetchMetrics });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [tag, setTag] = useState("all");
  const [metric, setMetric] = useState("exact_match");
  const selectedRuns = useMemo(
    () =>
      selectedIds
        .map((id) => runs.data?.find((run) => run.id === id))
        .filter((run): run is EvaluationRun => Boolean(run)),
    [runs.data, selectedIds],
  );
  const resultQueries = useQueries({
    queries: selectedIds.map((id) => ({
      queryKey: ["compare-results", id],
      queryFn: () => fetchRunResults(id),
      enabled: Boolean(id),
    })),
  });
  const metricQueries = useQueries({
    queries: selectedIds.map((id) => ({
      queryKey: ["compare-metrics", id],
      queryFn: () => fetchMetricResults(id),
      enabled: Boolean(id),
    })),
  });
  const previewVersionIds = Array.from(new Set(selectedRuns.map((run) => run.dataset_version_id)));
  const previewQueries = useQueries({
    queries: previewVersionIds.map((versionId) => ({
      queryKey: ["compare-preview", versionId],
      queryFn: () => fetchDatasetPreview(versionId),
      enabled: Boolean(versionId),
    })),
  });
  const previewCasesByVersion = new Map(
    previewVersionIds.map((versionId, index) => [
      versionId,
      previewQueries[index]?.data?.test_cases ?? [],
    ]),
  );
  const rows = buildComparisonRows(
    selectedRuns,
    resultQueries.map((query) => query.data ?? []),
    metricQueries.map((query) => query.data ?? []),
    selectedRuns.map((run) => previewCasesByVersion.get(run.dataset_version_id) ?? []),
    tag,
    metric,
    metrics.data?.metrics ?? [],
  );
  const comparisonLoading =
    selectedIds.length >= 2 &&
    [...resultQueries, ...metricQueries, ...previewQueries].some((query) => query.isLoading);
  const comparisonError =
    selectedIds.length >= 2 &&
    [...resultQueries, ...metricQueries, ...previewQueries].some((query) => query.isError);
  if (runs.isLoading || metrics.isLoading) return <LoadingState />;
  if (runs.isError || metrics.isError)
    return <ErrorState message="Comparison data could not be loaded." />;
  const allTags = Array.from(
    new Set(
      Array.from(previewCasesByVersion.values()).flatMap((testCases) =>
        testCases.flatMap((item) => item.tags),
      ),
    ),
  ).sort();
  const exportData = (format: "csv" | "json") => {
    const payload = rows.map((row) => ({
      row: row.rowNumber,
      tags: row.tags,
      input: row.input,
      expected_output: row.expected,
      runs: row.runs,
    }));
    const body =
      format === "json"
        ? JSON.stringify(payload, null, 2)
        : [
            "row,tags,input,expected_output," +
              selectedRuns.map((run) => run.id.slice(0, 8)).join(","),
            ...payload.map((row) =>
              [
                row.row,
                row.tags.join("|"),
                safeText(row.input),
                safeText(row.expected_output),
                ...selectedRuns.map((run) => safeText(row.runs[run.id]?.output)),
              ]
                .map(csvEscape)
                .join(","),
            ),
          ].join("\n");
    const blob = new Blob([body], { type: format === "json" ? "application/json" : "text/csv" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `evalforge-comparison.${format}`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <PageTitle
        title="Compare runs"
        description="Compare stored outputs and metrics without generating substitute values."
      />
      <Paper variant="outlined" sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={700} gutterBottom>
          Select two or more runs
        </Typography>
        <FormGroup>
          {(runs.data ?? [])
            .filter((run) => terminalStatuses.has(run.status))
            .map((run) => (
              <FormControlLabel
                key={run.id}
                control={
                  <Checkbox
                    checked={selectedIds.includes(run.id)}
                    onChange={() =>
                      setSelectedIds((current) =>
                        current.includes(run.id)
                          ? current.filter((id) => id !== run.id)
                          : [...current, run.id],
                      )
                    }
                  />
                }
                label={
                  <Stack direction="row" gap={1} alignItems="center">
                    <Typography fontFamily="monospace">{run.id.slice(0, 12)}</Typography>
                    <StatusChip status={run.status} />
                  </Stack>
                }
              />
            ))}
        </FormGroup>
        {selectedIds.length < 2 ? (
          <Alert severity="info">Select at least two finished runs to compare.</Alert>
        ) : null}
      </Paper>
      {selectedIds.length >= 2 ? (
        <>
          <Stack direction={{ xs: "column", sm: "row" }} gap={2} sx={{ mb: 3 }}>
            <FormControl sx={{ minWidth: 180 }}>
              <InputLabel id="compare-metric-label">Case metric</InputLabel>
              <Select
                labelId="compare-metric-label"
                label="Case metric"
                value={metric}
                onChange={(event) => setMetric(event.target.value)}
              >
                {metrics.data?.metrics.map((item) => (
                  <MenuItem key={item.name} value={item.name}>
                    {item.display_name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl sx={{ minWidth: 160 }}>
              <InputLabel id="compare-tag-label">Tag filter</InputLabel>
              <Select
                labelId="compare-tag-label"
                label="Tag filter"
                value={tag}
                onChange={(event) => setTag(event.target.value)}
              >
                <MenuItem value="all">All tags</MenuItem>
                {allTags.map((item) => (
                  <MenuItem key={item} value={item}>
                    {item}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Button variant="outlined" onClick={() => exportData("csv")}>
              Export CSV
            </Button>
            <Button variant="outlined" onClick={() => exportData("json")}>
              Export JSON
            </Button>
          </Stack>
          {comparisonLoading ? <LinearProgress sx={{ mb: 3 }} /> : null}
          {comparisonError ? (
            <Alert severity="error" sx={{ mb: 3 }}>
              One or more selected run artifacts could not be loaded.
            </Alert>
          ) : null}
          {!comparisonLoading && !comparisonError ? (
            <>
              <ComparisonSummary
                runs={selectedRuns}
                metrics={metrics.data?.metrics ?? []}
                rows={rows}
              />
              <Paper variant="outlined" sx={{ mt: 3, p: 2 }}>
                <Typography variant="h6" sx={{ mb: 2 }}>
                  Case comparison
                </Typography>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Case</TableCell>
                        <TableCell>Input / expected</TableCell>
                        {selectedRuns.map((run) => (
                          <TableCell key={run.id}>Run {run.id.slice(0, 8)}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows.length ? (
                        rows.map((row) => (
                          <TableRow key={row.key}>
                            <TableCell>
                              {row.rowNumber}
                              <Typography variant="caption" display="block">
                                {row.tags.join(", ") || "untagged"}
                              </Typography>
                              <StatusChip status={row.classification} />
                            </TableCell>
                            <TableCell
                              sx={{
                                minWidth: 240,
                                whiteSpace: "pre-wrap",
                                overflowWrap: "anywhere",
                              }}
                            >
                              Input: {safeText(row.input)}
                              {"\n"}Expected: {safeText(row.expected)}
                            </TableCell>
                            {selectedRuns.map((run) => (
                              <TableCell
                                key={run.id}
                                sx={{
                                  minWidth: 260,
                                  whiteSpace: "pre-wrap",
                                  overflowWrap: "anywhere",
                                  verticalAlign: "top",
                                }}
                              >
                                {safeText(row.runs[run.id]?.output)}
                                {row.runs[run.id]?.error_message ? (
                                  <Typography variant="caption" color="error" display="block">
                                    {row.runs[run.id]?.error_message}
                                  </Typography>
                                ) : null}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))
                      ) : (
                        <TableRow>
                          <TableCell colSpan={selectedRuns.length + 2}>
                            <Typography color="text.secondary">
                              No cases match the current filters.
                            </Typography>
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Paper>
            </>
          ) : null}
        </>
      ) : null}
    </>
  );
}

function ComparisonSummary({
  runs,
  metrics,
  rows,
}: {
  runs: EvaluationRun[];
  metrics: MetricDefinition[];
  rows: ComparisonRow[];
}) {
  const quality = metrics.filter(
    (metric) =>
      metric.name !== "latency_ms" &&
      !metric.name.includes("tokens") &&
      metric.name !== "estimated_cost",
  );
  const operational = metrics.filter((metric) => !quality.includes(metric));
  const metricValue = (run: EvaluationRun, name: string) =>
    run.aggregates.find(
      (aggregate) => aggregate.scope_type === "run" && aggregate.metric_name === name,
    )?.value;
  const overallScore = (run: EvaluationRun) => {
    const values = quality
      .map((definition) => metricValue(run, definition.name))
      .filter((value): value is string | number => value !== null && value !== undefined);
    return values.length
      ? values.reduce((sum: number, value) => sum + Number(value), 0) / values.length
      : null;
  };
  const stat = (run: EvaluationRun, names: string[], suffix = "") => {
    const name = names.find(
      (candidate) =>
        metricValue(run, candidate) !== null && metricValue(run, candidate) !== undefined,
    );
    return name ? formatMetric(metricValue(run, name), suffix) : "Not available";
  };
  const section = (title: string, definitions: MetricDefinition[]) => (
    <Box>
      <Typography variant="overline" color="text.secondary">
        {title}
      </Typography>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Metric</TableCell>
              {runs.map((run) => (
                <TableCell key={run.id}>Run {run.id.slice(0, 8)}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {definitions.map((definition) => (
              <TableRow key={definition.name}>
                <TableCell>{definition.display_name}</TableCell>
                {runs.map((run) => (
                  <TableCell key={run.id}>
                    {stat(run, [definition.name], definition.name === "latency_ms" ? " ms" : "")}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
  return (
    <Stack spacing={3}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        {section("Quality metrics", quality)}
      </Paper>
      <Paper variant="outlined" sx={{ p: 2 }}>
        {section("Operational metrics", operational)}
      </Paper>
      <Box
        sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" }, gap: 2 }}
      >
        {runs.map((run) => (
          <Card key={run.id}>
            <CardContent>
              <Typography fontWeight={700}>Run {run.id.slice(0, 8)}</Typography>
              <Typography variant="body2" color="text.secondary">
                Overall score
              </Typography>
              <Typography variant="h5">{formatMetric(overallScore(run))}</Typography>
              <Typography variant="body2" color="text.secondary">
                Pass rate{" "}
                {formatMetric(
                  metricValue(run, "exact_match") === null ||
                    metricValue(run, "exact_match") === undefined
                    ? null
                    : Number(metricValue(run, "exact_match")) * 100,
                  "%",
                )}
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                Improved {rows.filter((row) => row.classification === "improved").length} ·
                Regressed {rows.filter((row) => row.classification === "regressed").length} · Failed{" "}
                {rows.filter((row) => row.classification === "failed").length}
              </Typography>
            </CardContent>
          </Card>
        ))}
      </Box>
    </Stack>
  );
}

type ComparisonRow = {
  key: string;
  rowNumber: number;
  tags: string[];
  input: unknown;
  expected: unknown;
  classification: string;
  runs: Record<
    string,
    { output: unknown; status: string; error_message: string | null; score?: number }
  >;
};

function buildComparisonRows(
  runs: EvaluationRun[],
  resultSets: EvaluationResult[][],
  metricSets: MetricResult[][],
  casesSets: {
    id: string;
    row_number: number;
    input: unknown;
    expected_output: unknown;
    tags: string[];
  }[][],
  tag: string,
  metric: string,
  metrics: MetricDefinition[],
): ComparisonRow[] {
  const byCase = new Map<string, ComparisonRow>();
  runs.forEach((run, index) => {
    const cases = casesSets[index] ?? [];
    const results = resultSets[index] ?? [];
    const metricResults = metricSets[index] ?? [];
    const resultByCase = new Map(results.map((result) => [result.test_case_id, result]));
    const metricByCase = new Map(
      metricResults
        .filter((result) => result.metric_name === metric)
        .map((result) => [result.test_case_id, result]),
    );
    cases.forEach((testCase) => {
      if (tag !== "all" && !testCase.tags.includes(tag)) return;
      const result = resultByCase.get(testCase.id);
      const metricResult = metricByCase.get(testCase.id);
      const existing = byCase.get(testCase.id) ?? {
        key: testCase.id,
        rowNumber: testCase.row_number,
        tags: testCase.tags,
        input: testCase.input,
        expected: testCase.expected_output,
        classification: "unchanged",
        runs: {},
      };
      existing.runs[run.id] = {
        output: result?.output?.text ?? "Not available",
        status: result?.status ?? "pending",
        error_message: result?.error_message ?? null,
        score:
          metricResult && metricResult.status === "valid" ? Number(metricResult.value) : undefined,
      };
      byCase.set(testCase.id, existing);
    });
  });
  const definition = metrics.find((item) => item.name === metric);
  const first = runs[0];
  return Array.from(byCase.values()).map((row) => {
    const base = row.runs[first?.id ?? ""];
    const candidate = runs.slice(1).map((run) => row.runs[run.id]);
    if (candidate.some((item) => item?.status === "failed")) row.classification = "failed";
    else if (
      base?.score !== undefined &&
      candidate.some((item) => item?.score !== undefined && item.score !== base.score)
    ) {
      const improved = candidate.some(
        (item) =>
          item?.score !== undefined &&
          (definition?.direction === "lower_is_better"
            ? item.score < base.score!
            : item.score > base.score!),
      );
      row.classification = improved ? "improved" : "regressed";
    }
    return row;
  });
}

function csvEscape(value: unknown): string {
  const text = String(value ?? "");
  const safeText = /^[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safeText.replaceAll('"', '""')}"`;
}

function RegressionPage({ workspaceId }: { workspaceId: string }) {
  const client = useQueryClient();
  const baselines = useQuery({
    queryKey: ["baselines", workspaceId],
    queryFn: () => fetchBaselines(workspaceId),
  });
  const runs = useQuery({ queryKey: ["runs", workspaceId], queryFn: () => fetchRuns(workspaceId) });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: fetchMetrics });
  const [name, setName] = useState("");
  const [runId, setRunId] = useState("");
  const [ruleType, setRuleType] = useState("per_metric_threshold");
  const [metric, setMetric] = useState("exact_match");
  const [operator, setOperator] = useState("<");
  const [threshold, setThreshold] = useState("0.9");
  const [tag, setTag] = useState("");
  const baselineMutation = useMutation({
    mutationFn: () => createBaseline(workspaceId, { name, evaluation_run_id: runId }),
    onSuccess: () => {
      setName("");
      void client.invalidateQueries({ queryKey: ["baselines", workspaceId] });
    },
  });
  const ruleMutation = useMutation({
    mutationFn: (targetBaselineId: string) =>
      createRegressionRule(targetBaselineId, {
        rule_type: ruleType,
        ...(ruleType === "per_metric_threshold" ? { metric_name: metric } : {}),
        ...(tag ? { tag } : {}),
        operator,
        threshold: Number(threshold),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["baselines", workspaceId] });
    },
  });
  if (baselines.isLoading || runs.isLoading || metrics.isLoading) return <LoadingState />;
  if (baselines.isError || runs.isError || metrics.isError)
    return <ErrorState message="Regression configuration could not be loaded." />;
  const finishedRuns = (runs.data ?? []).filter(
    (run) =>
      terminalStatuses.has(run.status) && run.status !== "failed" && run.status !== "cancelled",
  );
  return (
    <>
      <PageTitle
        title="Regression rules"
        description="Store baselines and thresholds against completed, API-backed runs."
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Create baseline
        </Typography>
        <Stack
          component="form"
          direction={{ xs: "column", sm: "row" }}
          gap={2}
          onSubmit={(event) => {
            event.preventDefault();
            if (name && runId) baselineMutation.mutate();
          }}
        >
          <TextField
            label="Baseline name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
          <FormControl fullWidth>
            <InputLabel id="baseline-run-label">Completed run</InputLabel>
            <Select
              labelId="baseline-run-label"
              label="Completed run"
              value={runId}
              onChange={(event) => setRunId(event.target.value)}
            >
              {finishedRuns.map((run) => (
                <MenuItem key={run.id} value={run.id}>
                  {run.id.slice(0, 12)} · {run.status}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button type="submit" variant="contained">
            Save baseline
          </Button>
        </Stack>
      </Paper>
      {baselines.data?.length ? (
        <Stack spacing={2}>
          {baselines.data.map((baseline) => (
            <Card key={baseline.id}>
              <CardContent>
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  justifyContent="space-between"
                  gap={2}
                >
                  <Box>
                    <Typography variant="h6">{baseline.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Run {baseline.evaluation_run_id.slice(0, 12)}
                    </Typography>
                  </Box>
                  <Chip label={`${baseline.rules.length} rules`} />
                </Stack>
                {baseline.rules.length ? (
                  <Table size="small" sx={{ mt: 2 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Metric</TableCell>
                        <TableCell>Condition</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {baseline.rules.map((rule) => (
                        <TableRow key={rule.id}>
                          <TableCell>
                            {rule.rule_type}
                            {rule.metric_name ? `: ${rule.metric_name}` : ""}
                            {rule.tag ? ` (${rule.tag})` : ""}
                          </TableCell>
                          <TableCell>
                            {rule.operator} {rule.threshold}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <Typography color="text.secondary" sx={{ mt: 2 }}>
                    No rules on this baseline.
                  </Typography>
                )}
                <Stack
                  component="form"
                  direction={{ xs: "column", sm: "row" }}
                  gap={1}
                  sx={{ mt: 2 }}
                  onSubmit={(event) => {
                    event.preventDefault();
                    ruleMutation.mutate(baseline.id);
                  }}
                >
                  <FormControl size="small" sx={{ minWidth: 220 }}>
                    <InputLabel id={`rule-type-${baseline.id}`}>Rule type</InputLabel>
                    <Select
                      labelId={`rule-type-${baseline.id}`}
                      label="Rule type"
                      value={ruleType}
                      onChange={(event) => {
                        const next = event.target.value;
                        setRuleType(next);
                        const definition = regressionRuleTypes.find(([type]) => type === next);
                        if (definition?.[2]) setOperator(definition[2]);
                      }}
                    >
                      {regressionRuleTypes.map(([type, label]) => (
                        <MenuItem key={type} value={type}>
                          {label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  {ruleType === "per_metric_threshold" ? (
                    <FormControl size="small" sx={{ minWidth: 180 }}>
                      <InputLabel id={`rule-metric-${baseline.id}`}>Metric</InputLabel>
                      <Select
                        labelId={`rule-metric-${baseline.id}`}
                        label="Metric"
                        value={metric}
                        onChange={(event) => setMetric(event.target.value)}
                      >
                        {metrics.data?.metrics.map((item) => (
                          <MenuItem key={item.name} value={item.name}>
                            {item.display_name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  ) : null}
                  <FormControl size="small" sx={{ minWidth: 100 }}>
                    <InputLabel id={`rule-operator-${baseline.id}`}>Rule</InputLabel>
                    <Select
                      labelId={`rule-operator-${baseline.id}`}
                      label="Rule"
                      value={operator}
                      onChange={(event) => setOperator(event.target.value)}
                      disabled={ruleType !== "per_metric_threshold"}
                    >
                      <MenuItem value="<">&lt;</MenuItem>
                      <MenuItem value="<=">&lt;=</MenuItem>
                      <MenuItem value=">">&gt;</MenuItem>
                      <MenuItem value=">=">&gt;=</MenuItem>
                      <MenuItem value="=">=</MenuItem>
                    </Select>
                  </FormControl>
                  <TextField
                    size="small"
                    label="Tag (optional)"
                    value={tag}
                    onChange={(event) => setTag(event.target.value)}
                  />
                  <TextField
                    size="small"
                    label="Threshold"
                    type="number"
                    value={threshold}
                    onChange={(event) => setThreshold(event.target.value)}
                  />
                  <Button type="submit" variant="outlined">
                    Add rule
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Stack>
      ) : (
        <EmptyState
          title="No baselines"
          description="Finish a run, then save it here as the comparison point for regression rules."
        />
      )}
    </>
  );
}

export function Dashboard({
  workspaceId,
  page,
  setPage,
}: {
  workspaceId: string;
  page: Page;
  setPage: (page: Page) => void;
}) {
  const navigate = (next: Page) => {
    setPage(next);
    window.history.replaceState(null, "", `#${next}`);
  };
  const content =
    page === "overview" ? (
      <OverviewPage workspaceId={workspaceId} setPage={navigate} />
    ) : page === "suites" ? (
      <SuitesPage workspaceId={workspaceId} />
    ) : page === "datasets" ? (
      <DatasetsPage workspaceId={workspaceId} />
    ) : page === "prompts" ? (
      <PromptsPage workspaceId={workspaceId} />
    ) : page === "models" ? (
      <ModelsPage workspaceId={workspaceId} />
    ) : page === "runs" ? (
      <RunsPage workspaceId={workspaceId} setPage={navigate} />
    ) : page === "compare" ? (
      <ComparePage workspaceId={workspaceId} />
    ) : (
      <RegressionPage workspaceId={workspaceId} />
    );
  return <>{content}</>;
}

export function DashboardRoot() {
  const workspace = useQuery({ queryKey: ["workspaces"], queryFn: fetchWorkspaces });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30000,
  });
  const [page, setPage] = useState<Page>((window.location.hash.slice(1) as Page) || "overview");
  if (workspace.isLoading) return <LoadingState />;
  if (workspace.isError || !workspace.data?.[0])
    return (
      <Box sx={{ p: 4 }}>
        <ErrorState message="The local workspace could not be loaded. Check that the API is running." />
      </Box>
    );
  const navigate = (next: Page) => {
    setPage(next);
    window.history.replaceState(null, "", `#${next}`);
  };
  return (
    <Box>
      <AppShell page={page} setPage={navigate} workspaceName={workspace.data[0].name}>
        <Dashboard workspaceId={workspace.data[0].id} page={page} setPage={navigate} />
      </AppShell>
      <Snackbar
        open={Boolean(health.isError)}
        autoHideDuration={3000}
        message="The API is not reachable"
      />
    </Box>
  );
}
