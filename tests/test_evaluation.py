import json
from pathlib import Path

import pytest

from agent_reliability_lab.evaluation import evaluate, grade, load_cases, run_case
from agent_reliability_lab.models import Call, Diagnosis, Prices, Usage
from agent_reliability_lab.providers import Turn
from agent_reliability_lab.reporting import compare, save
from agent_reliability_lab.tools import Sandbox

DATASET = Path(__file__).parents[1] / "datasets/incidents.jsonl"


@pytest.fixture
def case():
    return load_cases(DATASET)[0]


class FakeProvider:
    model = "test-double"

    def __init__(self, calls):
        self.calls = iter(calls)
        self.histories = []

    def turn(self, history, tools):
        self.histories.append(json.loads(json.dumps(history)))
        call = next(self.calls)
        if isinstance(call, Exception):
            raise call
        return Turn([call], [], [str(len(self.histories))], Usage(input_tokens=10, output_tokens=5))


def answer(case, evidence=None, cause=None):
    return Diagnosis(
        cause=cause or case.expected.cause,
        evidence_ids=evidence if evidence is not None else case.expected.required_evidence,
        summary="Observed evidence is consistent with this diagnosis.",
        next_step="Inspect the relevant service metrics.",
    )


def submit(case, **kwargs):
    return Call(name="submit_diagnosis", arguments=answer(case, **kwargs).model_dump())


def test_unobserved_citations_fail_even_when_the_cause_is_right(case):
    score = grade(case, answer(case), Sandbox(case))
    assert score["cause_correct"]
    assert not score["citations_valid"]
    assert not score["passed"]


def test_missing_required_evidence_fails(case):
    sandbox = Sandbox(case)
    sandbox.execute("read_logs", {"service": case.service})
    score = grade(case, answer(case, evidence=["L1"]), sandbox)
    assert score["citations_valid"]
    assert score["evidence_recall"] == 0.5
    assert not score["passed"]


def test_fabricated_citation_fails(case):
    sandbox = Sandbox(case)
    sandbox.execute("read_logs", {"service": case.service})
    sandbox.execute("search_runbooks", {"query": ""})
    score = grade(case, answer(case, evidence=["L1", "R1", "invented"]), sandbox)
    assert not score["passed"]
    assert score["citation_precision"] == pytest.approx(2 / 3)


def test_agent_recovers_from_transient_outage():
    case = load_cases(DATASET)[2]
    provider = FakeProvider(
        [
            Call(name="read_logs", arguments={"service": case.service}),
            Call(name="read_logs", arguments={"service": case.service}),
            Call(name="search_runbooks", arguments={"query": ""}),
            submit(case),
        ]
    )
    result = run_case(case, "agent", provider)
    assert result["scores"]["passed"]
    assert result["tool_calls"] == 3
    assert result["trace"][0]["result"]["retryable"]
    assert result["usage"]["input_tokens"] == 40
    first_input = json.loads(provider.histories[0][0]["content"])
    assert set(first_input) == {"service", "incident"}
    assert "expected" not in json.dumps(provider.histories)
    assert "required_evidence" not in json.dumps(provider.histories)


def test_fixed_strategy_has_evidence_before_calling_model(case):
    provider = FakeProvider([submit(case)])
    result = run_case(case, "fixed", provider)
    assert result["scores"]["passed"]
    assert result["tool_calls"] == 2
    assert len(provider.histories) == 1
    assert "untrusted_evidence" in provider.histories[0][1]["content"]


def test_tool_budget_stops_a_loop(case):
    provider = FakeProvider([Call(name="read_logs", arguments={"service": case.service})] * 5)
    result = run_case(case, "agent", provider, max_tool_calls=2)
    assert result["error"] == "tool_budget_exceeded"
    assert result["tool_calls"] == 2
    assert not result["scores"]["passed"]


def test_turn_budget_stops_a_loop(case):
    provider = FakeProvider([Call(name="read_logs", arguments={"service": case.service})] * 5)
    result = run_case(case, "agent", provider, max_turns=2)
    assert result["error"] == "turn_budget_exceeded"
    assert result["model_turns"] == 2


def test_provider_failure_is_recorded_without_exception_body(case):
    result = run_case(case, "agent", FakeProvider([TimeoutError("private metadata")]))
    assert result["error"] == "TimeoutError"
    assert "private metadata" not in json.dumps(result)
    assert not result["scores"]["passed"]


def test_malformed_diagnosis_fails(case):
    provider = FakeProvider([Call(name="submit_diagnosis", arguments={"cause": "unknown"})])
    result = run_case(case, "agent", provider)
    assert result["error"] == "ValidationError"
    assert result["diagnosis"] is None


@pytest.mark.parametrize(
    "name,arguments,error",
    [
        ("shell", {"command": "whoami"}, "unknown_tool"),
        ("read_logs", {"service": "other"}, "unknown_service"),
        ("read_logs", {"service": 42}, "invalid_arguments"),
        ("search_runbooks", {"query": "", "extra": True}, "invalid_arguments"),
    ],
)
def test_tool_boundary(case, name, arguments, error):
    sandbox = Sandbox(case)
    assert sandbox.execute(name, arguments)["error"] == error
    assert not sandbox.observed


def test_runbook_search_does_not_expose_nonmatching_evidence(case):
    sandbox = Sandbox(case)
    assert sandbox.execute("search_runbooks", {"query": "unrelatedzzzz"}) == {"records": []}
    assert not sandbox.observed
    assert sandbox.execute("search_runbooks", {"query": "pool"})["records"]
    assert set(sandbox.observed) == {"R1"}


def test_baseline_exposes_failures_without_oracle_lookup():
    run = evaluate(DATASET, "baseline")
    assert run["summary"]["passed"] == 11
    assert run["by_variant"]["clean"]["passed"] == 10
    assert run["by_variant"]["injection"]["passed"] == 1
    assert run["by_variant"]["outage"]["passed"] == 0
    assert run["estimated_cost_usd"] == 0


def test_abstention_is_not_automatically_a_pass():
    known, unknown = load_cases(DATASET)[0], load_cases(DATASET)[-3]
    assert run_case(unknown, "baseline")["scores"]["passed"]
    sandbox = Sandbox(known)
    sandbox.execute("read_logs", {"service": known.service})
    sandbox.execute("search_runbooks", {"query": ""})
    assert not grade(known, answer(known, cause="unknown"), sandbox)["passed"]


def test_cached_tokens_are_not_double_charged():
    prices = Prices(input_per_million=2, cached_input_per_million=1, output_per_million=4)
    usage = Usage(input_tokens=1000, cached_input_tokens=200, output_tokens=100)
    assert prices.estimate(usage) == pytest.approx(0.0022)


def test_reports_refuse_overwrite_and_compare_dataset_changes(tmp_path):
    run = evaluate(DATASET, "baseline")
    destination = tmp_path / "result"
    save(run, destination)
    assert json.loads((destination / "results.json").read_text())["summary"]["cases"] == 30
    assert "11/30" in (destination / "report.md").read_text()
    with pytest.raises(FileExistsError):
        save(run, destination)
    assert "0 gains, 0 regressions" in compare(run, run)
    changed = {**run, "dataset_sha256": "different"}
    with pytest.raises(ValueError, match="same dataset"):
        compare(run, changed)


def test_unknown_prices_stay_unknown(tmp_path, case):
    dataset = tmp_path / "case.jsonl"
    dataset.write_text(case.model_dump_json() + "\n")
    run = evaluate(dataset, "fixed", FakeProvider([submit(case)]))
    assert run["estimated_cost_usd"] is None
    assert run["results"][0]["estimated_cost_usd"] is None


def test_duplicate_case_ids_are_rejected(tmp_path, case):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text((case.model_dump_json() + "\n") * 2)
    with pytest.raises(ValueError, match="unique"):
        load_cases(dataset)
