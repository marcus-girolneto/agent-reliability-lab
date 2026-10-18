# Architecture

The implementation uses Python, Pydantic and the OpenAI SDK. The runner is deliberately small enough to read without learning an orchestration framework.

## Boundaries

`models.py` defines fixtures, diagnoses and pricing. `tools.py` owns fixture access and keeps a ledger of observed evidence. `providers.py` converts Responses API function calls into internal calls. `evaluation.py` runs strategies and grades the resulting diagnosis. `reporting.py` writes artifacts and compares paired cases. `cli.py` handles configuration and exit codes.

Only the provider adapter imports the OpenAI client. A provider implements `turn(history, tools)` and returns a `Turn`. Tests replace that interface, including its token usage, without reaching the network.

The runner passes incident text and service name to the model. It never passes the expected cause or required evidence IDs. After the run, the grader can access both the answer key and the sandbox's observation ledger. A plausible evidence ID that was never retrieved fails citation validation.

## Why function calls for the final answer?

Submitting a diagnosis is a typed action. Its schema constrains the cause vocabulary and requires evidence, a summary and a proposed next step. This makes malformed output an explicit failure instead of relying on Markdown parsing. Validation is repeated locally; API-level schema enforcement is not the only check.

The adapter follows the [official Responses function-calling flow](https://developers.openai.com/api/docs/guides/function-calling): retain response output items, execute requested tools, append matching `function_call_output` items, then continue. Reasoning output items are preserved in memory between turns. Requests use `store=False`.

## Failure handling

The sandbox returns typed errors for invalid arguments, unknown tools, unknown services and simulated outages. The agent sees recoverable tool failures and can choose to retry within its limits. The fixed strategy intentionally does not adapt.

Provider failures fail the current case and the suite continues. Reports retain exception class names without dumping exception bodies, which may contain request metadata. The CLI exits nonzero if any case has an execution error. Raw reasoning is not exported; traces include executed tools and their results, the final diagnosis, usage and scores.

Tool calls and model turns have separate limits. Model output is bounded per request and the SDK has no hidden retries. The evaluator runs sequentially to make request pressure predictable. It does not provide a total-spend circuit breaker, distributed scheduling or a service API.

## Safety scope

The model has access to synthetic evidence through two read-only tools. It cannot execute the proposed next step. Tool names and arguments are checked locally even when the provider promises strict schemas. Prompts label retrieved content as untrusted, but prompt wording alone is not a security boundary.

A real connector would need authorization, tenant separation, redaction and output-size limits. Those are outside this fixture-based sandbox. Do not substitute production logs without reviewing what is sent to the provider and written to traces.

## Reproducibility

Every report records the package version, model name, prompt hash, dataset hash and evaluation limits. Prices are supplied explicitly and stored with the run. Pin a provider model snapshot where available and record the repository commit with published experiments.

Dependency versions are bounded in `pyproject.toml`; they are not a lockfile. CI checks the supported Python range against resolved dependencies. Reproducing a published experiment exactly also requires retaining its resolved environment, model snapshot and provider settings.
