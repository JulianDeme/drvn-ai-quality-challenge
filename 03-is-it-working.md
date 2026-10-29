# Nightly Triage Agent — Is It Working?

**Document:** `03-is-it-working.md`  
**References:** `02-evidence.md`, `jira/escaped_bugs.json`  
**Scope:** Label-free reliability measurement and Jira cross-referencing  

---

## Can We Tell If the Agent Is Working?

**Not conclusively.** The agent generates triage reports, but the historical data alone is insufficient to establish whether its classifications accurately identify genuine application defects.

We can measure reporting completeness without ground-truth labels. Classification correctness, however, requires independently verified outcomes.

### Label-Free Metric — Run-Level Classification Completeness

**76.7% (23/30 runs)**

Only 23 of the 30 nightly runs contained a classification for every recorded failure.

The remaining seven runs collectively omitted 24 of 595 raw failures (4.03%).

This metric measures whether the triage output accounts for all input failures, not whether the assigned categories are correct.

Nearly one in four nightly runs had incomplete classification coverage, demonstrating a measurable reporting reliability problem.

### What Can We Conclude from Jira?

The six Jira records document reported application defects and link each issue to a specific automated test. Five of those linked tests appear in the historical failure records.

One concerning example is **IT-3418 — Multi-leg itinerary priced incorrectly**.

Its linked test, `booking/multileg.spec.ts::should price multi-leg itinerary 3`, appeared as a failure in 14 nightly runs:

- 7 classifications as `flaky`.
- 7 classifications as `environment`.
- 0 classifications as `real_bug`.

This raises a legitimate concern about potentially missed defects.

However, the Jira link does not prove that each recorded failure was caused by the documented pricing issue. Different executions may fail for unrelated reasons.

The test linked to **IT-3466 — Group discount not applied for 10+ passengers** does not appear in the failure records. This does not establish whether the test was executed, passed, or was excluded from the regression suite.

Jira therefore provides useful investigation leads, but not a complete ground-truth dataset for evaluating the agent.

### What Can't We Conclude?

From the historical outputs and Jira links alone, we cannot reliably establish:

- **Classification accuracy:** How many assigned labels were actually correct.
- **Precision:** How many failures labeled `real_bug` corresponded to genuine application defects.
- **Recall:** How many genuine application defects the agent successfully identified.
- **Defect detection effectiveness:** How many reported defects were correctly surfaced or overlooked.

These measurements require failure-level reference labels supported by independent investigation.

A test's association with a Jira defect is insufficient to assign the same root cause to every failed execution.

---

## Conclusion

**We can demonstrate that the original agent has measurable reporting reliability problems, but we cannot establish its classification effectiveness from the historical data alone.**

Run-level classification completeness was 76.7%, with 24 recorded failures omitted across seven runs.

The Jira cross-reference highlights potentially missed application defects, particularly IT-3418, but does not provide enough evidence to calculate trustworthy classification accuracy, precision, or recall.

Without independently verified labels for individual failures, the historical evidence cannot establish the agent's classification accuracy or effectiveness.