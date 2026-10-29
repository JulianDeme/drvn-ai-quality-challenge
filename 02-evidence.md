# Nightly Triage Agent — Evidence Analysis

**Document:** `02-evidence.md`  
**References:** `01-first-read.md`, `prompts/classify.md`, `fixtures/history/`  
**Scope:** 30 nightly regression runs, August 10 – September 18, 2026  

---

## Overview

The six-week investigation identified three observable reliability problems in the recorded Nightly Triage Agent outputs:

1. Missing failure classifications.
2. Systematic retry-based classification as `flaky`.
3. Inconsistent cluster sizes and Slack summary counts.

The first and third findings establish concrete output-integrity defects. The second establishes a systematic classification pattern that may lead to incorrect triage decisions, although its actual misclassification rate remains unverified.

The findings are based on comparisons between original Playwright failures and the recorded classifications, clusters, and Slack summaries.

---

## Investigation Methodology

All 30 JSON files were examined through programmatic analysis and targeted verification.

The investigation included:

1. Comparing `total_failures`, `failures_accounted_for`, `raw_failures`, and `classifications` to detect missing records.
2. Matching individual failures using the run date, `test_file`, and `test_title`.
3. Cross-referencing `retry_count`, `classification`, and `rationale` against original error messages.
4. Recalculating cluster sizes and Slack summary counts from individual classification records.
5. Examining cluster assignments for potentially unrelated failure signatures.

These checks addressed the three first-read hypotheses: retry-based misclassification (H1), clustering quality (H2), and system-level output integrity (H3).

The analysis distinguishes observable output defects from hypotheses about their underlying causes. The available fixtures do not provide independently verified root causes for every failure or complete downstream processing records.

### Dataset Summary

| Metric | Result |
|---|---:|
| Nightly runs | 30 |
| Raw failures | 595 |
| Classified failures | 571 |
| Unclassified failures | 24 |
| `real_bug` classifications | 65 |
| `environment` classifications | 254 |
| `flaky` classifications | 252 |

The three classification categories account for all 571 recorded classification entries.

---

## D1 — Missing Failures from Triage Output

**Area:** Output Completeness / System Integration  
**Related hypothesis:** H3 — Missing or Ineffective System-Level Output Validation.

### Defect

The recorded triage outputs do not consistently account for every original test failure, violating the reporting requirement that every failure must remain accounted for.

Across 30 runs, 595 raw failures were recorded, but only 571 received classifications.

**24 failures (4.03%) were omitted across seven runs.**

These omissions can be established directly by matching the original failure identities against the classification records.

### Evidence

| Run Date | Raw Failures | Classified | Missing |
|---|---:|---:|---:|
| 2026-08-11 | 11 | 7 | 4 |
| 2026-08-17 | 9 | 5 | 4 |
| 2026-08-26 | 7 | 5 | 2 |
| 2026-08-28 | 10 | 6 | 4 |
| 2026-09-01 | 31 | 27 | 4 |
| 2026-09-09 | 25 | 23 | 2 |
| 2026-09-16 | 35 | 31 | 4 |
| **Total** | **128** | **104** | **24** |

**Specific examples:**

- **2026-08-17:** `dispatch/notify.spec.ts` — `should send assignment SMS`. The raw failure reports HTTP 500 but has no corresponding classification.
- **2026-09-16:** `portal/login.spec.ts` — `should reject expired token`. The raw failure also reports HTTP 500 but is absent from `classifications`.

Both failures appear in `raw_failures`, but neither receives a classification or cluster assignment.

In the affected runs, the recorded Slack summaries describe the classified failures without explicitly warning that some original failures were omitted.

The available evidence establishes omissions in the recorded output. It does not identify which component caused them or confirm whether those summaries were ultimately delivered to Slack.

### Why It Matters — Cost to the Team

Engineers relying on these summaries could overlook failures entirely.

For example, the August 17 report excludes four recorded failures, including an HTTP 500 response. An engineer reviewing only that triage output would not receive a classification or diagnostic context for those failures.

This compromises regression visibility and creates a risk that potentially significant defects remain uninvestigated.

Unlike classification accuracy, output completeness can be verified deterministically without knowing the underlying cause of each Playwright failure.

**H3 Assessment:** The output-completeness defect is confirmed. The available data does not establish which component caused or accepted the omissions.

---

## D2 — Retry Count Used as Definitive Flaky Evidence

**Area:** Classification Logic  
**Related hypothesis:** H1 — Intermittent Application Defects Misclassified as Flaky.

### Defect

The recorded classifications show a systematic relationship between `retry_count` and the `flaky` label.

Every classified failure with `retry_count > 0` was labeled `flaky`, regardless of its original error signature.

The corresponding rationales also describe these failures as having passed on retry, although the raw failure records do not contain an explicit retry-result field.

**A retry attempt is not equivalent to a successful retry.** Even a confirmed successful retry would not, by itself, establish that the original failure was caused by test instability.

The observed behavior is consistent with the retry-based rule in the original prompt. However, the recorded outputs alone do not establish every internal decision made by the agent.

### Evidence

Across all 571 classified failures:

| `retry_count` | Total | Classified `flaky` |
|---|---:|---:|
| 0 | 319 | 0 |
| 1 | 179 | 179 |
| 2 | 73 | 73 |
| **Total** | **571** | **252** |

**All 252 classified failures with retries were labeled `flaky`.** No classified failure with `retry_count = 0` received that label.

Among these 252 classifications:

- **13** original failures contained HTTP 500 responses.
- **23** original failures contained `ERR_CONNECTION_REFUSED`.

These error signatures can indicate application or infrastructure problems. They do not independently establish the correct classification, but they demonstrate why retry count alone is an insufficient diagnostic criterion.

### Additional Evidence — Comparable Connectivity Failures, Different Classifications

In the September 18 run, two failures in the `Staging service unreachable` cluster reported `ERR_CONNECTION_REFUSED` against the same staging payments service.

| Test | Error / Target | Retry Count | Classification |
|---|---|---:|---|
| `booking/multileg.spec.ts` — `should price multi-leg itinerary 8` | `ERR_CONNECTION_REFUSED` — `staging-payments.moveo.internal` | 1 | `flaky` |
| `chauffeur/status.spec.ts` — `should update ride status` | `ERR_CONNECTION_REFUSED` — `staging-payments.moveo.internal` | 0 | `environment` |

Despite comparable connectivity errors affecting the same service, the failures received different classifications.

This reinforces the concern that retry count may be overriding diagnostic evidence. It does not establish that both failures share an identical root cause or prove that retry count was the sole internal decision factor.

### Specific Example — September 18, 2026

**Test:** `payment/checkout.spec.ts` — `should capture card payment`

| Field | Value |
|---|---|
| `error_message` | Expected HTTP 200, received HTTP 500 |
| `retry_count` | 1 |
| `classification` | `flaky` |
| `confidence` | 0.91 |
| `rationale` | "Passed on a retry, treated as intermittent." |

The raw failure record confirms an HTTP 500 response and one retry, but does not explicitly establish that the retry succeeded.

Furthermore, an intermittent HTTP 500 may reflect an application reliability problem rather than an unreliable automated test.

This example illustrates the risk of treating retry behavior as conclusive evidence instead of incorporating the original failure and additional diagnostic context.

### Why It Matters — Cost to the Team

Application defects and infrastructure incidents may be dismissed as test instability.

This is particularly concerning for critical flows such as payment processing, where intermittent server errors can represent genuine business risks.

If engineers systematically deprioritize failures labeled `flaky`, incorrectly classified defects may remain unresolved.

However, the 252 retry-associated classifications should **not** be interpreted as 252 confirmed misclassifications. Establishing the actual error rate would require independently verified outcomes.

**H1 Assessment:** The retry-driven classification pattern is confirmed. The number of genuinely incorrect classifications remains unknown.

---

## D3 — Inconsistent Cluster Sizes and Slack Summary

**Area:** Output Integrity / Reporting Validation  
**Related hypothesis:** H3 — Missing or Ineffective System-Level Output Validation.

### Defect

The September 18 recorded output contains contradictory failure counts within the same run.

The reported cluster sizes and Slack summary do not match the underlying classification records.

This violates the internal consistency expected from a structured report, independently of whether individual classifications are correct.

### Evidence

**Specific run: 2026-09-18**

| Field | Value |
|---|---:|
| `total_failures` | 27 |
| `failures_accounted_for` | 27 |
| `classifications.length` | 27 |
| Sum of `clusters[].size` | 26 |
| Slack failures explained | 26 |

The cluster `Assertion mismatches in booking flow` declares `size: 15`, but **16 classification entries** reference that cluster.

The Slack summary states:

`3 clusters. 5 real bug, 13 environment, 8 flaky. 26 failures explained.`

However, counting the classification entries produces:

| Classification | Slack Summary | Actual Records |
|---|---:|---:|
| `real_bug` | 5 | 5 |
| `environment` | 13 | 13 |
| `flaky` | 8 | 9 |
| **Total** | **26** | **27** |

The summary underreports both the flaky count and the number of classified failures by one.

Unlike D1, this run contains a classification entry for every original failure. The problem is **inconsistent aggregation and reporting**, not missing classification records.

### Why It Matters — Cost to the Team

Inconsistent reports undermine confidence in automated regression metrics and may cause engineers to investigate an inaccurate picture of nightly failures.

These discrepancies can be detected through deterministic checks:

- Cluster sizes must equal the number of classifications assigned to each cluster.
- Classification totals must reconcile with the underlying records.
- Slack summary counts must match the validated output.

None of these checks requires additional model inference.

The recorded inconsistency is confirmed. However, the available files do not establish whether a separate downstream validator existed or subsequently rejected the report.

**H3 Assessment:** The output inconsistency is confirmed. The presence, absence, or effectiveness of downstream validation cannot be established from the recorded artifacts alone.

---

## Additional H2 Evidence — Heterogeneous Failure Patterns Within a Cluster

In the September 3 run, the cluster `Server errors on write endpoints` grouped 26 failures, including:

| Test | Original Failure |
|---|---|
| `booking/multileg.spec.ts` — `should price multi-leg itinerary 1` | HTTP 500 response |
| `payment/checkout.spec.ts` — `should decline insufficient funds` | Detached DOM element during form fill |
| `booking/groups.spec.ts` — `should handle group booking case 2` | Assertion mismatch: expected `true`, received `false` |
| `booking/search.spec.ts` — `should handle no availability` | Timeout waiting for the Confirm button |

These failures have different diagnostic signatures, and the cluster name does not adequately describe all of them. In particular, a detached DOM element or locator timeout is not, by itself, evidence of a server error on a write endpoint.

This supports the concern that clustering may obscure meaningful diagnostic distinctions. However, the records do not establish independent root causes or prove that the three-cluster limit forced these failures together.

**H2 therefore remains inconclusive**, despite observable weaknesses in cluster specificity and diagnostic usefulness.

---

## First-Read Hypothesis Assessment

| Hypothesis | Investigation Result |
|---|---|
| **H1 — Retry-Based Misclassification** | **Supported at the behavioral level.** All 252 classified failures with retries were labeled `flaky`. Actual misclassification rates remain unverified. |
| **H2 — Forced Clustering** | **Inconclusive.** Heterogeneous error signatures appeared within clusters, but distinct root causes were not independently established. |
| **H3 — System-Level Output Validation** | **Supported at the output-integrity level.** Missing classifications and contradictory counts were demonstrated. The downstream validation architecture remains unknown. |

The evidence supports H1 and H3 without proving every proposed causal mechanism.

H2 remains a plausible risk, but the three-cluster constraint alone does not demonstrate incorrect clustering. Distinct symptoms may still share a root cause.

---

## Highest-Priority Defect

**D1 — Missing Failures from Triage Output**

D1 is the highest-priority finding because it directly compromises the completeness of the triage process.

Twenty-four recorded failures received no classification, including failures reporting HTTP 500 responses.

The impact is concrete and independently verifiable: original failures disappear from the classified output without explicit acknowledgment.

D2 presents a potentially broader classification risk because retry-based labeling affects 252 entries. However, the number of incorrect classifications cannot be established from the available evidence.

D3 demonstrates another important integrity failure, but the September 18 discrepancy involves reporting inconsistencies rather than omitted classification records.

**D1 therefore represents the clearest demonstrated threat to the team's ability to detect and investigate all recorded failures.**

---

## Conclusion

The investigation identified three significant reliability problems:

1. **Missing classifications:** 24 of 595 recorded failures were omitted from classification output across seven runs.
2. **Retry-driven classification:** All 252 classified failures with retries were labeled `flaky`, including failures containing HTTP 500 and connection-refused errors. The actual classification error rate remains unknown.
3. **Inconsistent reporting:** The September 18 output contained contradictory classification totals, cluster sizes, and Slack summary counts.

Together, these findings establish concrete reporting-integrity defects and a systematic classification behavior that creates risk for engineering triage.

The evidence does not establish the root cause of every failure, the exact internal mechanism behind each output defect, or the behavior of any unobserved downstream validation.

**The demonstrated reliability concerns are incomplete failure accounting, inconsistent reporting, and systematic reliance on retry behavior for classification.**