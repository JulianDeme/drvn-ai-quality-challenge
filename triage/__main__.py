import argparse
import json
from pathlib import Path

from triage.agent import TriageError, run_agent
from triage.report import build_report


def main():
    parser = argparse.ArgumentParser(description="QA Triage Agent")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()

    try:
        with open(args.fixture, encoding="utf-8") as file:
            run_data = json.load(file)
        if not isinstance(run_data, dict):
            raise ValueError("Fixture must contain a JSON object")
        failures = run_data["raw_failures"]
        run_date = run_data["date"]
        run_id = run_data["run_id"]
        if not isinstance(failures, list) or not failures:
            raise ValueError("raw_failures must be a non-empty list")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("Invalid run_id")
        if not isinstance(run_date, str):
            raise ValueError("Invalid run date")
        for failure in failures:
            if not isinstance(failure, dict):
                raise ValueError("Invalid raw failure")
            for field in ("test_file", "test_title", "error_message", "retry_count"):
                if field not in failure:
                    raise ValueError(f"Missing input field: {field}")
            if (not isinstance(failure["error_message"], str)
                    or not failure["error_message"].strip()):
                raise ValueError("Invalid error_message: expected a non-empty string")
            if (type(failure["retry_count"]) is not int
                    or failure["retry_count"] < 0):
                raise ValueError("Invalid retry_count: expected a non-negative integer")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Error loading fixture: {error}\n")

    try:
        result = run_agent(failures, run_date)
        report = build_report(run_data, result)
    except (TriageError, ValueError, KeyError) as error:
        parser.exit(1, f"Triage failed: {error}\n")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("\n--- Slack Summary (preview only) ---")
    print(report["slack_summary"])

    # Print an honest review report, but tell CI that triage is not complete.
    if report["status"] == "needs_review":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
