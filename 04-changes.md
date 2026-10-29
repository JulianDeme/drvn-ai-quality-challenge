# 04 — Rebuild: Changes and Failure-Handling Policy

**Document:** `04-changes.md`  
**References:** `02-evidence.md`, `triage/prompt.py` (v1.3), `starter/`  
**Scope:** Agent rebuild, prompt changes, validation, error handling, and unit tests. `starter/` unchanged; Slack output printed, never posted.  

---

## Evidence from §2

| ID | Observed defect | What the evidence does **not** establish |
|---|---|---|
| **E1 — Missing coverage** | 24 of 595 input failures had no corresponding classification in the historical output. | It does not identify whether bad JSON, dropped model items, tool failures, or another mechanism caused those omissions. |
| **E2 — Retry-driven labeling** | All **252/252** failures with a retry were classified as `flaky`. | It establishes a systematic association, **not** that all 252 labels were incorrect. |
| **E3 — Internal inconsistency** | On `2026-09-18`, the source had 27 failures and 27 classification records, but reported cluster sizes totaled 26; Slack said 26 accounted for and 8 flaky, while 9 classification records were `flaky`. | It does not establish that the number of clusters, prompt length, model version, or transient errors caused the discrepancy. |

## Changes directly addressing the observed defects

Each table row is one prompt/code change and identifies the §2 observation it addresses. This section claims improvements in **coverage, traceability, and reporting consistency**, not independently verified classification accuracy.

| Change (prompt or code) | Defect from §2 addressed | Decision / expected effect |
|---|---|---|
| **Prompt — Evidence over retry success:** remove the rule treating a successful retry as proof of `flaky` (`triage/prompt.py`). | **E2:** 252/252 retried failures were labeled `flaky`. | Require classification from failure evidence, not from retry status alone. |
| **Prompt — Request history where useful:** explicitly instruct the model to use `get_test_history` when more evidence is needed (`triage/prompt.py`). | **E2:** labels were systematically associated with retry status. | Consult prior-night failures without claiming historical recurrence proves a ground-truth label. |
| **Prompt — Complete, exact identity coverage:** request no omitted, invented, or duplicate failures (`triage/prompt.py`). | **E1:** 24 input failures were absent from classifications. | Establish the expected input/output contract; enforce it independently in code. |
| **Prompt — Explicit abstention:** allow `unclassified` with rationale when evidence is insufficient (`triage/prompt.py`). | **E1:** unresolved input cases were not explicitly represented. | Distinguish a declared lack of evidence from silently dropping a test. This does **not** prove the historical omissions were due to insufficient evidence. |
| **Code — Validate input identities and metadata:** load `raw_failures`, enforce unique nonempty test identities, and reject malformed required fields before invoking the model (`triage/__main__.py`, `triage/agent.py`). | **E1:** omitted failures relative to input. | **Fail loudly** for invalid source input, including a non-string or empty `error_message` and a `retry_count` that is not a nonnegative integer; never silently shrink the input set. The specific malformed-field cases were not observed in §2. |
| **Code — Per-item validation and selective retries:** match classifications to input test IDs, validate each usable item, preserve accepted items, and retry only the unresolved subset (`triage/validation.py`, `triage/agent.py`). | **E1:** 24 absent classifications. | **Retry** missing/invalid items without discarding independently validated records. |
| **Code — Execute history requests:** offer and execute `get_test_history` using the fake provider's tool-call contract (`triage/agent.py`). | **E2:** retry-only evidence is insufficient to justify `flaky`. | Supply requested historical context; do not infer ground-truth accuracy from its use. |
| **Code — Separate unresolved reasons:** record `retry_exhausted` (agent-assigned) and `insufficient_evidence` (model-declared), with the original test identity (`triage/agent.py`, `triage/report.py`). | **E1:** missing cases were not accounted for explicitly. | **Require manual review** for unresolved cases; do not count either category as classified. |
| **Code — Reconcile input to output:** verify that every input test ID appears exactly once as either classified or explicitly unresolved; reject mismatched declared totals (`triage/report.py`). | **E1 + E3:** omissions and conflicting totals. | **Fail loudly** if the report itself loses, duplicates, or invents records. |
| **Code — Derive aggregates from validated classifications:** recompute classification and cluster totals rather than trusting model-supplied cluster sizes (`triage/report.py`). | **E3:** model/report clusters totaled 26 while there were 27 classification records. | Reconcile counts with actually validated classifications. |
| **Code — Generate Slack from the same report:** build the preview from validated counts and the explicit unresolved breakdown (`triage/report.py`, `triage/__main__.py`). | **E1 + E3:** historical Slack reported 26 accounted for and 8 flaky despite 27 classifications and 9 flaky entries. | Never claim more classified failures than validated; print only. |
| **Code — Signal incomplete triage to automation:** after printing a `needs_review` JSON report and Slack preview, exit with **code 2** (`triage/__main__.py`). | **E1 + E3:** incomplete/misleading completion accounting. | Keep unresolved items visible while preventing downstream automation from treating the run as fully complete. This is an operational safeguard, not a proven historical root-cause fix. |
| **Tests — Regression coverage:** test identity checks, malformed input fields, missing items, retries, abstention, tool-call ID reuse, aggregates, Slack, and CLI exit code (`tests/test_triage.py`). | **E1–E3:** the observed coverage, retry-labeling, and reporting discrepancies must not silently recur. | Verify deterministic properties around the unreliable model, including three additional boundary tests for input types and repeated tool-call IDs. |

## Additional §4 safeguards (preventive; not claimed as proven §2 root-cause fixes)

These are real changes required to make the agent dependable, but §2 did **not** show that their corresponding failure modes caused E1–E3. They should **not** be counted as evidence-backed fixes merely because they are good engineering practice.

| Change (prompt or code) | §2 context / evidentiary limit | Repair, retry, or fail policy |
|---|---|---|
| **Prompt — Versioned in code** (`PROMPT_VERSION = "1.3"`; recorded in `report.py`). | **E3** makes provenance useful; there is no evidence that missing prompt versioning caused the incorrect counts. | Record the prompt used for a given output. |
| **Prompt — Remove arbitrary three-cluster ceiling** (`triage/prompt.py`). | **H2 in §2:** the September 3 cluster mixed HTTP 500, detached DOM, assertion mismatches, and timeouts under a server-error label. The evidence does **not** prove that the three-cluster limit caused the merging. This is a preventive diagnostic-quality change. | Merge only when supported by shared symptoms or a plausible cause; do not force a numerical limit. |
| **Code — Recover JSON surrounded by prose/Markdown** (`triage/validation.py`). | **E1** is a coverage failure, but bad JSON wrappers were not established as its cause. | **Repair** the wrapper, then validate every returned item. |
| **Code — Normalize supported enums and numeric confidence strings** (`triage/validation.py`). | **E1** provides the motivation for not losing usable items; the exact bad formats were not observed in §2. | **Repair** unambiguous formatting only, never invented values. |
| **Code — Validate schema, finish reason, fields and finite confidence** (`triage/validation.py`). | **E1:** output integrity matters; specific malformed schemas were not proven. | **Retry** invalid/truncated responses; preserve only separately validated classifications. |
| **Code — Bound and validate tool interactions** (`triage/agent.py`). | **E2:** historical evidence can inform retry decisions; runaway or malformed tool calls were not observed. | Check name, test ID, arguments, dates, rounds and call count, and reject reused `call_id` values across all tool rounds of the same model conversation; **retry**, then flag unresolved items. |
| **Code — Explicit model configuration and identity check** (`TRIAGE_MODEL` in `triage/agent.py`; reported in `triage/report.py`). | **E3:** comparison needs provenance; model drift was not established as its cause. | **Fail loudly** on unsupported/unexpected model identity. |
| **Code — Bounded retries for timeouts, rate limits and bad model output** (`triage/agent.py`). | **E1:** unprocessed input must be visible; transport failures were not proven to cause the 24 omissions. | Retry at most three attempts; mark remaining test IDs `retry_exhausted`; **fail loudly** for non-retryable model errors. |

## Clustering decision: why the prompt no longer says "at most 3"

The starter prompt (`prompts/classify.md`, v1.0) required at most three clusters to keep the Slack summary readable. Version **1.3** removes this fixed limit to avoid forcing diagnostically distinct failure patterns into the same group without supporting evidence.

The concern originates in §2. On September 3, the historical cluster `Server errors on write endpoints` contained 26 failures, including HTTP 500 responses, detached DOM elements, assertion mismatches, and locator timeouts. The cluster name did not adequately describe these different symptoms, and the records did not establish that they shared a common root cause.

This does **not** prove that the three-cluster limit caused the original grouping. It does, however, demonstrate why clustering quality should be evaluated through diagnostic evidence rather than through cluster count alone.

**Design decision:** preserve groups based on shared symptoms or plausible common causes, without enforcing an arbitrary maximum. Clusters represent diagnostic patterns, not confirmed root causes.

**Readability validation:** On the September 18 fixture, the rebuilt agent returned six symptom-pattern clusters covering all 27 failures. Their recorded sizes reconciled with the validated classifications. The Slack preview remained a single-line summary reporting the cluster count and classification totals, without listing each cluster individually.

Therefore, allowing six clusters introduced **no additional lines into the implemented Slack preview**. The additional distinctions remain available in the structured JSON, while the summary retains its compact format.

This separates two concerns:

- **Diagnostic integrity:** Preserve meaningful distinctions in the underlying triage data.
- **Presentation readability:** Communicate the validated totals concisely in Slack.

The original three-cluster ceiling was a presentation constraint, not evidence that three root causes were sufficient for every nightly run.

**Important limitation:** The historical E3 defect was inconsistent reporting, not excessive clustering. Recalculating cluster sizes from validated classifications addresses that accounting problem. Removing the cluster ceiling is a separate preventive decision supported by the diagnostic ambiguity observed in §2, not a proven fix for the historical count mismatch.

## Model-output and execution policy

| Bad output / event | Decision | Result |
|---|---|---|
| Valid JSON wrapped in Markdown/prose | **Repair** | Extract JSON; then validate content. |
| Supported casing/spacing variation or numeric confidence string | **Repair** | Normalize unambiguous fields; validate enum/range. |
| Missing classification, invalid class/confidence, blank rationale/cluster | **Retry** | Keep valid independent items; retry unresolved IDs up to 3 attempts; then `retry_exhausted`. |
| Invalid/truncated JSON, incomplete `finish_reason`, absent required arrays | **Retry** | Reject the response; retry pending IDs; eventually `retry_exhausted`. |
| Invented or duplicate test identities in a model response | **Retry** | Reject that response; never count invented/duplicate records. |
| Explicit `unclassified` with rationale | **Accept abstention** | Record `insufficient_evidence` and the input test ID; flag for manual review. |
| Rate limit / model timeout | **Retry** | Bounded attempts; flag unprocessed IDs `retry_exhausted` if exhausted. |
| Malformed/over-limit tool calls, including `call_id` reuse across tool rounds | **Retry, then flag** | Bounded agent loop; no uncontrolled or ambiguously matched tool execution. |
| Invalid fixture (including malformed required field types/ranges), duplicate input IDs, mismatched report totals, unknown or unexpected model, non-retryable provider error | **Fail loudly** | Explicit failure; do not produce a misleading completion report. |
| Valid report with unresolved tests | **Report + nonzero exit** | Print validated JSON and Slack preview with `needs_review`; return **exit code 2** for automation/manual escalation. |

## Verification and limitations

- **Fixture execution (prompt v1.3):** `python -m triage run fixtures/history/2026-09-18.json` completed with **27/27 validated**, `status: complete`, **0 unresolved**, **13 `real_bug` / 9 `flaky` / 5 `environment`**, **six symptom-pattern clusters** whose sizes total 27, and **nine history tool calls**. The printed Slack preview matched these validated totals. No message was posted.
- **Unit verification (prompt v1.3):** The §4 regression suite passed **22 tests**, including three additional boundary cases for a numeric `error_message`, an invalid `retry_count`, and a reused tool-call ID across tool rounds. Coverage also includes identity and output validation, missing/duplicate/invented records, bounded retries and tool use, explicit abstention, count reconciliation, and a `needs_review` CLI test verifying **exit code 2 after printing JSON and Slack**. The full agent fixture was rerun after these hardening changes: **27/27 validated**, with matching Slack totals and **exit code 0**.
- **Reproduction boundary:** An additional smoke run used a **synthetic fixture** to exercise the CLI wiring; it is not presented as separate evidence of correctness on the supplied historical fixture.
- The fake provider does not naturally declare `insufficient_evidence` in the observed real-fixture run; that path is tested with simulated responses.
- Neither the simulator's labels nor its cluster names provide ground truth. **No classification-accuracy improvement is claimed** without independently labeled evaluation data.
