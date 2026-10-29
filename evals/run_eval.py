"""Offline, deterministic comparison against a manually reviewed JSONL gold set.

Run from the repository root:
    python evals/run_eval.py
    python evals/run_eval.py --min-real-bug-recall 0.60 --min-real-bug-precision 0.50 --min-coverage 1.0 --min-valid-output-rate 1.0

The original output is the recorded snapshot in the fixture. The rebuilt
agent is executed through the public CLI, using its pinned FakeLLM seed=42.
"""

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

LABELS = {"real_bug", "flaky", "environment"}
REASONS = {"retry_exhausted", "insufficient_evidence"}
ROOT = Path(__file__).resolve().parent.parent
MODEL = "drvn-sim-1.0"
SLACK_MARKER = "--- Slack Summary (preview only) ---"


def identity(item):
    return (item["test_file"], item["test_title"])


def load_inputs(fixture_path, gold_path):
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    failures = fixture["raw_failures"]
    if not isinstance(failures, list) or not failures:
        raise ValueError("Fixture must contain nonempty raw_failures")
    ids = [identity(item) for item in failures]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate fixture test IDs")
    if fixture.get("total_failures", len(failures)) != len(failures):
        raise ValueError("Fixture total_failures does not match raw_failures")
    if not isinstance(fixture.get("classifications"), list):
        raise ValueError("Fixture has no recorded original classifications")

    gold = {}
    for line_no, line in enumerate(gold_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        key = identity(entry)
        if key in gold or key not in set(ids):
            raise ValueError(f"Gold line {line_no}: duplicate or unknown test {key}")
        if entry.get("gold_label") not in LABELS:
            raise ValueError(f"Gold line {line_no}: invalid gold_label")
        if not isinstance(entry.get("justification"), str) or not entry["justification"].strip():
            raise ValueError(f"Gold line {line_no}: justification required")
        gold[key] = entry["gold_label"]
    if len(gold) < 10:
        raise ValueError("At least 10 gold cases are required")
    return fixture, gold


def valid_classification(item):
    if not isinstance(item, dict):
        return False
    if item.get("classification") not in LABELS:
        return False
    if not all(isinstance(item.get(k), str) and item[k].strip()
               for k in ("test_file", "test_title", "cluster", "rationale")):
        return False
    confidence = item.get("confidence")
    return (type(confidence) in (float, int)
            and math.isfinite(confidence) and 0 <= confidence <= 1)


def validated_items(report, expected_ids):
    predictions = {}
    issues = []
    seen = set()
    for item in report.get("classifications", []):
        if not isinstance(item, dict):
            issues.append("Non-object classification")
            continue
        key = (item.get("test_file"), item.get("test_title"))
        if key in seen or key not in expected_ids:
            issues.append(f"Duplicate or invented classification: {key}")
            continue
        seen.add(key)
        if not valid_classification(item):
            issues.append(f"Invalid classification: {key}")
            continue
        predictions[key] = item
    return predictions, issues


def validate_report(report, fixture, modern=False):
    """Validate full-run accounting independently from gold-set accuracy."""
    issues = []
    expected = {identity(item) for item in fixture["raw_failures"]}
    raw_items = report.get("classifications")
    if not isinstance(raw_items, list):
        return ["Missing classifications array"]
    predictions, item_issues = validated_items(report, expected)
    issues.extend(item_issues)
    pending = report.get("unclassified", []) if modern else []
    if not isinstance(pending, list):
        issues.append("Invalid unclassified array")
        pending = []

    pending_ids = set()
    for entry in pending:
        if not isinstance(entry, dict):
            issues.append("Non-object unclassified entry")
            continue
        key = (entry.get("test_file"), entry.get("test_title"))
        if (key not in expected or key in pending_ids or key in predictions
                or entry.get("reason") not in REASONS
                or not isinstance(entry.get("detail"), str)
                or not entry["detail"].strip()):
            issues.append(f"Invalid/duplicate unclassified entry: {key}")
        pending_ids.add(key)

    if set(predictions) | pending_ids != expected:
        issues.append("Not all input failures are validly accounted for")
    if report.get("run_id") != fixture.get("run_id"):
        issues.append("run_id mismatch")
    if report.get("total_failures") != len(expected):
        issues.append("total_failures mismatch")
    if report.get("failures_accounted_for") != len(expected):
        issues.append("failures_accounted_for mismatch")

    counts = Counter(item["classification"] for item in predictions.values())
    clusters = Counter(item["cluster"] for item in predictions.values())
    declared_clusters = report.get("clusters")
    if not isinstance(declared_clusters, list):
        issues.append("Missing clusters array")
    else:
        actual_clusters = {}
        for entry in declared_clusters:
            if (not isinstance(entry, dict)
                    or not isinstance(entry.get("name"), str)
                    or not entry["name"].strip()
                    or type(entry.get("size")) is not int
                    or entry["size"] <= 0
                    or entry["name"] in actual_clusters):
                issues.append("Malformed or duplicate cluster")
                continue
            actual_clusters[entry["name"]] = entry["size"]
        if actual_clusters != dict(clusters):
            issues.append("Cluster sizes do not match classifications")

    summary = report.get("slack_summary")
    if not isinstance(summary, str) or not summary.strip():
        issues.append("Missing Slack summary")
    else:
        for label, pattern in {
            "real_bug": r"\b(\d+)\s+real\s+bugs?\b",
            "flaky": r"\b(\d+)\s+flaky\b",
            "environment": r"\b(\d+)\s+environment\b",
        }.items():
            match = re.search(pattern, summary, flags=re.IGNORECASE)
            if not match or int(match.group(1)) != counts[label]:
                issues.append(f"Slack {label} count mismatch")
        summary_numbers = (
            (r"\b(\d+)\s+failures explained\b", len(predictions), "explained"),
            (r"\b(\d+)\s+failures detected\b", len(expected), "detected"),
            (r"\b(\d+)\s+classifications validated\b", len(predictions), "validated"),
            (r"\b(\d+)\s+unclassified\b", len(pending), "unclassified"),
            (r"\b(\d+)\s+clusters\b", len(clusters), "clusters"),
        )
        for pattern, expected_count, name in summary_numbers:
            match = re.search(pattern, summary, flags=re.IGNORECASE)
            if match and int(match.group(1)) != expected_count:
                issues.append(f"Slack {name} count mismatch")

    if modern:
        if report.get("validated_classifications") != len(predictions):
            issues.append("validated_classifications mismatch")
        if report.get("unclassified_failures") != len(pending):
            issues.append("unclassified_failures mismatch")
        if report.get("classification_counts") != {k: counts[k] for k in ("real_bug", "flaky", "environment")}:
            issues.append("classification_counts mismatch")
        if report.get("unclassified_breakdown") != {k: sum(e.get("reason") == k for e in pending if isinstance(e, dict)) for k in ("retry_exhausted", "insufficient_evidence")}:
            issues.append("unclassified_breakdown mismatch")
        expected_status = "needs_review" if pending else "complete"
        if report.get("status") != expected_status or report.get("manual_review_required") is not bool(pending):
            issues.append("Status/manual-review mismatch")
        execution = report.get("execution", {})
        if (not isinstance(execution, dict)
                or type(execution.get("attempts")) is not int
                or not 1 <= execution["attempts"] <= 3):
            issues.append("Invalid/missing attempt metadata")
    return issues


def run_rebuilt(fixture_path):
    env = dict(os.environ)
    env["TRIAGE_MODEL"] = MODEL
    env["PYTHONHASHSEED"] = "0"
    completed = subprocess.run(
        [sys.executable, "-m", "triage", "run", str(fixture_path.resolve())],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=120,
        check=False,
    )
    if completed.returncode not in (0, 2):
        raise RuntimeError(f"Rebuilt agent failed (exit {completed.returncode}): {completed.stderr.strip()}")
    decoder = json.JSONDecoder()
    report, end = decoder.raw_decode(completed.stdout.lstrip())
    remaining = completed.stdout.lstrip()[end:].strip()
    prefix = SLACK_MARKER + "\n"
    if not remaining.startswith(prefix) or remaining[len(prefix):].strip() != report.get("slack_summary"):
        raise ValueError("CLI output is not exactly JSON followed by its Slack preview")
    if (completed.returncode == 2) != (report.get("status") == "needs_review"):
        raise ValueError("CLI exit code does not match review status")
    return report


def score(report, fixture, gold, modern=False):
    expected = {identity(item) for item in fixture["raw_failures"]}
    predictions, _ = validated_items(report, expected)
    tp = sum(gold_label == "real_bug" and predictions.get(key, {}).get("classification") == "real_bug"
             for key, gold_label in gold.items())
    actual_bugs = sum(label == "real_bug" for label in gold.values())
    predicted_bugs = sum(predictions.get(key, {}).get("classification") == "real_bug" for key in gold)
    covered = sum(key in predictions for key in gold)
    matches = sum(predictions.get(key, {}).get("classification") == label for key, label in gold.items())
    issues = validate_report(report, fixture, modern=modern)
    return {
        "real_bug_recall": tp / actual_bugs if actual_bugs else None,
        "real_bug_precision": tp / predicted_bugs if predicted_bugs else None,
        "coverage": covered / len(gold),
        "gold_accuracy": matches / len(gold),
        "true_real_bugs": tp,
        "gold_real_bugs": actual_bugs,
        "real_bug_false_positives": predicted_bugs - tp,
        "classified_gold": covered,
        "gold_total": len(gold),
        "classified_all": len(predictions),
        "all_failures": len(expected),
        "valid_output": not issues,
        "issues": issues,
    }


def pct(value):
    return "N/A" if value is None else f"{100 * value:.1f}%"


def main():
    parser = argparse.ArgumentParser(description="Offline regression evaluation for triage")
    parser.add_argument("--fixture", type=Path, default=ROOT / "fixtures/history/2026-09-18.json")
    parser.add_argument("--gold", type=Path, default=ROOT / "evals/gold.jsonl")
    parser.add_argument("--min-real-bug-recall", type=float, default=None)
    parser.add_argument("--min-real-bug-precision", type=float, default=None)
    parser.add_argument("--min-coverage", type=float, default=None)
    parser.add_argument("--min-valid-output-rate", type=float, default=None)
    args = parser.parse_args()
    try:
        fixture, gold = load_inputs(args.fixture, args.gold)
        rebuilt = run_rebuilt(args.fixture)
        original = score(fixture, fixture, gold)
        updated = score(rebuilt, fixture, gold, modern=True)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")

    print(f"Fixture: {fixture['run_id']} | Gold: {len(gold)} manually labeled tests")
    print(f"Model: {MODEL} | FakeLLM seed: 42 (pinned in triage.agent)")
    print("\nMetric                              Original recorded    Rebuilt (post-policy)")
    print("-" * 78)
    for label, key in (
        ("Real-bug recall", "real_bug_recall"),
        ("Real-bug precision", "real_bug_precision"),
        ("Gold classification coverage", "coverage"),
        ("Gold label agreement", "gold_accuracy"),
    ):
        print(f"{label:<36}{pct(original[key]):<21}{pct(updated[key])}")
    print(f"{'Final valid-output rate':<36}{pct(float(original['valid_output'])):<21}{pct(float(updated['valid_output']))}")
    print(f"{'Full-run classification coverage':<36}{original['classified_all']}/{original['all_failures']:<18}{updated['classified_all']}/{updated['all_failures']}")
    print(f"{'False-positive real bugs on gold':<36}{original['real_bug_false_positives']:<21}{updated['real_bug_false_positives']}")
    print(f"Rebuilt model attempts: {rebuilt['execution']['attempts']} (max 3; policy includes bounded retries)")
    print("Final-output validity is measured over ONE recorded run per agent (0/1 or 1/1).")
    print("Original retry attempts were not recorded; original retry recovery rate is unknown.")
    print("No retry recovery can be inferred if rebuilt attempts = 1.")
    for name, item in (("Original", original), ("Rebuilt", updated)):
        print(f"{name} report: {'VALID' if item['valid_output'] else 'INVALID'}")
        for issue in item["issues"]:
            print(f"  - {issue}")

    gates = (
        ("real-bug recall", updated["real_bug_recall"], args.min_real_bug_recall),
        ("real-bug precision", updated["real_bug_precision"], args.min_real_bug_precision),
        ("gold coverage", updated["coverage"], args.min_coverage),
        ("valid-output rate", float(updated["valid_output"]), args.min_valid_output_rate),
    )
    for name, value, threshold in gates:
        if threshold is not None and (not 0 <= threshold <= 1 or value is None or value < threshold):
            print(f"FAIL: {name} = {pct(value)}; threshold = {pct(threshold)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
