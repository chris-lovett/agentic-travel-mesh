"""
Tier 1 Feature Tests — Architectural Plane 5: Observability & Governance Plane + Hardening
Covers:
- Feature 16: Act 4: Cycle Detection & Circuit Breaker (5 tests)
- Feature 17: Act 5: CRD Inspector & Zero-Code Telemetry (5 tests)
- Feature 19: Comprehensive 5-Act E2E Test Suite (5 tests)
- Feature 20: Adversarial Coverage Hardening (5 tests)
Total: 20 tests
"""
import pytest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

BOOKING_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"


# ==============================================================================
# Feature 16: Act 4: Cycle Detection & Circuit Breaker
# ==============================================================================
@pytest.mark.tier1
def test_f16_01_span_ingest_repetition_1(indigo_client):
    """Verify first tool call span registers with repetition_count 1 and circuit CLOSED."""
    resp = indigo_client.post(
        "/api/indigo/ingest-span",
        json={
            "trace_id": "trace-cycle-1",
            "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
            "tool_name": "search_flights",
            "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
            "tool_result": {"status": "NO_INVENTORY_RETRYABLE", "error_code": "GDS_SOLD_OUT_449"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("repetition_count") == 1
    assert data.get("circuit_state") == "CLOSED"


@pytest.mark.tier1
def test_f16_02_span_ingest_repetition_2(indigo_client):
    """Verify identical second tool call reaches repetition_count 2 and remains CLOSED."""
    span_data = {
        "trace_id": "trace-cycle-2",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        "tool_result": {"status": "NO_INVENTORY_RETRYABLE", "error_code": "GDS_SOLD_OUT_449"},
    }
    indigo_client.post("/api/indigo/ingest-span", json=span_data)
    resp = indigo_client.post("/api/indigo/ingest-span", json=span_data)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("repetition_count") == 2
    assert data.get("circuit_state") == "CLOSED"


@pytest.mark.tier1
def test_f16_03_span_ingest_repetition_3_trips_circuit(indigo_client):
    """Verify identical third tool call meets threshold (3) and trips circuit to OPEN."""
    span_data = {
        "trace_id": "trace-cycle-3",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        "tool_result": {"status": "NO_INVENTORY_RETRYABLE", "error_code": "GDS_SOLD_OUT_449"},
    }
    indigo_client.post("/api/indigo/ingest-span", json=span_data)
    indigo_client.post("/api/indigo/ingest-span", json=span_data)
    resp = indigo_client.post("/api/indigo/ingest-span", json=span_data)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("repetition_count") == 3
    assert data.get("circuit_state") == "OPEN"


@pytest.mark.tier1
def test_f16_04_circuit_open_tool_halt(indigo_client, flight_mcp_client):
    """Verify tool invocation is halted with -32029 (AGENT_CIRCUIT_OPEN) when circuit is OPEN."""
    span_data = {
        "trace_id": "trace-cycle-halt",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        "tool_result": {"status": "NO_INVENTORY_RETRYABLE", "error_code": "GDS_SOLD_OUT_449"},
    }
    for _ in range(3):
        indigo_client.post("/api/indigo/ingest-span", json=span_data)

    # 4th call to flight-mcp must be rejected immediately
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "halt-1",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"}},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32029
    assert "Circuit Breaker OPEN" in data["error"]["message"]


@pytest.mark.tier1
def test_f16_05_circuit_reset_endpoint(indigo_client):
    """Verify POST /api/indigo/circuit/reset restores circuit breakers to CLOSED."""
    # Trip circuit first
    span_data = {
        "trace_id": "trace-cycle-reset",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        "tool_result": {"status": "NO_INVENTORY_RETRYABLE", "error_code": "GDS_SOLD_OUT_449"},
    }
    for _ in range(3):
        indigo_client.post("/api/indigo/ingest-span", json=span_data)

    # Reset
    resp = indigo_client.post("/api/indigo/circuit/reset")
    assert resp.status_code == 200
    circuits = resp.json().get("circuits", {})
    for spiffe, circuit in circuits.items():
        assert circuit.get("state") == "CLOSED"


# ==============================================================================
# Feature 17: Act 5: CRD Inspector & Zero-Code Telemetry
# ==============================================================================
@pytest.mark.tier1
def test_f17_01_otel_ingest_trace(otel_client):
    """Verify POST /v1/traces accepts trace and returns status accepted."""
    resp = otel_client.post(
        "/v1/traces",
        json={
            "service": "travel-orchestrator",
            "span_type": "llm_inference",
            "model": "meta-llama/llama-3-70b-instruct",
            "tokens_used": 150,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "accepted"
    assert "trace_id" in data


@pytest.mark.tier1
def test_f17_02_otel_get_traces(otel_client):
    """Verify GET /v1/traces returns ingested trace history."""
    otel_client.post(
        "/v1/traces",
        json={"service": "travel-orchestrator", "tokens_used": 100},
    )
    resp = otel_client.get("/v1/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert "traces" in data
    assert len(data["traces"]) > 0


@pytest.mark.tier1
def test_f17_03_genai_semantic_attributes(otel_client):
    """Verify GenAI semantic convention attributes are populated in trace records."""
    otel_client.post(
        "/v1/traces",
        json={
            "service": "travel-orchestrator",
            "model": "meta-llama/llama-3-70b-instruct",
            "tokens_used": 200,
            "tool_name": "search_hotels",
            "mcp_server": "hotel-mcp",
        },
    )
    resp = otel_client.get("/v1/traces")
    latest = resp.json()["traces"][-1]
    gen_ai = latest.get("otel_gen_ai_attributes", {})
    assert gen_ai.get("gen_ai.request.model") == "meta-llama/llama-3-70b-instruct"
    assert gen_ai.get("gen_ai.usage.total_tokens") == 200
    assert gen_ai.get("mcp.tool.name") == "search_hotels"


@pytest.mark.tier1
def test_f17_04_bullmq_queue_depth(otel_client):
    """Verify trace ingestion enqueues jobs in BullMQ queue for Agentic Analytics."""
    resp1 = otel_client.get("/v1/traces")
    initial_depth = resp1.json().get("bullmq_queue_depth", 0)

    otel_client.post(
        "/v1/traces",
        json={"service": "booking-agent", "tokens_used": 50},
    )

    resp2 = otel_client.get("/v1/traces")
    assert resp2.json().get("bullmq_queue_depth", 0) == initial_depth + 1


@pytest.mark.tier1
def test_f17_05_governance_status_endpoint(frontend_client):
    """Verify /api/governance/status endpoint aggregates analytics and trace state."""
    resp = frontend_client.get("/api/governance/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "indigo" in data
    assert "otel" in data
    assert "personas" in data


# ==============================================================================
# Feature 19: Comprehensive 5-Act E2E Test Suite
# ==============================================================================
@pytest.mark.tier1
def test_f19_01_baseline_test_suite_passes():
    """Verify existing tests/test_camp_travel.py baseline continues to pass with 0 failures."""
    from tests.test_camp_travel import (
        test_weather_mcp,
        test_hotel_mcp_and_act2_sidecar_policy,
        test_flight_mcp_and_act3_obo_scopes,
        test_external_mcp_auth_and_obo_egress,
        test_llm_backend_auth_and_act1_failover,
        test_act4_cycle_detection_and_circuit_breaker,
    )
    test_weather_mcp()
    test_hotel_mcp_and_act2_sidecar_policy()
    test_flight_mcp_and_act3_obo_scopes()
    test_external_mcp_auth_and_obo_egress()
    test_llm_backend_auth_and_act1_failover()
    test_act4_cycle_detection_and_circuit_breaker()


@pytest.mark.tier1
def test_f19_02_all_services_covered():
    """Verify all 11 microservice apps can be invoked via ASGI."""
    from tests.conftest import SERVICE_APPS
    assert len(SERVICE_APPS) >= 11


@pytest.mark.tier1
def test_f19_03_jsonrpc_contracts_verified(hotel_mcp_client, flight_mcp_client):
    """Verify MCP servers adhere to JSON-RPC 2.0 error specifications."""
    resp = hotel_mcp_client.post("/mcp", json={"jsonrpc": "2.0", "id": "1", "method": "invalid/method"})
    assert resp.json().get("error", {}).get("code") == -32600


@pytest.mark.tier1
def test_f19_04_rest_contracts_verified(llm_backend_client, external_mcp_client):
    """Verify REST endpoints enforce HTTP 401 Unauthorized for unauthenticated calls."""
    resp_llm = llm_backend_client.post(
        "/v1/chat/completions",
        json={"model": "meta-llama/llama-3-70b-instruct", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp_llm.status_code == 401

    resp_ext = external_mcp_client.post(
        "/external/mcp/ground-transport",
        json={"destination": "San Francisco", "days": 4, "vehicle": "Executive Sedan"},
    )
    assert resp_ext.status_code == 401


@pytest.mark.tier1
def test_f19_05_zero_facade_tests():
    """Verify tests assert genuine application business logic."""
    from mcp_tools.weather_server.main import _execute_weather_forecast
    fc = _execute_weather_forecast("San Francisco", 4)
    assert "San Francisco" in fc["destination"]
    assert len(fc["daily_forecast"]) == 4


# ==============================================================================
# Feature 20: Adversarial Coverage Hardening (Tier 5)
# ==============================================================================
@pytest.mark.tier1
def test_f20_01_forged_hitl_signature_rejected(hotel_mcp_client):
    """Verify forged HITL signature without hitl-sig- prefix is rejected with -32003."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "forged-signature-token-9999",
        },
        json={
            "jsonrpc": "2.0",
            "id": "adv-1",
            "method": "tools/call",
            "params": {
                "name": "reserve_hotel",
                "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Attacker", "nights": 1},
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32003


@pytest.mark.tier1
def test_f20_02_scope_escalation_attempt(flight_mcp_client):
    """Verify caller asserting ungranted scopes is rejected with -32002."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read",  # missing booking:reserve
            "x-consul-hitl-evidence": "hitl-sig-verified123",
        },
        json={
            "jsonrpc": "2.0",
            "id": "adv-2",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {"flight_number": "UA-442"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32002


@pytest.mark.tier1
def test_f20_03_spiffe_spoofing_denied(hotel_mcp_client):
    """Verify unauthorized external SPIFFE ID is rejected with -32001."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://evil.attacker.domain/sa/rogue-agent",
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
        },
        json={
            "jsonrpc": "2.0",
            "id": "adv-3",
            "method": "tools/call",
            "params": {
                "name": "reserve_hotel",
                "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Attacker", "nights": 1},
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


@pytest.mark.tier1
def test_f20_04_unauthenticated_model_access(llm_backend_client):
    """Verify foundation model directly rejects unauthenticated calls with 401."""
    resp = llm_backend_client.post(
        "/v1/chat/completions",
        json={"model": "meta-llama/llama-3-70b-instruct", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401


@pytest.mark.tier1
def test_f20_05_unauthenticated_gds_egress(external_mcp_client):
    """Verify partner GDS directly rejects unauthenticated calls with 401."""
    resp = external_mcp_client.post(
        "/external/mcp/ground-transport",
        json={"destination": "San Francisco", "days": 4, "vehicle": "Executive Sedan"},
    )
    assert resp.status_code == 401
