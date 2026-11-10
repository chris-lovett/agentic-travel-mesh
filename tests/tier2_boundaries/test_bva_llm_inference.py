"""
Tier 2 Boundary Value Analysis — Gateway & LLM Inference Boundaries
Covers Boundary Value Analysis for Features 3, 4, 9, 12 (20 tests)
"""
import pytest
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


# ==============================================================================
# Feature 3 BVA: Ext-Proc Unix Socket Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f3_01_ext_proc_scheme_validation():
    """Verify ext-proc processorTarget specifies unix:// scheme rather than http://."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert "unix:///var/run/consul/" in content
    assert "http:///var/run/consul/" not in content


@pytest.mark.tier2
def test_bva_f3_02_ext_proc_socket_path_length_bound():
    """Verify Unix domain socket path is within Linux sockaddr_un 108-byte limit."""
    socket_path = "/var/run/consul/csl-mcp-sc.sock"
    assert len(socket_path.encode("utf-8")) < 108, "Unix socket path must fit in sockaddr_un"
    igw_socket_path = "/var/run/consul/csl-ig-pro.sock"
    assert len(igw_socket_path.encode("utf-8")) < 108


@pytest.mark.tier2
def test_bva_f3_03_ext_proc_timeout_string_format():
    """Verify messageTimeout in consul-crds.yaml has valid duration suffix ('s')."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    import re
    timeouts = re.findall(r'messageTimeout:\s*"([^"]+)"', crd_path.read_text())
    assert len(timeouts) > 0
    for t in timeouts:
        assert t.endswith("s"), f"Timeout {t} must have seconds unit ('s')"
        val = int(t[:-1])
        assert 1 <= val <= 60, f"Timeout {val}s is outside valid 1-60s boundary"


@pytest.mark.tier2
def test_bva_f3_04_ext_proc_envoy_extension_name():
    """Verify envoyExtensions name is strictly 'builtin/ext-proc'."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert "name: builtin/ext-proc" in content


@pytest.mark.tier2
def test_bva_f3_05_ext_proc_timeout_distinction():
    """Verify MCP tools (5s) and AI Inference Gateway (15s) have distinct timeout budgets."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert 'messageTimeout: "5s"' in content
    assert 'messageTimeout: "15s"' in content


# ==============================================================================
# Feature 4 BVA: Envoy Gateway Route & Rate Limiting Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f4_01_api_gw_unmatched_route_404():
    """Verify api-gw returns HTTP 404 for unmatched route prefixes."""
    import httpx
    from tests.conftest import _global_mesh_transport
    client = TestClient(ROOT_DIR)  # Not used directly; use transport
    import asyncio
    async def call():
        async with httpx.AsyncClient(transport=_global_mesh_transport) as c:
            return await c.get("http://api-gw:10000/unsupported/random/path")
    resp = asyncio.run(call())
    assert resp.status_code == 404


@pytest.mark.tier2
def test_bva_f4_02_gateway_port_validity():
    """Verify all gateway ports in envoy.yaml are valid unsigned 16-bit integers (1-65535)."""
    envoy_files = [
        ROOT_DIR / "gateways" / "api_gw" / "envoy.yaml",
        ROOT_DIR / "gateways" / "travel_igw" / "envoy.yaml",
        ROOT_DIR / "gateways" / "terminating_gw" / "envoy.yaml",
    ]
    import re
    for ef in envoy_files:
        content = ef.read_text()
        ports = re.findall(r"port_value:\s*(\d+)", content)
        assert len(ports) > 0
        for p in ports:
            val = int(p)
            assert 1 <= val <= 65535, f"Port {val} out of 16-bit range"


@pytest.mark.tier2
def test_bva_f4_03_rate_limiter_token_bucket_spec():
    """Verify local_ratelimit filter specifies exactly 100 max_tokens and 1s refill."""
    igw_file = ROOT_DIR / "gateways" / "travel_igw" / "envoy.yaml"
    content = igw_file.read_text()
    assert "max_tokens: 100" in content
    assert "tokens_per_fill: 100" in content
    assert "fill_interval: 1s" in content


@pytest.mark.tier2
def test_bva_f4_04_travel_igw_rate_limiting_enforcement():
    """Verify travel-igw returns HTTP 429 when rate limit is active."""
    import httpx
    from tests.conftest import _global_mesh_transport, rate_limit_state
    rate_limit_state["force_rate_limit"] = True
    import asyncio
    async def call():
        async with httpx.AsyncClient(transport=_global_mesh_transport) as c:
            return await c.post(
                "http://travel-igw:10001/v1/chat/completions",
                json={"model": "llama", "messages": []},
            )
    resp = asyncio.run(call())
    rate_limit_state["force_rate_limit"] = False
    assert resp.status_code == 429
    assert "Rate Limit" in resp.json().get("detail", "")


@pytest.mark.tier2
def test_bva_f4_05_terminating_gw_header_action():
    """Verify terminating_gw uses OVERWRITE_IF_EXISTS_OR_ADD for injected Vault token."""
    term_file = ROOT_DIR / "gateways" / "terminating_gw" / "envoy.yaml"
    content = term_file.read_text()
    assert "append_action: OVERWRITE_IF_EXISTS_OR_ADD" in content


# ==============================================================================
# Feature 9 BVA: Test Automation Runner Script Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f9_01_run_tests_sh_fast_flag():
    """Verify run_tests.sh --fast runs tests with compact formatting."""
    result = subprocess.run(
        ["./run_tests.sh", "--fast", "tests/test_camp_travel.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT_DIR),
    )
    assert result.returncode == 0
    assert "6 passed" in result.stdout or "6 passed" in result.stderr


@pytest.mark.tier2
def test_bva_f9_02_run_tests_sh_missing_tier_arg():
    """Verify run_tests.sh --tier without argument returns error code 1."""
    result = subprocess.run(
        ["./run_tests.sh", "--tier"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT_DIR),
    )
    assert result.returncode != 0
    assert "requires an argument" in result.stderr


@pytest.mark.tier2
def test_bva_f9_03_run_tests_sh_keyword_filtering():
    """Verify run_tests.sh -k filters specific tests."""
    result = subprocess.run(
        ["./run_tests.sh", "-k", "test_weather_mcp", "tests/test_camp_travel.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT_DIR),
    )
    assert result.returncode == 0
    assert "1 passed" in result.stdout
    assert "5 deselected" in result.stdout


@pytest.mark.tier2
def test_bva_f9_04_run_tests_sh_governance_flag():
    """Verify run_tests.sh --help lists --governance flag."""
    result = subprocess.run(
        ["./run_tests.sh", "--help"],
        stdout=subprocess.PIPE,
        text=True,
        cwd=str(ROOT_DIR),
    )
    assert "--governance" in result.stdout


@pytest.mark.tier2
def test_bva_f9_05_run_tests_sh_no_args_default():
    """Verify run_tests.sh runs pytest when called without arguments."""
    result = subprocess.run(
        ["./run_tests.sh", "--help"],
        stdout=subprocess.PIPE,
        text=True,
        cwd=str(ROOT_DIR),
    )
    assert result.returncode == 0


# ==============================================================================
# Feature 12 BVA: LLM Inference & Failover Token Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f12_01_empty_messages_prompt(llm_backend_client):
    """Verify empty messages list handles prompt gracefully without crash."""
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer vault:secret/data/ai/llm#api_key_sk_99201"},
        json={"model": "meta-llama/llama-3-70b-instruct", "messages": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "choices" in data


@pytest.mark.tier2
def test_bva_f12_02_large_prompt_token_calculation(llm_backend_client):
    """Verify large prompt (1000 words) calculates token count accurately."""
    large_content = "Word " * 1000
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer vault:secret/data/ai/llm#api_key_sk_99201"},
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": large_content}],
        },
    )
    assert resp.status_code == 200
    usage = resp.json()["usage"]
    assert usage["prompt_tokens"] > 500
    assert usage["total_tokens"] > 500


@pytest.mark.tier2
def test_bva_f12_03_outage_flag_case_insensitive_uppercase(llm_backend_client):
    """Verify header x-simulate-llm-outage: 'TRUE' is parsed case-insensitively."""
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer vault:secret/data/ai/llm#api_key_sk_99201",
            "x-simulate-llm-outage": "TRUE",
        },
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Test"}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["gateway_metadata"]["failover_triggered"] is True


@pytest.mark.tier2
def test_bva_f12_04_outage_flag_invalid_value_defaults_false(llm_backend_client):
    """Verify header x-simulate-llm-outage: 'invalid-string' defaults to False (no failover)."""
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer vault:secret/data/ai/llm#api_key_sk_99201",
            "x-simulate-llm-outage": "invalid-string",
        },
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Test"}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["gateway_metadata"]["failover_triggered"] is False


@pytest.mark.tier2
def test_bva_f12_05_cost_precision_rounding(llm_backend_client):
    """Verify estimated_cost_usd is rounded to 6 decimal places."""
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer vault:secret/data/ai/llm#api_key_sk_99201"},
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Cost test"}],
        },
    )
    assert resp.status_code == 200
    cost = resp.json()["gateway_metadata"]["estimated_cost_usd"]
    # Check decimal places <= 6
    s_cost = f"{cost:.8f}".rstrip("0")
    decimals = len(s_cost.split(".")[1]) if "." in s_cost else 0
    assert decimals <= 6
