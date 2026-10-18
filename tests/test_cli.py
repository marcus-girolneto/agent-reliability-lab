import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "agent_reliability_lab.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_writes_report_and_enforces_quality_gate(tmp_path):
    destination = tmp_path / "baseline"
    result = cli("run", "--output", str(destination), "--min-pass-rate", "0.9")
    assert result.returncode == 1
    assert "11/30" in result.stdout
    assert json.loads((destination / "results.json").read_text())["summary"]["errors"] == 0
    assert cli("run", "--output", str(destination)).returncode == 2


def test_cli_rejects_invalid_rate(tmp_path):
    result = cli("run", "--output", str(tmp_path / "bad"), "--min-pass-rate", "1.1")
    assert result.returncode == 2
    assert not (tmp_path / "bad").exists()
