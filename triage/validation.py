import json
import math

VALID_CLASSES = {"real_bug", "flaky", "environment"}


class TriageValidationError(ValueError):
    pass


def parse_response(content):
    if not isinstance(content, str) or not content.strip():
        raise TriageValidationError("Empty model response")

    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            data, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "classifications" in data:
            return data

    raise TriageValidationError("Invalid or truncated JSON")


def validate_partial_response(response, raw_failures):
    """Validate each usable item. Missing/invalid items remain unresolved."""
    if response.finish_reason != "stop":
        raise TriageValidationError(
            f"Incomplete model response: {response.finish_reason}"
        )

    data = parse_response(response.content)
    if not isinstance(data.get("classifications"), list):
        raise TriageValidationError("Missing classifications array")
    if not isinstance(data.get("clusters"), list):
        raise TriageValidationError("Missing clusters array")

    expected = {}
    for failure in raw_failures:
        if not isinstance(failure, dict):
            raise TriageValidationError("Invalid input failure")
        key = (failure.get("test_file"), failure.get("test_title"))
        if not all(isinstance(x, str) and x.strip() for x in key):
            raise TriageValidationError("Invalid input test ID")
        if key in expected:
            raise TriageValidationError(f"Duplicate input test: {key}")
        expected[key] = failure

    seen = set()
    classified = []
    insufficient = []

    for item in data["classifications"]:
        if not isinstance(item, dict):
            raise TriageValidationError("Invalid classification object")
        key = (item.get("test_file"), item.get("test_title"))
        if key not in expected:
            raise TriageValidationError(f"Invented test: {key}")
        if key in seen:
            raise TriageValidationError(f"Duplicate test: {key}")
        seen.add(key)

        label = item.get("classification")
        if not isinstance(label, str):
            continue
        label = label.strip().lower().replace(" ", "_")
        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            continue

        if label == "unclassified":
            insufficient.append({
                "test_file": key[0],
                "test_title": key[1],
                "reason": "insufficient_evidence",
                "detail": rationale.strip(),
            })
            continue

        if label not in VALID_CLASSES:
            continue
        cluster = item.get("cluster")
        if not isinstance(cluster, str) or not cluster.strip():
            continue
        confidence = item.get("confidence")
        if isinstance(confidence, bool):
            continue
        try:
            confidence = float(confidence)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            continue

        classified.append({
            "test_file": key[0],
            "test_title": key[1],
            "cluster": cluster.strip(),
            "classification": label,
            "confidence": confidence,
            "rationale": rationale.strip(),
        })

    return classified, insufficient


def validate_response(response, raw_failures):
    """Strict validator for callers that require full classification coverage."""
    classified, insufficient = validate_partial_response(response, raw_failures)
    if insufficient or len(classified) != len(raw_failures):
        raise TriageValidationError(
            f"Incomplete classification: {len(classified)}/{len(raw_failures)}"
        )
    return classified
