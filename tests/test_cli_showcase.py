"""
CAMP Travel Mesh — Automated CLI Showcase Runner Test Suite
Validates scripts/run_showcase.py under various CLI invocation patterns:
- --auto with redirected /dev/null stdin (Challenger 1 regression prevention)
- --all full automated walkthrough
- --plain plain-text diagnostic formatting
- --act <N> individual act routing (1, 2a, 2b, 2, 3, 4, 5)
- Non-interactive headless EOF resilience
"""
import pytest
import sys
import os
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SHOWCASE_SCRIPT = ROOT_DIR / "scripts" / "run_showcase.py"


@pytest.fixture
def run_cli_cmd():
    """Helper fixture to execute scripts/run_showcase.py in a subprocess with controlled stdin."""
    def _run(args, stdin=subprocess.DEVNULL, timeout=25):
        cmd = [sys.executable, str(SHOWCASE_SCRIPT)] + args
        env = {**os.environ, "PYTHONPATH": str(ROOT_DIR)}
        return subprocess.run(
            cmd,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(ROOT_DIR),
            env=env,
            timeout=timeout,
        )
    return _run


@pytest.mark.governance
def test_cli_showcase_auto_devnull(run_cli_cmd):
    """
    Verify `python3 scripts/run_showcase.py --auto < /dev/null` executes cleanly.
    Regression test for Challenger 1 Milestone 1 rejection.
    """
    result = run_cli_cmd(["--auto", "--delay", "0.0"])
    assert result.returncode == 0, f"Process crashed with stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    assert "EOF when reading a line" not in result.stderr
    assert "EOF when reading a line" not in result.stdout
    assert "ALL GOVERNANCE ACTS VERIFIED SUCCESSFULLY!" in result.stdout
    assert "Act 1: AI Gateway Failover" in result.stdout
    assert "Act 2a: Per-Tool SPIFFE Policy" in result.stdout
    assert "Act 2b: Cryptographic HITL Gate" in result.stdout
    assert "Act 3: Identity Plane OBO Delegation" in result.stdout
    assert "Act 4: Cycle Detection & Circuit Breaker" in result.stdout
    assert "Act 5: Observability & CRDs" in result.stdout


@pytest.mark.governance
def test_cli_showcase_all_devnull(run_cli_cmd):
    """Verify `python3 scripts/run_showcase.py --all < /dev/null` executes all acts without prompting."""
    result = run_cli_cmd(["--all", "--delay", "0.0"])
    assert result.returncode == 0, f"Process failed with stderr:\n{result.stderr}"
    assert "ALL GOVERNANCE ACTS VERIFIED SUCCESSFULLY!" in result.stdout


@pytest.mark.governance
def test_cli_showcase_auto_plain_devnull(run_cli_cmd):
    """Verify `python3 scripts/run_showcase.py --auto --plain < /dev/null` runs cleanly in plain format."""
    result = run_cli_cmd(["--auto", "--plain", "--delay", "0.0"])
    assert result.returncode == 0
    assert "Consul Agentic Runtime Fabric (CAMP) Showcase" in result.stdout
    assert "ALL GOVERNANCE ACTS VERIFIED SUCCESSFULLY!" in result.stdout
    # Verify plain output lacks Rich box drawing artifacts
    assert "╭" not in result.stdout
    assert "╰" not in result.stdout


@pytest.mark.governance
def test_cli_showcase_headless_fallback_resilience(run_cli_cmd):
    """
    Verify `python3 scripts/run_showcase.py < /dev/null` (interactive invocation with EOF stdin)
    does not crash with unhandled EOFError.
    """
    result = run_cli_cmd(["--delay", "0.0"])
    assert result.returncode == 0, f"Failed on redirected EOF stdin:\n{result.stderr}"
    assert "EOF when reading a line" not in result.stderr
    assert "ALL GOVERNANCE ACTS VERIFIED SUCCESSFULLY!" in result.stdout


@pytest.mark.governance
@pytest.mark.parametrize("act_id,expected_label", [
    ("1", "Act 1: AI Gateway Failover"),
    ("2a", "Act 2a: Per-Tool SPIFFE Policy"),
    ("2b", "Act 2b: Cryptographic HITL Gate"),
    ("2", "Act 2a: Per-Tool SPIFFE Policy"),
    ("3", "Act 3: Identity Plane OBO Delegation"),
    ("4", "Act 4: Cycle Detection & Circuit Breaker"),
    ("5", "Act 5: Observability & CRDs"),
])
def test_cli_showcase_individual_acts(run_cli_cmd, act_id, expected_label):
    """Verify each act can be invoked individually via --act <N> under /dev/null stdin."""
    result = run_cli_cmd(["--act", act_id, "--delay", "0.0"])
    assert result.returncode == 0, f"Act {act_id} failed:\n{result.stderr}"
    assert expected_label in result.stdout
    assert "ALL GOVERNANCE ACTS VERIFIED SUCCESSFULLY!" in result.stdout
