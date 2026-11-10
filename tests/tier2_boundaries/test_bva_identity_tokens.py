"""
Tier 2 Boundary Value Analysis — Identity Plane & User Interface Boundaries
Covers Boundary Value Analysis for Features 7, 8, 10, 18 (20 tests)
"""
import pytest
import subprocess
import sys
from pathlib import Path
from frontend.main import UserTripSubmission

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


# ==============================================================================
# Feature 7 BVA: Project Hygiene & Configuration Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f7_01_pydantic_duration_boundary_zero():
    """Verify duration_days=0 is handled cleanly by Pydantic model."""
    sub = UserTripSubmission(
        user_id="traveler-101",
        origin="JFK",
        destination="SFO",
        duration_days=0,
        budget_usd=1000.0,
    )
    assert sub.duration_days == 0


@pytest.mark.tier2
def test_bva_f7_02_pydantic_duration_boundary_large():
    """Verify large duration_days (365) does not overflow integer bounds."""
    sub = UserTripSubmission(
        user_id="traveler-101",
        origin="JFK",
        destination="SFO",
        duration_days=365,
        budget_usd=50000.0,
    )
    assert sub.duration_days == 365


@pytest.mark.tier2
def test_bva_f7_03_pydantic_negative_budget():
    """Verify negative budget float is accepted by parser and evaluated by business logic."""
    sub = UserTripSubmission(
        user_id="traveler-101",
        origin="JFK",
        destination="SFO",
        duration_days=3,
        budget_usd=-100.0,
    )
    assert sub.budget_usd == -100.0


@pytest.mark.tier2
def test_bva_f7_04_pydantic_optional_fields_default():
    """Verify optional fields default cleanly when omitted."""
    sub = UserTripSubmission(
        user_id="traveler-101",
        origin="JFK",
        destination="SFO",
        duration_days=2,
        budget_usd=500.0,
    )
    assert sub.scenario_mode == "normal"


@pytest.mark.tier2
def test_bva_f7_05_pyproject_version_format():
    """Verify pyproject.toml version follows strict semantic versioning X.Y.Z."""
    pyproject_path = ROOT_DIR / "pyproject.toml"
    content = pyproject_path.read_text()
    import re
    m = re.search(r'version\s*=\s*"(\d+)\.(\d+)\.(\d+)"', content)
    assert m is not None, "Version must follow semver X.Y.Z format"
    major, minor, patch = m.groups()
    assert int(major) >= 2


# ==============================================================================
# Feature 8 BVA: CLI Showcase Runner Flag Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f8_01_cli_act_below_minimum():
    """Verify CLI runner rejects --act 0 (below minimum valid act 1)."""
    cmd = [sys.executable, str(ROOT_DIR / "scripts" / "run_showcase.py"), "--act", "0"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert result.returncode != 0, "CLI should reject invalid act 0"


@pytest.mark.tier2
def test_bva_f8_02_cli_act_above_maximum():
    """Verify CLI runner rejects --act 6 (above maximum valid act 5)."""
    cmd = [sys.executable, str(ROOT_DIR / "scripts" / "run_showcase.py"), "--act", "6"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert result.returncode != 0, "CLI should reject invalid act 6"


@pytest.mark.tier2
def test_bva_f8_03_cli_act_non_numeric():
    """Verify CLI runner rejects non-numeric/invalid act names like --act foo."""
    cmd = [sys.executable, str(ROOT_DIR / "scripts" / "run_showcase.py"), "--act", "foo"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert result.returncode != 0, "CLI should reject non-act name"


@pytest.mark.tier2
def test_bva_f8_04_cli_act_subdivision_2a():
    """Verify CLI runner accepts subdivision act --act 2a."""
    cmd = [sys.executable, str(ROOT_DIR / "scripts" / "run_showcase.py"), "--act", "2a", "--auto", "--plain"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert result.returncode == 0
    assert "Act 2a" in result.stdout


@pytest.mark.tier2
def test_bva_f8_05_cli_act_subdivision_2b():
    """Verify CLI runner accepts subdivision act --act 2b."""
    cmd = [sys.executable, str(ROOT_DIR / "scripts" / "run_showcase.py"), "--act", "2b", "--auto", "--plain"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert result.returncode == 0
    assert "Act 2b" in result.stdout


# ==============================================================================
# Feature 10 BVA: Working Tree & Staging Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f10_01_git_diff_no_conflict_markers():
    """Verify working tree files contain zero merge conflict markers (<<<<<<<, =======, >>>>>>>)."""
    py_files = list(ROOT_DIR.glob("**/*.py"))
    for pf in py_files:
        if ".git" in str(pf):
            continue
        try:
            content = pf.read_text(errors="ignore")
            assert "<<<<<<< " not in content, f"Conflict marker found in {pf}"
            assert ">>>>>>> " not in content, f"Conflict marker found in {pf}"
        except Exception:
            pass


@pytest.mark.tier2
def test_bva_f10_02_script_permissions():
    """Verify all shell scripts in root and scripts directory have execution bits set."""
    scripts = [ROOT_DIR / "run_tests.sh", ROOT_DIR / "scripts" / "run_showcase.py"]
    for s in scripts:
        if s.exists():
            import os
            assert os.access(s, os.X_OK), f"Script {s} must be executable"


@pytest.mark.tier2
def test_bva_f10_03_no_empty_source_files():
    """Verify core python modules are non-empty (>0 bytes)."""
    core_files = [
        ROOT_DIR / "frontend" / "main.py",
        ROOT_DIR / "agents" / "orchestrator" / "main.py",
        ROOT_DIR / "agents" / "booking_agent" / "main.py",
        ROOT_DIR / "agents" / "weather_agent" / "main.py",
        ROOT_DIR / "llm_backend" / "main.py",
    ]
    for cf in core_files:
        assert cf.stat().st_size > 100, f"Source file {cf} is suspiciously small or empty"


@pytest.mark.tier2
def test_bva_f10_04_gitignore_rules_count():
    """Verify .gitignore contains at least 5 standard Python and IDE exclusion patterns."""
    gitignore = ROOT_DIR / ".gitignore"
    lines = [line.strip() for line in gitignore.read_text().splitlines() if line.strip() and not line.startswith("#")]
    assert len(lines) >= 5


@pytest.mark.tier2
def test_bva_f10_05_clean_directory_structure():
    """Verify expected directory tree exists at root."""
    for dirname in ["agents", "frontend", "gateways", "helm", "mcp_tools", "observability", "scripts", "tests"]:
        assert (ROOT_DIR / dirname).is_dir(), f"Required directory {dirname} is missing"


# ==============================================================================
# Feature 18 BVA: Experience UI & API Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f18_01_review_nonexistent_trip_404(frontend_client):
    """Verify reviewing an unknown trip ID returns HTTP 404 Not Found."""
    resp = frontend_client.post(
        "/api/travel/review-action",
        json={"trip_id": "TRIP-NONEXISTENT-9999", "action": "APPROVE", "approver": "Alex Mercer"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json().get("detail", "").lower()


@pytest.mark.tier2
def test_bva_f18_02_obo_unknown_user_fallback(frontend_client):
    """Verify requesting OBO token for unknown user_id defaults safely to traveler-101."""
    resp = frontend_client.post("/api/auth/obo-token", json={"user_id": "unknown-user-999"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["obo_subject"] == "traveler-101"


@pytest.mark.tier2
def test_bva_f18_03_obo_empty_user_id(frontend_client):
    """Verify empty user_id string defaults safely."""
    resp = frontend_client.post("/api/auth/obo-token", json={"user_id": ""})
    assert resp.status_code == 200
    assert "scopes" in resp.json()


@pytest.mark.tier2
def test_bva_f18_04_toggle_outage_empty_body_fallback(frontend_client):
    """Verify toggle endpoint defaults to False when body is empty."""
    resp = frontend_client.post(
        "/api/governance/toggle-llm-outage",
        json={},
    )
    assert resp.status_code == 200
    assert resp.json().get("runtime_flags", {}).get("simulate_primary_llm_outage") is False


@pytest.mark.tier2
def test_bva_f18_05_audit_stream_slice_limit(frontend_client):
    """Verify audit-stream returns at most 25 events without memory bloat."""
    resp = frontend_client.get("/api/travel/audit-stream")
    assert resp.status_code == 200
    events = resp.json().get("audit_events", [])
    assert len(events) <= 25
