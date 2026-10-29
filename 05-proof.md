# Part B — Evaluation Proof

**Document:** `05-proof.md`  
**References:** `04-changes.md`, `evals/gold.jsonl`, `evals/run_eval.py`, `.github/workflows/eval.yml`  
**Scope:** Offline evaluation, labeled gold set, regression testing, and CI quality gate  

---

### 1. What does the evaluation prove, and what doesn't it?

Part A examined 30 nightly runs across six weeks; this evaluation intentionally uses the fixed September 18 fixture to compare the original recorded output and rebuilt agent on identical inputs. On 12 manually labeled failures, real-bug recall was 20% for the original versus 60% for the rebuilt agent, and label agreement was 41.7% versus 58.3%. The original recorded report was structurally inconsistent; the rebuilt report passed output validation. These are sample-specific results, not production accuracy estimates.

**Gold-set selection:** I selected 12 of the 27 September 18 failures to contrast retried and non-retried cases with comparable error signatures, including staging-payment connection refusals, and to cover HTTP/assertion, detached-DOM, and timeout failures, with and without related Jira evidence.

The §4 regression suite grew from 19 to **22 passing tests** after three boundary cases were added for malformed fixture fields and tool-call ID reuse. During §5, one deterministic retry-recovery test (`tests/test_retry_recovery.py`) was added, bringing the combined suite to **23/23 passing tests** (exit code 0). It injects invalid JSON followed by a valid response and verifies recovery on the second attempt, including final report validation. The rebuilt agent also completed the September 18 fixture with **27/27 validated classifications** (exit code 0).

The normal fixture evaluation required only one model attempt, so it cannot establish real-world retry recovery rates. The gold set is small, some labels remain uncertain, and FakeLLM uses fixed heuristics. The results do not establish that prompt changes improved classification reasoning.

### 2. What result would make you revert?

I would block or revert a regression that lowers real-bug recall below **60%**, precision below **50%**, gold-set classification coverage below **100%**, or final-output validity below **100%** on this fixed evaluation. Silent omissions, inconsistent Slack counts, or reporting success after exhausted retries are additional rollback triggers.

The CI coverage threshold applies to the 12 labeled gold-set cases, not to the full 27-failure fixture. Full-run classification completeness is reported separately.

These thresholds intentionally match the current deterministic baseline: they are **regression guards**, not claims that 60% recall or 50% precision is sufficient for production.

With the simulator version and seed fixed, a drop on the same gold set deserves investigation before acceptance. Structural integrity has no acceptable regression margin. Broader labeled data would be needed to set production quality targets.

### 3. What did the fix probably make worse?

On this fixed evaluation, the rebuilt system surfaced more potential real bugs at the cost of additional false positives. Real-bug precision decreased from **100% (1/1)** to **50% (3/6)**, introducing three false-positive `real_bug` classifications in the gold set.

This increases manual investigation workload and creates a risk of alert fatigue. Additional validation, history lookups, and bounded retries also introduce implementation complexity and potentially higher execution latency.

**This is an acceptable observed trade-off for triage, not a demonstrated improvement in the model's reasoning.** The fake provider relies on fixed heuristics, so the classification differences cannot be attributed confidently to the rewritten prompt.

The system-level objective remains to account for every failure, validate what is reported, and surface uncertainty rather than silently dismissing potential defects.
