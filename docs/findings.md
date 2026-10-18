# Baseline findings

The first recorded experiment runs the deterministic signature baseline on the development suite. It uses no model, no network calls and no API credits.

| Variant | Passed | Observation |
| --- | ---: | --- |
| Clean | 10/10 | Explicit signatures identify nine causes; incomplete telemetry yields unknown. |
| Injection | 1/10 | The added rate-limit signature creates conflicting matches or a false attribution. |
| Outage | 0/10 | No retry means the required log evidence is never retrieved. |

The one injection success is the actual rate-limit incident: the misleading payload happens to name the correct cause. That is not evidence of robust behavior.

The baseline cites everything it retrieves and does not assess whether runbook content supports its summary. It is useful as a reference for fixture coverage and a deliberately simple policy, not as a production incident classifier.

## What these results suggest

The fixed model strategy can test whether contextual interpretation handles a misleading signature better than literal matching. The adaptive agent can test whether recovering missing logs improves task completion enough to justify additional calls and latency.

Those are hypotheses. The repository does not include live-model results yet. Publish repeated runs with exact model IDs, environment versions, dataset and prompt hashes before drawing conclusions about a model or strategy.

The raw baseline output and every failed case are available in [the recorded artifact](../examples/baseline/results.json).
