# Metric Semantics

Metric implementations live in `backend/src/evalforge/metrics.py`. Every result stores a
normalized value, a `valid` or `invalid` status, and raw details including the expected and
actual values. Invalid inputs are not silently treated as a passing or failing model answer.

| Metric | Definition | Aggregation |
| --- | --- | --- |
| `exact_match` | Trim whitespace, collapse internal whitespace, and compare values exactly. | Mean |
| `case_insensitive_exact_match` | Exact match after the same normalization and Unicode case folding. | Mean |
| `contains` | Case-insensitive substring search after normalization. | Mean |
| `regex_match` | Full-match the configured `pattern`, or the expected value when no pattern is supplied. Invalid regular expressions are invalid results. | Mean |
| `json_schema_validity` | Parse the output as JSON and validate it against the configured Draft 2020-12 schema. Missing or malformed schemas are invalid results. | Mean |
| `numeric_tolerance` | Compare numeric values using `tolerance`. Values within tolerance score `1.0`; values outside tolerance receive a bounded linear penalty and reach `0.0` at twice the tolerance. Non-numeric inputs are invalid. | Mean |
| `semantic_similarity` | Cosine similarity from the deterministic local `local-hash-embedding-v1` hashing proxy, normalized to `[0, 1]`. This is not a trained language embedding model and should not be presented as semantic understanding. Empty text is invalid. | Mean |
| `latency_ms` | Adapter-reported provider latency in milliseconds. Missing or negative values are invalid. | Mean |
| `input_tokens` | Provider-reported prompt token count. Missing or negative values are invalid. | Sum |
| `output_tokens` | Provider-reported completion token count. Missing or negative values are invalid. | Sum |
| `estimated_cost` | Input and output tokens multiplied by the effective editable pricing row, divided by 1,000. The currency and effective date are retained in raw details. Missing pricing is invalid. | Sum |

Run aggregates are materialized for the complete run, dataset, each test-case tag, prompt
version, and model configuration. Mean metrics average valid item results; sum metrics add
valid item results. An aggregate is `partial` when some item results are invalid and `invalid`
when none are valid.

Pricing is configuration, not a permanent provider fact. Rows are selected by workspace,
provider, model, and effective date. Update pricing through the provider-pricing API when the
account's rate changes.

The hashing proxy is intentionally dependency-free and reproducible for local tests. It is useful
as a stable demonstration metric, but quality-sensitive deployments should add a validated local
embedding backend before treating semantic similarity as evidence of meaning preservation.
