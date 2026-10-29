
"""Deterministic contract-repair regression: invalid model output, then valid output."""

import io
import json
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch

from evals.run_eval import validate_report
from triage.agent import run_agent
from triage.report import build_report


FAILURES = [
    {
        "test_file": "booking/quote.spec.ts",
        "test_title": title,
        "error_message": "Expected 200, received 500",
        "retry_count": 0,
    }
    for title in ("should calculate quote", "should calculate tax")
]


def model_response(content):
    return SimpleNamespace(
        model="drvn-sim-1.0",
        content=content,
        finish_reason="stop",
        tool_calls=[],
    )


class TestRetryRecovery(unittest.TestCase):
    @patch("triage.agent.time.sleep")
    @patch("triage.agent.FakeLLM")
    def test_invalid_first_response_then_valid_second(self, fake_llm, sleep):
        valid_payload = {
            "clusters": [{"name": "Server errors", "size": 2}],
            "classifications": [
                {
                    "test_file": failure["test_file"],
                    "test_title": failure["test_title"],
                    "cluster": "Server errors",
                    "classification": "real_bug",
                    "confidence": 0.9,
                    "rationale": "Observed HTTP response mismatch",
                }
                for failure in FAILURES
            ],
        }
        fake_llm.return_value.complete.side_effect = [
            model_response('{"clusters": [INVALID JSON'),
            model_response(json.dumps(valid_payload)),
        ]

        diagnostic = io.StringIO()
        with redirect_stderr(diagnostic):
            result = run_agent(FAILURES, "2026-09-18")

        self.assertEqual(fake_llm.return_value.complete.call_count, 2)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(result["classifications"]), len(FAILURES))
        self.assertEqual(result["unclassified"], [])
        self.assertIn("Retrying 2 pending failures", diagnostic.getvalue())
        sleep.assert_called_once_with(0)

        fixture = {
            "run_id": "retry-repair-probe",
            "date": "2026-09-18",
            "raw_failures": FAILURES,
            "total_failures": len(FAILURES),
        }
        report = build_report(fixture, result)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["execution"]["attempts"], 2)
        self.assertEqual(report["validated_classifications"], 2)
        self.assertEqual(validate_report(report, fixture, modern=True), [])


if __name__ == "__main__":
    unittest.main()
