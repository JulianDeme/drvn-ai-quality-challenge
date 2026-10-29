import copy
import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from starter.fake_llm import LLMError, LLMTimeoutError, RateLimitError
from triage.agent import MAX_TOOL_CALLS, TriageError, run_agent
from triage.__main__ import main as cli_main
from triage.prompt import PROMPT_VERSION, SYSTEM_PROMPT
from triage.report import build_report
from triage.validation import (
    TriageValidationError,
    validate_partial_response,
    validate_response,
)

FAILURES = [
    {
        "test_file": "booking/quote.spec.ts",
        "test_title": title,
        "error_message": "Expected 200, received 500",
        "retry_count": 0,
    }
    for title in ("should calculate quote", "should calculate tax")
]


def output_for(indices=(0, 1)):
    return {
        "clusters": [{"name": "Server error", "size": len(indices)}],
        "classifications": [
            {
                "test_file": FAILURES[i]["test_file"],
                "test_title": FAILURES[i]["test_title"],
                "cluster": "Server error",
                "classification": "real_bug",
                "confidence": 0.9,
                "rationale": "Unexpected response",
            }
            for i in indices
        ],
    }


def response(data=None, finish_reason="stop", tool_calls=None):
    return SimpleNamespace(
        model="drvn-sim-1.0",
        content=json.dumps(data) if data is not None else None,
        finish_reason=finish_reason,
        tool_calls=tool_calls or [],
    )


class TestValidation(unittest.TestCase):
    def test_valid_response(self):
        self.assertEqual(len(validate_response(response(output_for()), FAILURES)), 2)

    def test_missing_classification(self):
        valid, undecided = validate_partial_response(
            response(output_for((0,))), FAILURES
        )
        self.assertEqual(len(valid), 1)
        self.assertEqual(undecided, [])
        with self.assertRaises(TriageValidationError):
            validate_response(response(output_for((0,))), FAILURES)

    def test_invented_test(self):
        data = output_for()
        data["classifications"][0]["test_title"] = "invented test"
        with self.assertRaises(TriageValidationError):
            validate_partial_response(response(data), FAILURES)

    def test_duplicate_classification(self):
        data = output_for()
        data["classifications"].append(copy.deepcopy(data["classifications"][0]))
        with self.assertRaises(TriageValidationError):
            validate_partial_response(response(data), FAILURES)

    def test_truncated_response(self):
        with self.assertRaises(TriageValidationError):
            validate_partial_response(
                response(output_for(), finish_reason="length"), FAILURES
            )

    def test_repair_json_wrapper(self):
        wrapped = response(output_for())
        wrapped.content = f"Here is the result:\n```json\n{wrapped.content}\n```"
        self.assertEqual(len(validate_response(wrapped, FAILURES)), 2)

    def test_normalize_enum_and_confidence(self):
        data = output_for()
        data["classifications"][0]["classification"] = "REAL BUG"
        data["classifications"][0]["confidence"] = "0.9"
        valid, _ = validate_partial_response(response(data), FAILURES)
        self.assertEqual(valid[0]["classification"], "real_bug")
        self.assertEqual(valid[0]["confidence"], 0.9)

    def test_explicit_insufficient_evidence(self):
        data = output_for((1,))
        data["classifications"][0]["classification"] = "unclassified"
        data["classifications"][0].pop("cluster")
        _, undecided = validate_partial_response(response(data), FAILURES)
        self.assertEqual(undecided[0]["reason"], "insufficient_evidence")


class TestAgent(unittest.TestCase):
    @patch("triage.agent.time.sleep")
    @patch("triage.agent.FakeLLM")
    def test_retry_rate_limit(self, fake_llm, _):
        fake_llm.return_value.complete.side_effect = [
            RateLimitError(0), response(output_for())
        ]
        result = run_agent(FAILURES, "2026-09-18")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["unclassified"], [])

    @patch("triage.agent.time.sleep")
    @patch("triage.agent.FakeLLM")
    def test_timeout_exhaustion_requires_review(self, fake_llm, _):
        fake_llm.return_value.complete.side_effect = LLMTimeoutError("timeout")
        result = run_agent(FAILURES, "2026-09-18")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(len(result["unclassified"]), 2)
        self.assertTrue(all(
            item["reason"] == "retry_exhausted"
            for item in result["unclassified"]
        ))

    @patch("triage.agent.time.sleep")
    @patch("triage.agent.FakeLLM")
    def test_preserve_valid_and_retry_missing(self, fake_llm, _):
        fake_llm.return_value.complete.side_effect = [
            response(output_for((0,))),
            response(output_for(())),
            response(output_for(())),
        ]
        result = run_agent(FAILURES, "2026-09-18")
        self.assertEqual(len(result["classifications"]), 1)
        self.assertEqual(len(result["unclassified"]), 1)
        self.assertEqual(result["unclassified"][0]["reason"], "retry_exhausted")
        calls = fake_llm.return_value.complete.call_args_list
        last_batch = json.loads(calls[1].kwargs["messages"][0]["content"])
        self.assertEqual(len(last_batch), 1)
        self.assertEqual(last_batch[0]["test_title"], FAILURES[1]["test_title"])

    @patch("triage.agent.FakeLLM")
    def test_model_declares_insufficient_evidence(self, fake_llm):
        data = output_for()
        data["classifications"][1]["classification"] = "unclassified"
        data["classifications"][1]["rationale"] = "Not enough evidence"
        fake_llm.return_value.complete.return_value = response(data)
        result = run_agent(FAILURES, "2026-09-18")
        self.assertEqual(len(result["classifications"]), 1)
        self.assertEqual(result["unclassified"][0]["reason"], "insufficient_evidence")

    @patch("triage.agent.FakeLLM")
    def test_nonretryable_model_error(self, fake_llm):
        fake_llm.return_value.complete.side_effect = LLMError("unknown model")
        with self.assertRaises(TriageError):
            run_agent(FAILURES, "2026-09-18")
        self.assertEqual(fake_llm.return_value.complete.call_count, 1)

    @patch("triage.agent.FakeLLM")
    @patch("triage.agent.get_test_history")
    def test_history_tool_loop(self, history_tool, fake_llm):
        test_id = "booking/quote.spec.ts::should calculate quote"
        call = {
            "id": "call_1",
            "name": "get_test_history",
            "arguments": {"test_id": test_id},
        }
        history_tool.return_value = [{"date": "2026-09-17", "failed": True}]
        fake_llm.return_value.complete.side_effect = [
            response(finish_reason="tool_use", tool_calls=[call]),
            response(output_for()),
        ]
        result = run_agent(FAILURES, "2026-09-18")
        self.assertEqual(result["history_tool_calls"], 1)
        history_tool.assert_called_once_with(
            test_id, before_date="2026-09-18", nights=5
        )

    @patch("triage.agent.time.sleep")
    @patch("triage.agent.FakeLLM")
    @patch("triage.agent.get_test_history")
    def test_reused_tool_call_id_across_rounds(self, history_tool, fake_llm, _):
        first_call = {
            "id": "call_1",
            "name": "get_test_history",
            "arguments": {
                "test_id": "booking/quote.spec.ts::should calculate quote"
            },
        }
        reused_id_call = {
            "id": "call_1",
            "name": "get_test_history",
            "arguments": {
                "test_id": "booking/quote.spec.ts::should calculate tax"
            },
        }
        history_tool.return_value = []
        fake_llm.return_value.complete.side_effect = [
            response(finish_reason="tool_use", tool_calls=[first_call]),
            response(finish_reason="tool_use", tool_calls=[reused_id_call]),
            response(output_for()),
        ]

        result = run_agent(FAILURES, "2026-09-18")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(result["classifications"]), 2)
        self.assertEqual(result["unclassified"], [])
        history_tool.assert_called_once()

    @patch("triage.agent.time.sleep")
    @patch("triage.agent.FakeLLM")
    @patch("triage.agent.get_test_history")
    def test_tool_call_limit(self, history_tool, fake_llm, _):
        test_id = "booking/quote.spec.ts::should calculate quote"
        calls = [
            {
                "id": f"call_{i}",
                "name": "get_test_history",
                "arguments": {"test_id": test_id},
            }
            for i in range(MAX_TOOL_CALLS + 1)
        ]
        fake_llm.return_value.complete.return_value = response(
            finish_reason="tool_use", tool_calls=calls
        )
        result = run_agent(FAILURES, "2026-09-18")
        history_tool.assert_not_called()
        self.assertEqual(len(result["unclassified"]), 2)
        self.assertEqual(result["attempts"], 3)


class TestReport(unittest.TestCase):
    def test_complete_report_counts(self):
        result = {
            "model": "drvn-sim-1.0",
            "attempts": 1,
            "history_tool_calls": 0,
            "classifications": validate_response(response(output_for()), FAILURES),
            "unclassified": [],
        }
        report = build_report({
            "run_id": "test-run",
            "date": "2026-09-18",
            "raw_failures": FAILURES,
            "total_failures": 2,
        }, result)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(sum(c["size"] for c in report["clusters"]), 2)
        self.assertEqual(sum(report["classification_counts"].values()), 2)

    def test_review_report_counts(self):
        result = {
            "model": "drvn-sim-1.0",
            "attempts": 3,
            "history_tool_calls": 0,
            "classifications": validate_response(
                response(output_for((0,))), [FAILURES[0]]
            ),
            "unclassified": [{
                "test_file": FAILURES[1]["test_file"],
                "test_title": FAILURES[1]["test_title"],
                "reason": "retry_exhausted",
                "detail": "No valid response after 3 attempts",
            }],
        }
        report = build_report({
            "run_id": "test-run",
            "date": "2026-09-18",
            "raw_failures": FAILURES,
            "total_failures": 2,
        }, result)
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["validated_classifications"], 1)
        self.assertEqual(report["unclassified_failures"], 1)
        self.assertIn("Manual review required", report["slack_summary"])


class TestCLIBoundary(unittest.TestCase):
    def test_needs_review_prints_report_and_exits_two(self):
        fixture = {
            "run_id": "test-run",
            "date": "2026-09-18",
            "raw_failures": FAILURES,
        }
        preview = {
            "status": "needs_review",
            "slack_summary": "1 item needs human review.",
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            fixture_path = Path(temporary_dir) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            printed = io.StringIO()
            with (
                patch("sys.argv", ["triage", "run", str(fixture_path)]),
                patch("triage.__main__.run_agent", return_value={}),
                patch("triage.__main__.build_report", return_value=preview),
                redirect_stdout(printed),
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('"status": "needs_review"', printed.getvalue())
        self.assertIn("1 item needs human review.", printed.getvalue())

    def _assert_invalid_fixture_field(self, field, value, error_message):
        fixture = {
            "run_id": "test-run",
            "date": "2026-09-18",
            "raw_failures": [dict(FAILURES[0], **{field: value})],
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            fixture_path = Path(temporary_dir) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            errors = io.StringIO()
            with (
                patch("sys.argv", ["triage", "run", str(fixture_path)]),
                patch("triage.__main__.run_agent") as agent,
                patch("sys.stderr", errors),
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_main()
        self.assertEqual(raised.exception.code, 1)
        agent.assert_not_called()
        self.assertIn(error_message, errors.getvalue())

    def test_reject_numeric_error_message(self):
        self._assert_invalid_fixture_field(
            "error_message", 42, "Invalid error_message"
        )

    def test_reject_invalid_retry_count(self):
        self._assert_invalid_fixture_field(
            "retry_count", "n/a", "Invalid retry_count"
        )

    def test_prompt_allows_evidence_based_cluster_counts(self):
        self.assertEqual(PROMPT_VERSION, "1.3")
        self.assertNotIn("at most 3 clusters", SYSTEM_PROMPT)
        self.assertIn("do not", SYSTEM_PROMPT.lower())
        self.assertIn("arbitrary number of groups", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
