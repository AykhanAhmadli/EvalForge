# Regression Rules

Regression rules are gates over stored baseline and candidate run artifacts. They are not
claims about a model in general: an evaluation dataset, prompt version, model configuration,
metric definition, and provider response all constrain what a rule says.

## Rule Types

| Rule type | Candidate value | Required operator | Tag behavior |
| --- | --- | --- | --- |
| `minimum_overall_score` | Mean of valid quality metrics requested by the run | `>=` | Scores only rows carrying the tag |
| `maximum_score_decrease` | `max(0, baseline overall - candidate overall)` | `<=` | Computes both scores on tagged rows |
| `maximum_failed_cases` | Count of failed or cancelled cases | `<=` | Counts only failed tagged rows |
| `maximum_p95_latency` | Nearest-rank 95th percentile of valid latency samples | `<=` | Uses tagged rows |
| `maximum_estimated_cost` | Sum of valid estimated-cost samples | `<=` | Sums tagged rows |
| `per_metric_threshold` | Mean or sum according to the metric definition | Configurable | Uses tagged rows |

`tag` is optional. Without it, the rule uses all rows. A tag that selects no stored rows makes the
rule `not_evaluable`; the gate fails closed instead of treating missing evidence as a pass.

Overall score excludes operational metrics such as latency, token counts, and estimated cost. It
averages valid higher-is-better metrics requested by the run. A metric with invalid inputs does
not contribute a value and is preserved as invalid in the run artifacts.

Baseline and candidate runs must be completed. Cancelled, failed, queued, running, and partially
failed candidates are not comparable and produce a non-passing result. A CI job that times out
before the API reports a terminal state is also non-passing.

## Interpretation

A passing rule means only that this recorded candidate stayed within the configured boundary for
this dataset and configuration. Evaluation metrics are imperfect proxies rather than absolute
measures of model quality. Keep datasets representative, review changes to prompts and metrics,
and use human or domain review for decisions that need more evidence than an automated gate can
provide.

The API evaluates rules with `POST /api/v1/baselines/{baseline_id}/compare?candidate_run_id=...`.
The response includes the status, every violation, the baseline and candidate values, the
threshold, and the tag scope used for each rule.
