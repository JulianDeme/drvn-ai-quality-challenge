from collections import Counter
from triage.prompt import PROMPT_VERSION

VALID_CLASSES = ("real_bug", "flaky", "environment")
REASONS = ("retry_exhausted", "insufficient_evidence")


def build_report(run_data, result):
    failures = run_data["raw_failures"]
    classifications = result["classifications"]
    unclassified = result["unclassified"]

    expected = [(f["test_file"], f["test_title"]) for f in failures]
    accounted = [
        (f["test_file"], f["test_title"])
        for f in classifications + unclassified
    ]
    if (len(expected) != len(set(expected))
            or len(accounted) != len(set(accounted))
            or set(expected) != set(accounted)):
        raise ValueError("Report has missing, duplicate or invented test IDs")
    if ("total_failures" in run_data
            and run_data["total_failures"] != len(expected)):
        raise ValueError("Input failure count mismatch")

    counts = Counter(f["classification"] for f in classifications)
    if set(counts) - set(VALID_CLASSES):
        raise ValueError("Unexpected classification in report")
    reasons = Counter(f["reason"] for f in unclassified)
    if set(reasons) - set(REASONS):
        raise ValueError("Unexpected unclassified reason")
    clusters = Counter(f["cluster"] for f in classifications)

    total = len(expected)
    validated = len(classifications)
    pending = len(unclassified)
    needs_review = pending > 0
    summary = (
        f"Run {run_data['run_id']}: {total} failures detected. "
        f"{validated} classifications validated; {pending} unclassified "
        f"({reasons['retry_exhausted']} retries exhausted, "
        f"{reasons['insufficient_evidence']} insufficient evidence). "
        f"{counts['real_bug']} real bugs, "
        f"{counts['environment']} environment, {counts['flaky']} flaky. "
        f"{len(clusters)} clusters. "
        + ("Manual review required." if needs_review else "Triage complete.")
    )

    return {
        "run_id": run_data["run_id"],
        "date": run_data["date"],
        "status": "needs_review" if needs_review else "complete",
        "prompt_version": PROMPT_VERSION,
        "model_version": result["model"],
        "total_failures": total,
        "failures_accounted_for": total,
        "validated_classifications": validated,
        "unclassified_failures": pending,
        "unclassified_breakdown": {reason: reasons[reason] for reason in REASONS},
        "manual_review_required": needs_review,
        "classification_counts": {label: counts[label] for label in VALID_CLASSES},
        "clusters": [
            {"name": name, "size": size}
            for name, size in sorted(clusters.items())
        ],
        "classifications": classifications,
        "unclassified": unclassified,
        "execution": {
            "attempts": result["attempts"],
            "history_tool_calls": result["history_tool_calls"],
        },
        "slack_summary": summary,
    }
