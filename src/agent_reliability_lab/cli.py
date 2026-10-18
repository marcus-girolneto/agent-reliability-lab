import argparse
import json
import os
import sys
from pathlib import Path

from .evaluation import evaluate
from .models import Prices
from .providers import OpenAIProvider
from .reporting import compare, save


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Evaluate incident-response agents against evidence."
    )
    commands = root.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run a baseline or model-backed evaluation")
    run.add_argument("--dataset", type=Path, default=Path("datasets/incidents.jsonl"))
    run.add_argument("--strategy", choices=["baseline", "fixed", "agent"], default="baseline")
    run.add_argument("--model", default=os.environ.get("OPENAI_MODEL"))
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--max-turns", type=positive_int, default=6)
    run.add_argument("--max-tool-calls", type=positive_int, default=8)
    run.add_argument("--prices", type=Path, help="JSON containing per-million token prices")
    run.add_argument("--min-pass-rate", type=float, default=0.0)
    diff = commands.add_parser("compare", help="Compare two runs on identical cases")
    diff.add_argument("left", type=Path)
    diff.add_argument("right", type=Path)
    return root


def main() -> int:
    root = parser()
    args = root.parse_args()
    try:
        if args.command == "compare":
            print(compare(json.loads(args.left.read_text()), json.loads(args.right.read_text())))
            return 0
        if args.output.exists():
            root.error("output directory already exists; choose a new run directory")
        if not 0 <= args.min_pass_rate <= 1:
            root.error("--min-pass-rate must be between 0 and 1")
        if args.max_tool_calls < 2:
            root.error("--max-tool-calls must be at least 2")
        provider = None
        if args.strategy != "baseline":
            if not args.model or not os.environ.get("OPENAI_API_KEY"):
                root.error("model runs require --model (or OPENAI_MODEL) and OPENAI_API_KEY")
            provider = OpenAIProvider(args.model)
        prices = Prices.model_validate_json(args.prices.read_text()) if args.prices else None
        run = evaluate(
            args.dataset, args.strategy, provider, args.max_turns, args.max_tool_calls, prices
        )
        save(run, args.output)
        summary = run["summary"]
        print(f"{summary['passed']}/{summary['cases']} passed ({summary['pass_rate']:.1%})")
        print(f"Report: {args.output / 'report.md'}")
        return int(summary["errors"] > 0 or summary["pass_rate"] < args.min_pass_rate)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
