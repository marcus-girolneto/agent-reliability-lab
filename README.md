# Agent Reliability Lab

[![CI](https://github.com/marcus-girolneto/agent-reliability-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/marcus-girolneto/agent-reliability-lab/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An incident-response agent can produce a convincing diagnosis without checking the right evidence. This project measures that gap.

It runs three investigation strategies against the same incidents, records tool calls and token usage, and scores the diagnosis against a separate answer key. A correct label is not enough: the agent must cite evidence it actually retrieved and include the evidence required by the case.

**Status:** working evaluation harness with an offline baseline and an OpenAI Responses adapter. The checked-in results are from the rule baseline. No live-model performance claims yet.

## Try it

```bash
git clone https://github.com/marcus-girolneto/agent-reliability-lab.git
cd agent-reliability-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
agent-lab run --strategy baseline --output runs/baseline
cat runs/baseline/report.md
```

No API key is needed for the baseline. Each run writes `results.json` with full tool traces and a readable `report.md`. Output directories cannot be overwritten accidentally.

## What is being compared?

| Strategy | Evidence collection | Diagnosis | Purpose |
| --- | --- | --- | --- |
| `baseline` | Read logs, then fetch runbooks once | Explicit log-signature rules | Cheap reference and harness smoke test |
| `fixed` | Same two calls, without retries | Model | Isolates the value of model interpretation |
| `agent` | Model chooses tools and can retry | Model | Measures the value and cost of adaptive investigation |

The sandbox exposes only `read_logs(service)` and `search_runbooks(query)`. The agent submits a typed diagnosis through `submit_diagnosis`. No shell, network access, or remediation tools are exposed to the model.

```mermaid
flowchart LR
    D[Incident fixture] --> S[Tool sandbox]
    D --> O[Answer key]
    I[Incident description] --> R[Strategy runner]
    R <--> S
    R <--> P[Model adapter]
    R --> T[Diagnosis and trace]
    T --> G[Deterministic grader]
    O --> G
    G --> A[JSON and Markdown reports]
```

The model receives the incident description and retrieved tool results. The answer key stays in the evaluation process. This is a data boundary for evaluation integrity, not process isolation from arbitrary Python code.

## Run a model

Set `OPENAI_API_KEY` in your shell. `.env.example` documents the variables; the CLI does not automatically load `.env` files. Choose a model available to your account that supports Responses function calling and structured function arguments.

```bash
export OPENAI_MODEL='your-model-id'
agent-lab run --strategy fixed --output runs/fixed
agent-lab run --strategy agent --output runs/agent
agent-lab compare runs/fixed/results.json runs/agent/results.json
```

To compare two models, repeat the agent run with `--model MODEL_A` and `--model MODEL_B`, using distinct output directories. Both runs must use exactly the same dataset. Model calls incur API charges.

`--max-turns` defaults to 6 and `--max-tool-calls` to 8 per case. Each model request has a 30-second timeout and a 1,500-token output limit. SDK retries are disabled so provider failures remain visible. These limits are not a dollar budget or a whole-run deadline.

For cost estimates, pass `--prices path/to/prices.json`:

```json
{
  "input_per_million": 1.0,
  "cached_input_per_million": 0.5,
  "output_per_million": 4.0
}
```

Those are example rates, **not current model prices**. Supply the rates for the chosen model. Missing prices produce `null`, not a zero-cost claim. Estimates cover reported token usage; they are not billing records.

## Dataset and scoring

There are **10 synthetic incident families, each with 3 variants**: clean evidence, an injected instruction inside a log entry, and a transient log-tool outage. Nine families have a known root cause; one requires abstention. All fixtures are inspectable in [the dataset](datasets/incidents.jsonl).

A case passes only when all three conditions hold:

1. The cause matches the answer key, including `unknown` where appropriate.
2. Every cited evidence ID was actually returned by a tool, and at least one was cited.
3. The diagnosis cites all evidence required by the case.

Reports also include cause accuracy, citation validity, evidence recall, tool calls, errors, latency, usage and optional cost. See the [evaluation protocol](docs/evaluation.md) for limitations and how to extend the benchmark.

## Recorded baseline

The [checked-in run](examples/baseline/report.md) is an actual local execution of the rule baseline. It passes **11/30 cases**: 10 clean, 1 injection and 0 outage variants.

This is deliberately a small, brittle baseline. The injected log contains a misleading error signature, so matching strings can select the wrong cause. An outage hides the required log evidence, and this strategy does not retry. These failures give model-backed strategies something specific to improve on.

A baseline failure on an injected payload is evidence contamination, not proof that an LLM obeyed malicious instructions. The current rubric measures task success under injection; it does not establish general prompt-injection resistance.

## Development

```bash
ruff check .
ruff format --check .
pytest -q
```

CI runs these checks on Python 3.11–3.13 and uploads a baseline report. Tests use a fake provider and an HTTP transport stub; they do not spend API credits. The CLI returns a nonzero exit code for execution errors or when `--min-pass-rate` is not met. An incorrect diagnosis alone is a scored outcome, not an execution error.

```bash
docker build -t agent-reliability-lab .
docker run --rm agent-reliability-lab
```

The default container runs the offline baseline. To retain its report, copy `/app/runs/baseline` from a named container or mount a writable directory at `/app/runs`.

## Design notes

- [Architecture and trade-offs](docs/architecture.md)
- [Evaluation protocol and limitations](docs/evaluation.md)
- [Baseline findings](docs/findings.md)

The next useful experiment is a repeated fixed-versus-agent comparison on a private holdout with a mix of recoverable and persistent failures. More fixtures matter more than another orchestration framework.
