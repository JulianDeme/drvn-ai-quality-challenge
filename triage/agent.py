import json
import os
import sys
import time
from datetime import date

from starter.fake_llm import FakeLLM, LLMError, LLMTimeoutError, RateLimitError
from starter.history_tool import GET_TEST_HISTORY_SPEC, get_test_history
from triage.prompt import SYSTEM_PROMPT
from triage.validation import TriageValidationError, validate_partial_response

MODEL = os.getenv("TRIAGE_MODEL", "drvn-sim-1.0")
MAX_ATTEMPTS = 3
MAX_TOOL_ROUNDS = 2
MAX_TOOL_CALLS = 20


class TriageError(RuntimeError):
    pass


def _test_id(item):
    return (item["test_file"], item["test_title"])


def execute_tool_calls(calls, failures, run_date, seen_call_ids=None):
    allowed_tests = {f"{f['test_file']}::{f['test_title']}" for f in failures}
    if seen_call_ids is None:
        seen_call_ids = set()
    tool_messages = []

    for call in calls:
        if not isinstance(call, dict):
            raise TriageValidationError("Invalid tool call")
        call_id = call.get("id")
        args = call.get("arguments")
        if not isinstance(call_id, str) or not call_id or call_id in seen_call_ids:
            raise TriageValidationError("Missing or duplicate tool call ID")
        seen_call_ids.add(call_id)
        if call.get("name") != "get_test_history" or not isinstance(args, dict):
            raise TriageValidationError("Unknown tool or invalid arguments")
        if set(args) - {"test_id", "before_date", "nights"}:
            raise TriageValidationError("Unexpected history tool arguments")
        test_id = args.get("test_id")
        if not isinstance(test_id, str) or test_id not in allowed_tests:
            raise TriageValidationError(f"Unknown test requested: {test_id}")
        before_date = args.get("before_date", run_date)
        try:
            if (not isinstance(before_date, str)
                    or date.fromisoformat(before_date) > date.fromisoformat(run_date)):
                raise ValueError("History date exceeds run date")
        except ValueError as error:
            raise TriageValidationError(f"Invalid history date: {before_date}") from error
        nights = args.get("nights", 5)
        if type(nights) is not int or not 1 <= nights <= 14:
            raise TriageValidationError("History nights must be an integer from 1 to 14")
        try:
            history = get_test_history(test_id, before_date=before_date, nights=nights)
        except (OSError, ValueError) as error:
            raise TriageError(f"History lookup failed for {test_id}: {error}") from error
        tool_messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(history),
        })

    return tool_messages


def run_agent(failures, run_date):
    try:
        date.fromisoformat(run_date)
    except (TypeError, ValueError) as error:
        raise TriageError("Missing or invalid run date") from error
    if not isinstance(failures, list) or not failures:
        raise TriageError("No failures supplied")

    pending = {}
    for failure in failures:
        if not isinstance(failure, dict):
            raise TriageError("Invalid input failure")
        try:
            key = _test_id(failure)
            if not all(isinstance(x, str) and x for x in key):
                raise TriageError("Invalid input test ID")
        except KeyError as error:
            raise TriageError(f"Missing input test ID: {error}") from error
        if key in pending:
            raise TriageError(f"Duplicate input test: {key}")
        if (not isinstance(failure.get("error_message"), str)
                or not failure["error_message"].strip()):
            raise TriageError("Invalid error_message: expected a non-empty string")
        if (type(failure.get("retry_count")) is not int
                or failure["retry_count"] < 0):
            raise TriageError("Invalid retry_count: expected a non-negative integer")
        pending[key] = failure

    llm = FakeLLM(seed=42)
    classified = {}
    insufficient = {}
    last_error = "No valid classification returned"
    total_tools = 0
    attempts = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not pending:
            break
        attempts = attempt
        batch = list(pending.values())
        messages = [{"role": "user", "content": json.dumps(batch)}]
        tool_rounds = 0
        tool_calls_executed = 0
        seen_call_ids = set()

        try:
            while True:
                response = llm.complete(
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    model=MODEL,
                    tools=[GET_TEST_HISTORY_SPEC],
                    max_output_tokens=8192,
                )
                if response.model != MODEL:
                    raise TriageError(f"Unexpected model: {response.model}")

                if response.finish_reason == "tool_use":
                    calls = response.tool_calls
                    if not isinstance(calls, list) or not calls:
                        raise TriageValidationError("Tool-use response without tool calls")
                    if (tool_rounds >= MAX_TOOL_ROUNDS
                            or tool_calls_executed + len(calls) > MAX_TOOL_CALLS):
                        raise TriageValidationError("Tool loop limit exceeded")
                    tool_messages = execute_tool_calls(
                        calls, batch, run_date, seen_call_ids=seen_call_ids
                    )
                    messages.append({"role": "assistant", "tool_calls": calls})
                    messages.extend(tool_messages)
                    tool_rounds += 1
                    tool_calls_executed += len(calls)
                    total_tools += len(calls)
                    continue

                if response.tool_calls:
                    raise TriageValidationError("Unexpected tool calls in final response")

                valid, undecided = validate_partial_response(response, batch)
                for item in valid:
                    key = _test_id(item)
                    classified[key] = item
                    pending.pop(key, None)
                for item in undecided:
                    key = _test_id(item)
                    insufficient[key] = item
                    pending.pop(key, None)
                last_error = f"{len(pending)} failures still unresolved"
                break

        except RateLimitError as error:
            last_error = str(error)
            delay = error.retry_after_s
        except LLMTimeoutError as error:
            last_error = str(error)
            delay = 0.5 * attempt
        except TriageValidationError as error:
            last_error = str(error)
            delay = 0
        except LLMError as error:
            raise TriageError(f"Non-retryable model error: {error}") from error
        else:
            delay = 0

        if pending and attempt < MAX_ATTEMPTS:
            print(
                f"Attempt {attempt}/{MAX_ATTEMPTS}: {last_error}. Retrying {len(pending)} pending failures...",
                file=sys.stderr,
            )
            time.sleep(delay)

    unresolved = [
        {
            "test_file": failure["test_file"],
            "test_title": failure["test_title"],
            "reason": "retry_exhausted",
            "detail": f"Not classified after {MAX_ATTEMPTS} attempts: {last_error}",
        }
        for failure in pending.values()
    ]

    return {
        "model": MODEL,
        "attempts": attempts,
        "history_tool_calls": total_tools,
        "classifications": list(classified.values()),
        "unclassified": list(insufficient.values()) + unresolved,
    }
