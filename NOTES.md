# NOTES — Scope, Trade-offs, and Deferred Work

**Timebox (approximate):**

Approximately 3 hours of active, AI-assisted work across both parts:

- **Part A — Diagnose:** ~1 hour, focused on investigation and evidence analysis.
- **Part B — Rebuild & Evaluate:** ~2 hours, focused on implementation, validation, testing, and offline evaluation.

Approximately 15 additional minutes were spent completing `NOTES.md`. No further implementation, testing, or evaluation was performed.

## Approach and Prioritization

The approach evolved as the investigation progressed rather than following a fully predetermined implementation plan. Initial hypotheses guided the evidence analysis; the findings then informed the agent rebuild and, ultimately, its evaluation. Additional risks, limitations, and improvement opportunities emerged along the way.

AI assistance accelerated analysis, coding, and documentation. Technical direction and review of the reasoning, deliverables, and execution results remained human responsibilities. Functional verification was prioritized over an exhaustive source-code audit.

Within the time constraint, delivery of a working, verifiable solution was prioritized over expanding every area identified during development.

## §1 — First Read

No significant work was left incomplete. The assessment was limited to the requested three falsifiable hypotheses, including a non-model failure mode. Those hypotheses then guided the subsequent investigation.

## §2 — Evidence Analysis

**Deferred: Individual root-cause investigation of all 595 failures.**

**Why:** All 30 runs were analyzed programmatically, and specific failures were reviewed to substantiate the findings. Individual root causes were not investigated for every failure. Given the available time, reproducible system-level defects and verification of their supporting evidence were prioritized. The unavailable original implementation and diagnostic traces also limit how confidently individual root causes can be established.

**Deferred: Deeper longitudinal analysis of reliability degradation.**

**Why:** The six-week history could support further investigation into changes in the agent's behavior over time. Priority was given to demonstrating three concrete reliability problems rather than extending the investigation into trends whose causes and classification accuracy could not yet be verified.

## §3 — Is It Working?

**Not established: Historical classification accuracy, precision, and recall.**

**Why:** The six Jira records provide useful investigation leads but do not constitute failure-level ground truth. Instead of presenting unsupported accuracy estimates, run-level classification completeness was measured directly from the supplied data.

This is primarily an evidence limitation, not simply work deferred because of time.

## §4 — Agent Rebuild

**Deferred: Running and reviewing the rebuilt agent across all 30 historical fixtures.**

**Why:** Reliable execution of the required September 18 fixture, output validation, and targeted tests for important failure modes were prioritized. A broader replay matrix would provide additional confidence, but any discrepancies would also need to be reviewed and potentially addressed. With §5 still pending, this stage was not extended further.

**Deferred: Exhaustive fault-injection and recovery testing.**

**Why:** Important scenarios are covered, including malformed model output, missing classifications, transient errors, tool-call limits, and retry exhaustion. Not every possible combination or sequence of failures was tested. Bounded execution, explicit failure states, and representative deterministic tests were prioritized over exhaustive coverage within the timebox.

**Deferred: Deeper code-level review, refactoring, and optimization.**

**Why:** Understanding the agent's behavior, verifying its integration, and executing the tests were prioritized over a comprehensive line-by-line source-code audit. The implementation works under the tested scenarios, but passing tests do not establish that every implementation choice is optimal or that untested defects are absent.

Further internal review remains valuable, but was not treated as a prerequisite for completing the required functional deliverable.

## §5 — Evaluation and CI

**Deferred: A larger, more representative gold set across multiple nights.**

**Why:** The evaluation was limited to 12 labeled failures from September 18 instead of being expanded across the 30 historical runs. With the remaining time, completion of the required evaluation pipeline was prioritized: gold-set selection and justification, original-versus-rebuilt comparison, metric calculation, and an offline CI quality gate.

This provides a reproducible starting point, but not a representative estimate of historical or production classification quality.

**Deferred: Independent verification of gold labels and further false-positive investigation.**

**Why:** Some labels remain provisional judgments based on available failure evidence and Jira context. Against those labels, the rebuilt agent produced three false-positive `real_bug` classifications, with precision of 50%.

Given the limited evidence and remaining review time, this trade-off was documented instead of pursuing score improvements based on unsupported assumptions or tuning against FakeLLM's heuristics.

**Deferred: Multi-seed evaluation and broader retry-recovery measurement.**

**Why:** A fixed model configuration and seed were used to make the CI evaluation reproducible. A deterministic test verifies recovery from an invalid response, but the standard fixture completes in one attempt.

Testing multiple seeds and failure combinations would improve confidence in resilience, but the initial priority was a complete, functioning evaluation and regression gate.

**Deferred: Production-level quality thresholds and confidence calibration.**

**Why:** The current thresholds protect the fixed evaluation baseline; they do not establish production readiness. With a small gold set and uncertain labels, definitive quality targets would imply more confidence than the evidence supports.

Better labels and broader evaluation should precede classification-policy tuning or production acceptance criteria.

## Next Priorities

The highest-value next step would be to expand and independently review the gold set across multiple nights, particularly the cases labeled as false-positive `real_bug` predictions. Broader recovery testing across different seeds and failure scenarios, deeper implementation review, and recalibration of quality thresholds should follow as stronger evidence becomes available.

**The main trade-off was breadth versus a complete, verifiable delivery.** Demonstrable failure accounting, validated reporting, bounded recovery, and a working evaluation gate were prioritized. Broader classification-quality evidence and more extensive implementation review remain the most important unfinished work.
