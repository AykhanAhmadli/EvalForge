# Metric Semantics

Every metric used by EvalForge must have documented semantics before it can be attached to an evaluation run.

## exact_match

- Direction: higher is better.
- Value range: `0.0` or `1.0` for item-level results; aggregate value is the arithmetic mean across evaluated rows.
- Semantics: returns `1.0` when the normalized model output is exactly equal to the normalized expected output, otherwise `0.0`.
- Normalization: trim leading and trailing whitespace and convert consecutive internal whitespace to a single space.
- Intended use: deterministic regression checks for tasks with canonical answers.

## contains_expected

- Direction: higher is better.
- Value range: `0.0` or `1.0` for item-level results; aggregate value is the arithmetic mean across evaluated rows.
- Semantics: returns `1.0` when the normalized expected output appears as a case-insensitive substring of the normalized model output, otherwise `0.0`.
- Normalization: trim leading and trailing whitespace and convert consecutive internal whitespace to a single space.
- Intended use: deterministic checks for generated answers where the expected answer may be embedded in a longer response.

## Adding Metrics

New metrics must define:

- Name and stable identifier.
- Directionality.
- Item-level and aggregate value ranges.
- Normalization behavior.
- Failure behavior when inputs are missing or malformed.
- Known limitations.
