import {
  Alert,
  AppBar,
  Box,
  Card,
  CardContent,
  Chip,
  Container,
  Grid,
  LinearProgress,
  Stack,
  Toolbar,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { fetchHealth, fetchLifecycle, fetchMetrics } from "./api";

const workflowSteps = [
  "Upload datasets",
  "Version prompts",
  "Select adapters",
  "Run evaluations",
  "Compare results",
  "Gate CI",
];

function StatusChip({ value }: { value: string }) {
  const color = value === "completed" ? "success" : value === "failed" ? "error" : "default";
  return <Chip label={value} color={color} size="small" variant="outlined" />;
}

export function App() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });
  const lifecycleQuery = useQuery({ queryKey: ["lifecycle"], queryFn: fetchLifecycle });
  const metricsQuery = useQuery({ queryKey: ["metrics"], queryFn: fetchMetrics });

  const isLoading = healthQuery.isLoading || lifecycleQuery.isLoading || metricsQuery.isLoading;

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="static" color="primary" elevation={0}>
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            EvalForge
          </Typography>
          <Chip
            label={healthQuery.data?.status === "ok" ? "API live" : "API unknown"}
            color={healthQuery.data?.status === "ok" ? "success" : "warning"}
            size="small"
          />
        </Toolbar>
      </AppBar>

      {isLoading ? <LinearProgress /> : null}

      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Stack spacing={4}>
          <Box>
            <Typography variant="h4" component="h1" gutterBottom>
              Evaluation Control Plane
            </Typography>
            <Typography color="text.secondary" sx={{ maxWidth: 780 }}>
              Track dataset versions, prompt changes, provider adapters, metrics, and CI decisions
              from one place.
            </Typography>
          </Box>

          {healthQuery.isError ? (
            <Alert severity="warning">The frontend is running, but the API is not reachable.</Alert>
          ) : null}

          <Grid container spacing={2}>
            {workflowSteps.map((step) => (
              <Grid item xs={12} sm={6} md={4} key={step}>
                <Card>
                  <CardContent>
                    <Typography variant="overline" color="text.secondary">
                      Workflow
                    </Typography>
                    <Typography variant="h6">{step}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>
                Evaluation Lifecycle
              </Typography>
              <Stack direction="row" gap={1} flexWrap="wrap">
                {(lifecycleQuery.data?.evaluation_run_statuses ?? []).map((status) => (
                  <StatusChip key={status} value={status} />
                ))}
              </Stack>
            </Grid>

            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>
                Documented Metrics
              </Typography>
              <Stack spacing={1}>
                {(metricsQuery.data?.metrics ?? []).map((metric) => (
                  <Box key={metric.name}>
                    <Typography fontWeight={700}>{metric.display_name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {metric.semantics}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </Grid>
          </Grid>
        </Stack>
      </Container>
    </Box>
  );
}
