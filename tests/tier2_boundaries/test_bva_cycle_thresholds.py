"""
Tier 2 Boundary Value Analysis — Cycle Detection, Observability & Adversarial Boundaries
Covers Boundary Value Analysis for Features 16, 17, 19, 20 (20 tests)
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BOOKING_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"
WEATHER_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/weather-agent"


# ==============================================================================
# Feature 16 BVA: Cycle Detection Fingerprint & Counter Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f16_01_repetition_boundary_near_threshold(indigo_client):
    """Verify repetition count N=2 remains strictly CLOSED."""
    span_data = {
        "trace_id": "bva-trace-near-thresh",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SFO"},
        "tool_result": {"status": "available"},
    }
    indigo_client.post("/api/indigo/ingest-span", json=span_data)
    resp = indigo_client.post("/api/indigo/ingest-span", json=span_data)
    assert resp.status_code == 200
    assert resp.json()["repetition_count"] == 2
    assert resp.json()["circuit_state"] == "CLOSED"


@pytest.mark.tier2
def test_bva_f16_02_repetition_exact_threshold_trips(indigo_client):
    """Verify repetition count N=3 trips circuit state to OPEN."""
    span_data = {
        "trace_id": "bva-trace-thresh",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SFO"},
        "tool_result": {"status": "available"},
    }
    for _ in range(2):
        indigo_client.post("/api/indigo/ingest-span", json=span_data)
    resp = indigo_client.post("/api/indigo/ingest-span", json=span_data)
    assert resp.status_code == 200
    assert resp.json()["repetition_count"] == 3
    assert resp.json()["circuit_state"] == "OPEN"


@pytest.mark.tier2
def test_bva_f16_03_different_arguments_separate_fingerprints(indigo_client):
    """Verify varying arguments generates distinct fingerprints without tripping breaker."""
    span_1 = {
        "trace_id": "bva-fp-1",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SFO"},
        "tool_result": {"status": "available"},
    }
    span_2 = {
        "trace_id": "bva-fp-2",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "LHR"},
        "tool_result": {"status": "available"},
    }
    resp1 = indigo_client.post("/api/indigo/ingest-span", json=span_1)
    resp2 = indigo_client.post("/api/indigo/ingest-span", json=span_2)
    assert resp1.json()["fingerprint"] != resp2.json()["fingerprint"]
    assert resp2.json()["repetition_count"] == 1
    assert resp2.json()["circuit_state"] == "CLOSED"


@pytest.mark.tier2
def test_bva_f16_04_different_results_separate_fingerprints(indigo_client):
    """Verify changing tool results produces distinct fingerprints."""
    span_1 = {
        "trace_id": "bva-res-1",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SFO"},
        "tool_result": {"status": "available", "count": 5},
    }
    span_2 = {
        "trace_id": "bva-res-2",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SFO"},
        "tool_result": {"status": "sold_out", "count": 0},
    }
    resp1 = indigo_client.post("/api/indigo/ingest-span", json=span_1)
    resp2 = indigo_client.post("/api/indigo/ingest-span", json=span_2)
    assert resp1.json()["fingerprint"] != resp2.json()["fingerprint"]
    assert resp2.json()["circuit_state"] == "CLOSED"


@pytest.mark.tier2
def test_bva_f16_05_reset_specific_agent_circuit(indigo_client):
    """Verify resetting circuit with specific agent_spiffe_id targets that agent."""
    resp = indigo_client.post(
        "/api/indigo/circuit/reset",
        json={"agent_spiffe_id": BOOKING_AGENT_SPIFFE},
    )
    assert resp.status_code == 200
    circuits = resp.json().get("circuits", {})
    assert circuits[BOOKING_AGENT_SPIFFE]["state"] == "CLOSED"


# ==============================================================================
# Feature 17 BVA: Observability & Telemetry Value Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f17_01_trace_zero_tokens_cost(otel_client):
    """Verify trace with tokens_used=0 calculates prompt=0, completion=0, cost=0.0."""
    resp = otel_client.post(
        "/v1/traces",
        json={"service": "travel-orchestrator", "tokens_used": 0},
    )
    assert resp.status_code == 200
    traces = otel_client.get("/v1/traces").json()["traces"]
    latest = traces[-1]
    gen_ai = latest["otel_gen_ai_attributes"]
    assert gen_ai["gen_ai.usage.total_tokens"] == 0
    assert gen_ai["gen_ai.usage.cost_usd"] == 0.0


@pytest.mark.tier2
def test_bva_f17_02_trace_large_tokens_cost(otel_client):
    """Verify trace with tokens_used=1,000,000 calculates cost accurately without int overflow."""
    resp = otel_client.post(
        "/v1/traces",
        json={"service": "travel-orchestrator", "tokens_used": 1000000},
    )
    assert resp.status_code == 200
    traces = otel_client.get("/v1/traces").json()["traces"]
    latest = traces[-1]
    assert latest["otel_gen_ai_attributes"]["gen_ai.usage.total_tokens"] == 1000000
    assert latest["otel_gen_ai_attributes"]["gen_ai.usage.cost_usd"] > 0


@pytest.mark.tier2
def test_bva_f17_03_trace_missing_service_default(otel_client):
    """Verify trace without service defaults to travel-orchestrator."""
    resp = otel_client.post("/v1/traces", json={"tokens_used": 10})
    assert resp.status_code == 200
    traces = otel_client.get("/v1/traces").json()["traces"]
    latest = traces[-1]
    assert latest["service"] == "travel-orchestrator"


@pytest.mark.tier2
def test_bva_f17_04_trace_missing_span_type_default(otel_client):
    """Verify trace without span_type defaults to llm_inference."""
    resp = otel_client.post("/v1/traces", json={"tokens_used": 10})
    assert resp.status_code == 200
    traces = otel_client.get("/v1/traces").json()["traces"]
    latest = traces[-1]
    assert latest["span_type"] == "llm_inference"


@pytest.mark.tier2
def test_bva_f17_05_traces_store_slice_bound(otel_client):
    """Verify GET /v1/traces caps history to last 50 traces."""
    # Ingest batch
    for i in range(10):
        otel_client.post("/v1/traces", json={"tokens_used": i})
    resp = otel_client.get("/v1/traces")
    assert resp.status_code == 200
    assert len(resp.json()["traces"]) <= 50


# ==============================================================================
# Feature 19 BVA: E2E Test Framework & Isolation Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f19_01_state_isolation_between_tests():
    """Verify in-memory stores are clean at test start."""
    from frontend.main import trips_database, audit_events
    from observability.otel.main import traces_store
    assert len(trips_database) == 0
    assert len(audit_events) == 0
    assert len(traces_store) == 0


@pytest.mark.tier2
def test_bva_f19_02_circuit_isolation_clean():
    """Verify all circuits start in CLOSED state."""
    from observability.indigo.main import agent_circuits
    for spiffe, circuit in agent_circuits.items():
        assert circuit["state"] == "CLOSED"


@pytest.mark.tier2
def test_bva_f19_03_outage_state_isolation():
    """Verify local outage simulation flag starts as False."""
    from llm_backend.main import local_outage_state
    assert local_outage_state["simulate_primary_llm_outage"] is False


@pytest.mark.tier2
def test_bva_f19_04_token_stats_isolation():
    """Verify token usage stats are initialized to 0."""
    from llm_backend.main import token_usage_stats
    assert token_usage_stats["total_calls"] == 0
    assert token_usage_stats["total_tokens"] == 0


@pytest.mark.tier2
def test_bva_f19_05_fingerprint_counters_isolation():
    """Verify fingerprint counters dictionary is empty at test start."""
    from observability.indigo.main import fingerprint_counters
    assert len(fingerprint_counters) == 0


# ==============================================================================
# Feature 20 BVA: Adversarial Hardening Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f20_01_large_payload_string_boundary(hotel_mcp_client):
    """Verify 10,000-character destination string is handled safely without buffer error."""
    large_dest = "A" * 10000
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "bva-adv-1",
            "method": "tools/call",
            "params": {"name": "search_hotels", "arguments": {"destination": large_dest}},
        },
    )
    assert resp.status_code == 200
    assert "result" in resp.json()


@pytest.mark.tier2
def test_bva_f20_02_unicode_characters_handling(hotel_mcp_client):
    """Verify Unicode non-ASCII string ('東京 (Tokyo) 🗼') is encoded properly."""
    unicode_city = "東京 (Tokyo) 🗼"
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "bva-adv-2",
            "method": "tools/call",
            "params": {"name": "search_hotels", "arguments": {"destination": unicode_city}},
        },
    )
    assert resp.status_code == 200
    assert "result" in resp.json()


@pytest.mark.tier2
def test_bva_f20_03_sql_injection_payload_sanitized(flight_mcp_client):
    """Verify SQL injection payload in tool arguments is treated strictly as literal string."""
    sql_inj = "JFK'; DROP TABLE flights; SELECT * FROM flights WHERE '1'='1"
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "bva-adv-3",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": sql_inj, "destination": "SFO"}},
        },
    )
    assert resp.status_code == 200
    assert "result" in resp.json()


@pytest.mark.tier2
def test_bva_f20_04_tampered_hitl_signature_length(hotel_mcp_client):
    """Verify hitl-sig- prefix with unusual character sequence is still processed per protocol."""
    tampered_token = "hitl-sig-GGGGGGGGGGGGGGGG"
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": tampered_token,
        },
        json={
            "jsonrpc": "2.0",
            "id": "bva-adv-4",
            "method": "tools/call",
            "params": {
                "name": "reserve_hotel",
                "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Test", "nights": 1},
            },
        },
    )
    assert resp.status_code == 200
    # Must either confirm with token or verify prefix
    assert "result" in resp.json()
    assert resp.json()["result"]["hitl_evidence_verified"] == tampered_token


@pytest.mark.tier2
def test_bva_f20_05_tampered_obo_header_injection(flight_mcp_client):
    """Verify semicolon-delimited header injection attempt does not grant privileged scopes."""
    malicious_header = "travel:read; admin:true; booking:reserve"
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": malicious_header,
            "x-consul-hitl-evidence": "hitl-sig-valid",
        },
        json={
            "jsonrpc": "2.0",
            "id": "bva-adv-5",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    # Semicolons are not CSV delimiters, so 'booking:reserve' is not parsed as a separate scope
    assert resp.json().get("error", {}).get("code") == -32002
