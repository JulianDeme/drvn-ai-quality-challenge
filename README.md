# Nightly Triage Agent — frozen output pack

This pack contains six weeks of production output from drvn's automated test
triage agent, plus the prompt that produced it.

**The original agent's code is not included.** Everything you need is in this
repository. Nothing requires an API key, an account, or network access.

## What's here

```
prompts/classify.md          The agent's classification prompt (v1.0, unchanged
                             since launch)
fixtures/history/*.json      30 nightly runs, 2026-08-10 to 2026-09-18.
                             Each file contains the raw Playwright failures the
                             agent received AND the output it produced.
jira/escaped_bugs.json       Six defects that reached production during this
                             period, with the test that should have caught each.
starter/fake_llm.py          Offline fake LLM API for Part B. Read its docstring.
starter/history_tool.py      Local tool: a test's results on previous nights.
```

Do not modify `starter/`. Import it from your code (`from starter.fake_llm import FakeLLM`).

## Reading a run file

| Field | Meaning |
|---|---|
| `model_version` | Which model produced this run's output |
| `total_failures` | Failures in the Playwright report |
| `failures_accounted_for` | Failures present in the agent's output |
| `clusters` | The groups the agent formed |
| `classifications` | Per-failure verdict, confidence, and rationale |
| `slack_summary` | Exactly what was posted to the QA channel that morning |
| `raw_failures` | The input the agent saw: error, stack, retry count, duration |

## Ground truth

There isn't any. Nobody labeled this data. `jira/escaped_bugs.json` is the only
external signal available, and it is incomplete by construction — it records
defects that were *caught in production*, not every defect that existed.

Working out what can be concluded from this is part of the challenge.

## How to Run
Run from the repository root with Python 3.13. Fully offline; no API keys or third-party dependencies required.

- **Agent (validated JSON + Slack preview) §4:** `python -m triage run fixtures/history/2026-09-18.json`
- **Unit tests §4–5:** `python -m unittest discover -s tests -v`
- **Original vs. rebuilt evaluation §5:** `python evals/run_eval.py`
- **Quality gate §5:** `python evals/run_eval.py --min-real-bug-recall 0.60 --min-real-bug-precision 0.50 --min-coverage 1.0 --min-valid-output-rate 1.0`
- **Negative gate test (expected exit 1) §5:** `python evals/run_eval.py --min-real-bug-recall 0.80 --min-real-bug-precision 0.50 --min-coverage 1.0 --min-valid-output-rate 1.0`

Agent exit codes: `0` = complete, `1` = execution failure, `2` = manual review required. GitHub Actions runs on push and pull requests.