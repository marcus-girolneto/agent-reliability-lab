import hashlib
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from . import __version__
from .baseline import diagnose
from .models import Case, Diagnosis, Prices, Usage
from .providers import SYSTEM
from .tools import READ_TOOLS, SUBMIT, Sandbox


def load_cases(path: Path) -> list[Case]:
    cases = [
        Case.model_validate(json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    if not cases or len({case.id for case in cases}) != len(cases):
        raise ValueError("Dataset must be nonempty and case IDs must be unique")
    return cases


def grade(case: Case, diagnosis: Diagnosis | None, sandbox: Sandbox) -> dict:
    cited = set(diagnosis.evidence_ids) if diagnosis else set()
    observed = set(sandbox.observed)
    required = set(case.expected.required_evidence)
    correct = bool(diagnosis and diagnosis.cause == case.expected.cause)
    valid = bool(cited) and cited <= observed
    covered = required <= cited
    return {
        "passed": correct and valid and covered,
        "cause_correct": correct,
        "citations_valid": valid,
        "required_evidence_covered": covered,
        "citation_precision": len(cited & observed) / len(cited) if cited else 0.0,
        "evidence_recall": len(cited & required) / len(required),
        "abstained": bool(diagnosis and diagnosis.cause == "unknown"),
    }


def run_case(
    case: Case,
    strategy: Literal["baseline", "fixed", "agent"],
    provider=None,
    max_turns: int = 6,
    max_tool_calls: int = 8,
) -> dict:
    start = time.perf_counter()
    sandbox = Sandbox(case)
    diagnosis, error = None, None
    usage, turns = Usage(), 0
    if strategy != "baseline" and provider is None:
        raise ValueError("A provider is required for model-backed strategies")
    if max_turns < 1 or max_tool_calls < 2:
        raise ValueError("Use at least one model turn and two tool calls")
    try:
        if strategy == "baseline":
            diagnosis = diagnose(sandbox)
        else:
            history = [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "service": case.service,
                            "incident": case.incident,
                        }
                    ),
                }
            ]
            if strategy == "fixed":
                evidence = [
                    sandbox.execute("read_logs", {"service": case.service}),
                    sandbox.execute("search_runbooks", {"query": ""}),
                ]
                history.append(
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "untrusted_evidence": evidence,
                            }
                        ),
                    }
                )
            for _ in range(max_turns):
                tools = [SUBMIT] if strategy == "fixed" else [*READ_TOOLS, SUBMIT]
                turn = provider.turn(history, tools)
                turns += 1
                for key in Usage.model_fields:
                    setattr(usage, key, getattr(usage, key) + getattr(turn.usage, key))
                history.extend(turn.output)
                if not turn.calls:
                    error = "no_tool_call"
                    break
                if len(turn.calls) != len(turn.call_ids):
                    error = "invalid_provider_response"
                    break
                for call, call_id in zip(turn.calls, turn.call_ids, strict=True):
                    if call.name == "submit_diagnosis":
                        diagnosis = Diagnosis.model_validate(call.arguments)
                        break
                    if strategy == "fixed":
                        error = "tool_not_allowed"
                        break
                    if len(sandbox.events) >= max_tool_calls:
                        error = "tool_budget_exceeded"
                        break
                    result = sandbox.execute(call.name, call.arguments)
                    history.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(result),
                        }
                    )
                if diagnosis or error:
                    break
            if not diagnosis and not error:
                error = "turn_budget_exceeded"
    except Exception as exc:
        error = type(exc).__name__
    return {
        "case_id": case.id,
        "family": case.family,
        "variant": case.variant,
        "diagnosis": diagnosis.model_dump() if diagnosis else None,
        "expected": case.expected.model_dump(),
        "scores": grade(case, diagnosis, sandbox),
        "error": error,
        "usage": usage.model_dump(),
        "model_turns": turns,
        "tool_calls": len(sandbox.events),
        "trace": sandbox.events,
        "latency_ms": round((time.perf_counter() - start) * 1000, 3),
    }


def summarize(results: list[dict]) -> dict:
    n = len(results)
    if not n:
        raise ValueError("Cannot summarize an empty run")
    successes = sum(row["scores"]["passed"] for row in results)
    p, z = successes / n, 1.96
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    latency = sorted(row["latency_ms"] for row in results)
    return {
        "cases": n,
        "passed": successes,
        "pass_rate": p,
        "pass_rate_wilson_95": [max(0, center - margin), min(1, center + margin)],
        "cause_accuracy": sum(r["scores"]["cause_correct"] for r in results) / n,
        "citation_validity_rate": sum(r["scores"]["citations_valid"] for r in results) / n,
        "errors": sum(r["error"] is not None for r in results),
        "latency_p50_ms": latency[math.ceil(n * 0.50) - 1],
        "latency_p95_ms": latency[math.ceil(n * 0.95) - 1],
        "tool_calls": sum(r["tool_calls"] for r in results),
    }


def evaluate(
    dataset: Path,
    strategy: str,
    provider=None,
    max_turns: int = 6,
    max_tool_calls: int = 8,
    prices: Prices | None = None,
) -> dict:
    cases = load_cases(dataset)
    results = [run_case(case, strategy, provider, max_turns, max_tool_calls) for case in cases]
    for row in results:
        row["estimated_cost_usd"] = (
            0.0
            if strategy == "baseline"
            else prices.estimate(Usage(**row["usage"]))
            if prices
            else None
        )
    return {
        "schema_version": 1,
        "version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "strategy": strategy,
        "model": getattr(provider, "model", None),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
        "config": {
            "max_turns": max_turns,
            "max_tool_calls": max_tool_calls,
            "prices": prices.model_dump() if prices else None,
        },
        "summary": summarize(results),
        "by_variant": {
            variant: summarize([r for r in results if r["variant"] == variant])
            for variant in sorted({r["variant"] for r in results})
        },
        "estimated_cost_usd": (
            sum(r["estimated_cost_usd"] for r in results)
            if all(r["estimated_cost_usd"] is not None for r in results)
            else None
        ),
        "results": results,
    }
