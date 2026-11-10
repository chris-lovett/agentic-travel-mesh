"""
Tier 1 Feature Tests — Architectural Plane 2: Gateway Plane + Data Plane & Automation
Covers:
- Feature 3: Envoy builtin/ext-proc Unix Sockets (5 tests)
- Feature 4: Envoy Gateway Configurations (5 tests)
- Feature 9: Python Environment & Test Automation (5 tests)
- Feature 12: Act 1: AI GW Failover & Protocol Translation (5 tests)
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
# Feature 3: Envoy builtin/ext-proc Unix Sockets
# ==============================================================================
@pytest.mark.tier1
def test_f3_01_mcp_socket_processor_target():
    """Verify consul-crds.yaml binds MCP tools to unix:///var/run/consul/csl-mcp-sc.sock."""
    crds_file = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    assert crds_file.exists(), "consul-crds.yaml must exist"
    content = crds_file.read_text()
    assert "unix:///var/run/consul/csl-mcp-sc.sock" in content


@pytest.mark.tier1
def test_f3_02_mcp_socket_message_timeout():
    """Verify consul-crds.yaml configures 5s message timeout on agent ext-proc sidecars."""
    crds_file = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crds_file.read_text()
    assert 'messageTimeout: "5s"' in content


@pytest.mark.tier1
def test_f3_03_inference_gw_socket_processor_target():
    """Verify consul-crds.yaml binds AI inference gateway to unix:///var/run/consul/csl-ig-pro.sock."""
    crds_file = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crds_file.read_text()
    assert "unix:///var/run/consul/csl-ig-pro.sock" in content


@pytest.mark.tier1
def test_f3_04_inference_gw_socket_message_timeout():
    """Verify consul-crds.yaml configures 15s message timeout on inference gateway."""
    crds_file = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crds_file.read_text()
    assert 'messageTimeout: "15s"' in content


@pytest.mark.tier1
def test_f3_05_ext_proc_filter_ordering():
    """Verify travel_igw envoy.yaml places http filters in correct sequence before router."""
    igw_envoy = ROOT_DIR / "gateways" / "travel_igw" / "envoy.yaml"
    assert igw_envoy.exists(), "gateways/travel_igw/envoy.yaml must exist"
    content = igw_envoy.read_text()
    pos_ratelimit = content.find("envoy.filters.http.local_ratelimit")
    pos_router = content.find("envoy.filters.http.router")
    assert pos_ratelimit != -1 and pos_router != -1
    assert pos_ratelimit < pos_router, "Local ratelimit filter must precede router filter"


# ==============================================================================
# Feature 4: Envoy Gateway Configurations
# ==============================================================================
@pytest.mark.tier1
def test_f4_01_api_gw_route():
    """Verify gateways/api_gw/envoy.yaml routes /agent/orchestrate to orchestrator:8080."""
    api_gw_file = ROOT_DIR / "gateways" / "api_gw" / "envoy.yaml"
    content = api_gw_file.read_text()
    assert 'prefix: "/agent/orchestrate"' in content
    assert "cluster: orchestrator_cluster" in content
    assert "port_value: 10000" in content
    assert "port_value: 8080" in content


@pytest.mark.tier1
def test_f4_02_travel_igw_chat_route():
    """Verify gateways/travel_igw/envoy.yaml injects Vault bearer key for /v1/chat/completions."""
    igw_file = ROOT_DIR / "gateways" / "travel_igw" / "envoy.yaml"
    content = igw_file.read_text()
    assert 'prefix: "/v1/chat/completions"' in content
    assert "Bearer vault:secret/data/ai/llm#api_key_sk_99201" in content
    assert "x-consul-mesh-tier" in content
    assert "travel-igw-2.1" in content


@pytest.mark.tier1
def test_f4_03_travel_igw_messages_route():
    """Verify gateways/travel_igw/envoy.yaml injects Vault secret for /v1/messages."""
    igw_file = ROOT_DIR / "gateways" / "travel_igw" / "envoy.yaml"
    content = igw_file.read_text()
    assert 'prefix: "/v1/messages"' in content
    assert "Bearer vault:secret/data/ai/anthropic#api_key_ant_8820" in content


@pytest.mark.tier1
def test_f4_04_terminating_gw_route():
    """Verify gateways/terminating_gw/envoy.yaml routes /external/mcp with Vault token."""
    term_file = ROOT_DIR / "gateways" / "terminating_gw" / "envoy.yaml"
    content = term_file.read_text()
    assert 'prefix: "/external/mcp"' in content
    assert "Bearer vault:secret/data/partners/amadeus#gds_token_9918" in content
    assert "x-egress-gateway" in content


@pytest.mark.tier1
def test_f4_05_travel_igw_rate_limiting_config():
    """Verify gateways/travel_igw/envoy.yaml configures 100 tokens/s rate limiter."""
    igw_file = ROOT_DIR / "gateways" / "travel_igw" / "envoy.yaml"
    content = igw_file.read_text()
    assert "max_tokens: 100" in content
    assert "tokens_per_fill: 100" in content
    assert "fill_interval: 1s" in content


# ==============================================================================
# Feature 9: Python Environment & Test Automation
# ==============================================================================
@pytest.mark.tier1
def test_f9_01_run_tests_sh_executable():
    """Verify run_tests.sh exists and is executable."""
    script_path = ROOT_DIR / "run_tests.sh"
    assert script_path.exists()
    assert os.access(script_path, os.X_OK)


@pytest.mark.tier1
def test_f9_02_run_tests_sh_help():
    """Verify ./run_tests.sh --help outputs usage text with exit code 0."""
    result = subprocess.run(["./run_tests.sh", "--help"], stdout=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert result.returncode == 0
    assert "Usage: ./run_tests.sh" in result.stdout
    assert "--tier" in result.stdout


@pytest.mark.tier1
def test_f9_03_run_tests_sh_tier_flag():
    """Verify ./run_tests.sh --help lists tier options."""
    result = subprocess.run(["./run_tests.sh", "--help"], stdout=subprocess.PIPE, text=True, cwd=str(ROOT_DIR))
    assert "--tier1" in result.stdout
    assert "--tier2" in result.stdout


@pytest.mark.tier1
def test_f9_04_run_tests_sh_runs_baseline():
    """Verify ./run_tests.sh successfully executes baseline test suite."""
    result = subprocess.run(
        ["./run_tests.sh", "tests/test_camp_travel.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT_DIR),
    )
    assert result.returncode == 0
    assert "6 passed" in result.stdout


@pytest.mark.tier1
def test_f9_05_run_tests_sh_failure_exit_code():
    """Verify ./run_tests.sh propagates non-zero exit code on nonexistent tests."""
    result = subprocess.run(
        ["./run_tests.sh", "-k", "non_existent_test_pattern_xyz_123"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT_DIR),
    )
    assert result.returncode != 0


# ==============================================================================
# Feature 12: Act 1: AI GW Failover & Protocol Translation
# ==============================================================================
@pytest.mark.tier1
def test_f12_01_normal_priority1_inference(llm_backend_client):
    """Verify /v1/chat/completions routes to Priority 1 Llama-3-70B under normal conditions."""
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer vault:secret/data/ai/llm#api_key_sk_99201"},
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Plan a 4-day trip to San Francisco"}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["gateway_metadata"]["failover_triggered"] is False
    assert "llama-3-70b" in data["gateway_metadata"]["routed_model"]
    assert "choices" in data
    assert len(data["choices"]) > 0


@pytest.mark.tier1
def test_f12_02_unauthenticated_request_rejected(llm_backend_client):
    """Verify request without injected Bearer token is rejected with HTTP 401 Unauthorized."""
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert resp.status_code == 401
    assert "Missing or invalid injected provider API key" in resp.json().get("detail", "")


@pytest.mark.tier1
def test_f12_03_simulated_outage_failover_claude(llm_backend_client):
    """Verify x-simulate-llm-outage: true triggers failover to Claude 3.5 Sonnet."""
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer vault:secret/data/ai/llm#api_key_sk_99201",
            "x-simulate-llm-outage": "true",
        },
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Synthesize trip itinerary"}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    metadata = data["gateway_metadata"]
    assert metadata["failover_triggered"] is True
    assert "claude-3-5-sonnet" in metadata["routed_model"]


@pytest.mark.tier1
def test_f12_04_protocol_translation_metadata(llm_backend_client):
    """Verify failover response records OpenAI-to-Anthropic protocol translation."""
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer vault:secret/data/ai/llm#api_key_sk_99201",
            "x-simulate-llm-outage": "true",
        },
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Weather advisory"}],
        },
    )
    assert resp.status_code == 200
    metadata = resp.json()["gateway_metadata"]
    assert "protocol_translation" in metadata
    assert "OpenAI /v1/chat/completions -> Anthropic /v1/messages" in metadata["protocol_translation"]


@pytest.mark.tier1
def test_f12_05_native_anthropic_endpoint(llm_backend_client):
    """Verify /v1/messages responds with native Anthropic schema response."""
    resp = llm_backend_client.post(
        "/v1/messages",
        headers={"Authorization": "Bearer vault:secret/data/ai/anthropic#api_key_ant_8820"},
        json={
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Summarize policy"}],
            "max_tokens": 512,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("type") == "message"
    assert "claude-3-5-sonnet" in data.get("model", "")
    assert "content" in data and len(data["content"]) > 0
    assert "usage" in data
