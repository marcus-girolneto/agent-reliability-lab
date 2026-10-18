import json
from pathlib import Path


def markdown(run: dict) -> str:
    summary = run["summary"]
    low, high = summary["pass_rate_wilson_95"]
    cost = run["estimated_cost_usd"]
    cost_label = "unavailable (no price configuration)" if cost is None else f"${cost:.6f}"
    lines = [
        "# Evaluation report",
        "",
        f"Strategy: **{run['strategy']}** · Model: **{run['model'] or 'none (rule baseline)'}**",
        "",
        f"Dataset SHA-256: `{run['dataset_sha256']}`",
        "",
        f"Passed: **{summary['passed']}/{summary['cases']}** ({summary['pass_rate']:.1%}).",
        f"Descriptive Wilson interval: {low:.1%}–{high:.1%}.",
        "Variants share incident families; this interval is not a generalization claim.",
        "",
        f"Cause accuracy: {summary['cause_accuracy']:.1%}. "
        f"Citation validity: {summary['citation_validity_rate']:.1%}.",
        f"Latency p50 / p95: {summary['latency_p50_ms']:.1f} / "
        f"{summary['latency_p95_ms']:.1f} ms. Tool calls: {summary['tool_calls']}.",
        f"Estimated API cost: {cost_label}.",
        "",
        "## By variant",
        "",
        "| Variant | Passed | Rate | Errors |",
        "| --- | ---: | ---: | ---: |",
    ]
    for variant, stats in run["by_variant"].items():
        lines.append(
            f"| {variant} | {stats['passed']}/{stats['cases']} | "
            f"{stats['pass_rate']:.1%} | {stats['errors']} |"
        )
    lines += [
        "",
        "## Cases",
        "",
        "| Case | Passed | Cause | Error |",
        "| --- | :---: | --- | --- |",
    ]
    for row in run["results"]:
        cause = row["diagnosis"]["cause"] if row["diagnosis"] else "—"
        lines.append(
            f"| {row['case_id']} | {'yes' if row['scores']['passed'] else 'no'} | "
            f"{cause} | {row['error'] or '—'} |"
        )
    lines += ["", "Full tool traces and per-case scores are in the adjacent JSON file.", ""]
    return "\n".join(lines)


def save(run: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "results.json").write_text(json.dumps(run, indent=2) + "\n")
    (directory / "report.md").write_text(markdown(run))


def compare(left: dict, right: dict) -> str:
    if left["dataset_sha256"] != right["dataset_sha256"]:
        raise ValueError("Runs must use the same dataset bytes")
    a = {r["case_id"]: r for r in left["results"]}
    b = {r["case_id"]: r for r in right["results"]}
    if a.keys() != b.keys():
        raise ValueError("Runs must contain the same cases")
    gained = [key for key in a if not a[key]["scores"]["passed"] and b[key]["scores"]["passed"]]
    lost = [key for key in a if a[key]["scores"]["passed"] and not b[key]["scores"]["passed"]]
    delta = right["summary"]["pass_rate"] - left["summary"]["pass_rate"]
    return "\n".join(
        [
            "# Paired run comparison",
            "",
            f"Left: {left['strategy']} / {left['model'] or 'rules'}",
            f"Right: {right['strategy']} / {right['model'] or 'rules'}",
            "",
            f"Pass-rate change: {delta:+.1%} ({len(gained)} gains, {len(lost)} regressions).",
            "",
            "Gains: " + (", ".join(gained) or "none"),
            "Regressions: " + (", ".join(lost) or "none"),
            "",
            "This is a paired descriptive comparison, not a significance test.",
            "",
        ]
    )
