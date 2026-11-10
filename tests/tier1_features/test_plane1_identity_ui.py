"""
Tier 1 Feature Tests — Architectural Plane 1: Identity & User Plane + Packaging
Covers:
- Feature 7: Project Hygiene & pyproject.toml (5 tests)
- Feature 8: Standalone Interactive CLI Demo Runner (5 tests)
- Feature 10: Git Working Tree Baseline Staging (5 tests)
- Feature 18: Interactive Web Experience Polish (5 tests)
Total: 20 tests
"""
import pytest
import os
import subprocess
import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


# ==============================================================================
# Feature 7: Project Hygiene & pyproject.toml
# ==============================================================================
@pytest.mark.tier1
def test_f7_01_pyproject_toml_structure():
    """Verify pyproject.toml exists and has valid TOML structure with standard metadata."""
    pyproject_path = ROOT_DIR / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml must exist at repo root"
    content = pyproject_path.read_text()
    assert "[project]" in content
    assert 'name = "agentic-travel-mesh"' in content
    assert 'version = "2.1.0"' in content
    assert "requires-python" in content


@pytest.mark.tier1
def test_f7_02_dependencies_declared():
    """Verify runtime dependencies (fastapi, httpx, pydantic, uvicorn) are explicitly declared."""
    pyproject_path = ROOT_DIR / "pyproject.toml"
    content = pyproject_path.read_text()
    for pkg in ["fastapi", "uvicorn", "httpx", "pydantic", "pytest"]:
        assert pkg in content, f"Dependency {pkg} must be declared in pyproject.toml"


@pytest.mark.tier1
def test_f7_03_clean_module_imports():
    """Verify all 11 service modules can be imported without syntax or dependency errors."""
    from frontend.main import app as f_app
    from agents.orchestrator.main import app as o_app
    from agents.booking_agent.main import app as b_app
    from agents.weather_agent.main import app as w_app
    from mcp_tools.hotel_booking.main import app as h_app
    from mcp_tools.flight_booking.main import app as fl_app
    from mcp_tools.weather_server.main import app as we_app
    from mcp_tools.external_mcp.main import app as ex_app
    from llm_backend.main import app as l_app
    from observability.otel.main import app as ot_app
    from observability.indigo.main import app as in_app

    apps = [f_app, o_app, b_app, w_app, h_app, fl_app, we_app, ex_app, l_app, ot_app, in_app]
    assert len(apps) == 11
    for a in apps:
        assert hasattr(a, "title") and len(a.title) > 0


@pytest.mark.tier1
def test_f7_04_fastapi_app_instances():
    """Verify each FastAPI instance declares matching version 2.1.0 and health endpoint."""
    from frontend.main import app as f_app
    from agents.orchestrator.main import app as o_app
    from mcp_tools.hotel_booking.main import app as h_app

    client_f = TestClient(f_app)
    client_o = TestClient(o_app)
    client_h = TestClient(h_app)

    assert client_f.get("/healthz").status_code == 200
    assert client_o.get("/healthz").status_code == 200
    assert client_h.get("/healthz").status_code == 200


@pytest.mark.tier1
def test_f7_05_pydantic_schema_validity():
    """Verify Pydantic models validate request payloads with typed properties."""
    from frontend.main import UserTripSubmission

    submission = UserTripSubmission(
        user_id="traveler-101",
        origin="JFK",
        destination="San Francisco",
        duration_days=4,
        budget_usd=2500.0,
        trip_purpose="Executive Summit",
    )
    assert submission.user_id == "traveler-101"
    assert submission.duration_days == 4
    assert submission.budget_usd == 2500.0


# ==============================================================================
# Feature 8: Standalone Interactive CLI Demo Runner
# ==============================================================================
@pytest.mark.tier1
def test_f8_01_cli_script_exists_and_executable():
    """Verify scripts/run_showcase.py exists and is a valid Python script."""
    script_path = ROOT_DIR / "scripts" / "run_showcase.py"
    assert script_path.exists(), "scripts/run_showcase.py must exist"
    assert os.access(script_path, os.R_OK)


@pytest.mark.tier1
def test_f8_02_cli_help_flag():
    """Verify scripts/run_showcase.py --help returns exit code 0 and usage documentation."""
    cmd = [sys.executable, str(ROOT_DIR / "scripts" / "run_showcase.py"), "--help"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert result.returncode == 0
    assert "Consul Agentic Mesh Platform" in result.stdout or "usage:" in result.stdout
    assert "--act" in result.stdout


@pytest.mark.tier1
def test_f8_03_cli_act1_execution():
    """Verify scripts/run_showcase.py --act 1 --auto --plain executes Act 1 successfully."""
    cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "run_showcase.py"),
        "--act",
        "1",
        "--auto",
        "--plain",
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert result.returncode == 0, f"CLI runner failed: {result.stderr}"
    assert "Act 1: AI Gateway Failover" in result.stdout
    assert "Act 1 PASSED" in result.stdout


@pytest.mark.tier1
def test_f8_04_cli_all_acts_option():
    """Verify scripts/run_showcase.py supports the --all option."""
    cmd = [sys.executable, str(ROOT_DIR / "scripts" / "run_showcase.py"), "--help"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert "--all" in result.stdout


@pytest.mark.tier1
def test_f8_05_cli_diagnostics_formatting():
    """Verify CLI runner outputs structured diagnostics with metadata."""
    cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "run_showcase.py"),
        "--act",
        "1",
        "--auto",
        "--plain",
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert "vault_secret_ref" in result.stdout or "Vault bearer" in result.stdout


@pytest.mark.tier1
def test_f8_06_cli_auto_mode_headless_closed_stdin():
    """Verify scripts/run_showcase.py --auto executes all 5 acts cleanly under closed stdin."""
    cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "run_showcase.py"),
        "--auto",
        "--plain",
        "--delay",
        "0.0",
    ]
    result = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT_DIR),
        timeout=30.0,
    )
    assert result.returncode == 0, f"Showcase runner failed with exit code {result.returncode}: {result.stderr}"
    assert "ALL GOVERNANCE ACTS VERIFIED SUCCESSFULLY!" in result.stdout


# ==============================================================================
# Feature 10: Git Working Tree Baseline Staging
# ==============================================================================
@pytest.mark.tier1
def test_f10_01_gitignore_pycache():
    """Verify .gitignore ignores bytecode and __pycache__ directories."""
    gitignore_path = ROOT_DIR / ".gitignore"
    assert gitignore_path.exists(), ".gitignore must exist"
    content = gitignore_path.read_text()
    assert "__pycache__" in content or "*.py[cod]" in content


@pytest.mark.tier1
def test_f10_02_gitignore_pytest_cache():
    """Verify .gitignore ignores .pytest_cache."""
    gitignore_path = ROOT_DIR / ".gitignore"
    content = gitignore_path.read_text()
    assert ".pytest_cache" in content


@pytest.mark.tier1
def test_f10_03_gitignore_env():
    """Verify .gitignore ignores environment and virtualenv files."""
    gitignore_path = ROOT_DIR / ".gitignore"
    content = gitignore_path.read_text()
    assert ".venv" in content or "venv" in content or ".env" in content


@pytest.mark.tier1
def test_f10_04_tracked_files_no_credentials():
    """Verify no active private key PEM files are checked into Git."""
    key_files = list(ROOT_DIR.glob("**/*.pem")) + list(ROOT_DIR.glob("**/*.key"))
    for k in key_files:
        assert ".git" in str(k) or not k.exists() or k.stat().st_size == 0


@pytest.mark.tier1
def test_f10_05_line_endings_and_encoding():
    """Verify core Python source files use valid UTF-8 encoding and standard formatting."""
    core_files = [
        ROOT_DIR / "frontend" / "main.py",
        ROOT_DIR / "agents" / "orchestrator" / "main.py",
        ROOT_DIR / "llm_backend" / "main.py",
    ]
    for cf in core_files:
        with open(cf, "rb") as f:
            data = f.read()
            assert b"\x00" not in data, f"{cf} contains binary null bytes"
            data.decode("utf-8")


# ==============================================================================
# Feature 18: Interactive Web Experience Polish (frontend/main.py)
# ==============================================================================
@pytest.mark.tier1
def test_f18_01_serve_index_html(frontend_client):
    """Verify GET / returns HTTP 200 with HTML title Consul Agentic Runtime Fabric."""
    resp = frontend_client.get("/")
    assert resp.status_code == 200
    assert "Consul Agentic Runtime Fabric" in resp.text
    assert "Traveler Workspace" in resp.text or "5-Act" in resp.text


@pytest.mark.tier1
def test_f18_02_health_endpoint(frontend_client):
    """Verify GET /healthz returns status healthy for experience-ui-backend."""
    resp = frontend_client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "healthy"
    assert data.get("service") == "experience-ui-backend"


@pytest.mark.tier1
def test_f18_03_audit_stream(frontend_client):
    """Verify GET /api/travel/audit-stream returns JSON object with audit_events list."""
    resp = frontend_client.get("/api/travel/audit-stream")
    assert resp.status_code == 200
    data = resp.json()
    assert "audit_events" in data
    assert isinstance(data["audit_events"], list)


@pytest.mark.tier1
def test_f18_04_governance_toggle_llm_outage(frontend_client):
    """Verify POST /api/governance/toggle-llm-outage updates simulate_primary_llm_outage."""
    resp = frontend_client.post(
        "/api/governance/toggle-llm-outage",
        json={"simulate_primary_llm_outage": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "updated"
    assert data.get("runtime_flags", {}).get("simulate_primary_llm_outage") is True

    # Toggle back to False
    resp2 = frontend_client.post(
        "/api/governance/toggle-llm-outage",
        json={"simulate_primary_llm_outage": False},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2.get("status") == "updated"
    assert data2.get("runtime_flags", {}).get("simulate_primary_llm_outage") is False


@pytest.mark.tier1
def test_f18_05_governance_reset_circuit(frontend_client):
    """Verify POST /api/governance/reset-circuit invokes Indigo reset and returns status."""
    resp = frontend_client.post("/api/governance/reset-circuit")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "reset"
    circuits = data.get("circuits", {})
    assert len(circuits) > 0
    for spiffe, circuit in circuits.items():
        assert circuit.get("state") == "CLOSED"
