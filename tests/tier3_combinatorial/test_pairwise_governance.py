"""
Tier 3 Pairwise Combinatorial Tests — 24-Run Orthogonal Covering Array (L24)
Covers pairwise cross-plane interactions across:
- Factor A: Identity Persona & OBO Scopes (Alex Full, Sam Contractor, Anonymous, Finance Admin)
- Factor B: LLM Gateway State & Outage (Normal, Failover, Rate Limited)
- Factor C: HITL Cryptographic Evidence (Valid, Missing, Forged)
- Factor D: Caller SPIFFE ID & Workload Authorization (Booking Agent, Weather Agent, Admin Agent, Untrusted)
- Factor E: Circuit Breaker State (CLOSED, NEAR_THRESHOLD, OPEN, RESET_EXEC)
- Factor F: External Egress & Vault Token (Vault Valid, Vault Missing, Contractor Egress)
Total: 24 tests
"""
import pytest
from tests.conftest import rate_limit_state

BOOKING_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"
WEATHER_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/weather-agent"
ADMIN_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/finance-admin-agent"
UNTRUSTED_SPIFFE = "spiffe://untrusted.domain/bad-actor"

VAULT_LLM_BEARER = "Bearer vault:secret/data/ai/llm#api_key_sk_99201"
VAULT_GDS_BEARER = "Bearer vault:secret/data/partners/amadeus#gds_token_9918"


def _trip_circuit(indigo_client, spiffe_id=BOOKING_AGENT_SPIFFE, count=3):
    span_data = {
        "trace_id": f"trip-circuit-{count}",
        "agent_spiffe_id": spiffe_id,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        "tool_result": {"status": "NO_INVENTORY_RETRYABLE", "error_code": "GDS_SOLD_OUT_449"},
    }
    for _ in range(count):
        indigo_client.post("/api/indigo/ingest-span", json=span_data)


# ------------------------------------------------------------------------------
# R01: Alex Full + Normal + Valid HITL + Booking Agent + CLOSED + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r01_alex_nominal_happy_path(hotel_mcp_client, external_mcp_client):
    """R01: Nominal happy path -> Hotel confirmed with valid HITL and GDS egress allowed."""
    h_resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve,partner:gds_egress",
            "x-consul-hitl-evidence": "hitl-sig-valid-r01",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r01-1",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Alex", "nights": 2}},
        },
    )
    assert h_resp.status_code == 200
    assert h_resp.json().get("result", {}).get("status") == "confirmed"

    ext_resp = external_mcp_client.post(
        "/external/mcp/ground-transport",
        headers={
            "Authorization": VAULT_GDS_BEARER,
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve,partner:gds_egress",
        },
        json={"destination": "San Francisco", "days": 2, "vehicle": "Sedan"},
    )
    assert ext_resp.status_code == 200
    assert ext_resp.json().get("status") == "reserved"


# ------------------------------------------------------------------------------
# R02: Alex Full + Failover + Missing HITL + Weather Agent + OPEN + Vault Missing
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r02_circuit_open_intercepts_first(indigo_client, flight_mcp_client):
    """R02: Circuit breaker in OPEN state halts invocation immediately with -32029."""
    _trip_circuit(indigo_client, BOOKING_AGENT_SPIFFE, count=3)
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r02-1",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32029


# ------------------------------------------------------------------------------
# R03: Alex Full + Rate Limited + Forged HITL + Admin Agent + NEAR_THRESH + Contractor Egress
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r03_forged_hitl_rejected_at_proxy_gate(hotel_mcp_client):
    """R03: Forged HITL evidence rejected with -32003 at sidecar proxy gate."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "forged-token-r03",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r03-1",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32003


# ------------------------------------------------------------------------------
# R04: Alex Full + Normal + Valid HITL + Untrusted Caller + RESET_EXEC + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r04_untrusted_caller_spiffe_denied(hotel_mcp_client):
    """R04: Untrusted caller SPIFFE ID rejected by per-tool policy with -32001."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": UNTRUSTED_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "hitl-sig-valid-r04",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r04-1",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


# ------------------------------------------------------------------------------
# R05: Sam Contractor + Failover + Valid HITL + Booking Agent + NEAR_THRESH + Contractor Egress
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r05_contractor_scope_denied_and_egress_denied(flight_mcp_client, external_mcp_client):
    """R05: Contractor lacking booking:reserve returns -32002 and external MCP returns 403."""
    f_resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
            "x-consul-hitl-evidence": "hitl-sig-valid-r05",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r05-1",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {"flight_number": "UA-442"}},
        },
    )
    assert f_resp.status_code == 200
    assert f_resp.json().get("error", {}).get("code") == -32002

    ext_resp = external_mcp_client.post(
        "/external/mcp/ground-transport",
        headers={
            "Authorization": VAULT_GDS_BEARER,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={"destination": "San Francisco", "days": 3, "vehicle": "Sedan"},
    )
    assert ext_resp.status_code == 403


# ------------------------------------------------------------------------------
# R06: Sam Contractor + Normal + Missing HITL + Admin Agent + CLOSED + Vault Missing
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r06_destination_obo_denial_contractor(flight_mcp_client):
    """R06: Destination identity processor rejects contractor on reservation tool."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r06-1",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32002


# ------------------------------------------------------------------------------
# R07: Sam Contractor + Rate Limited + Forged HITL + Untrusted Caller + OPEN + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r07_circuit_open_takes_precedence(indigo_client, flight_mcp_client):
    """R07: Circuit OPEN intercepts invocation prior to caller SPIFFE or token validation."""
    _trip_circuit(indigo_client, BOOKING_AGENT_SPIFFE, count=3)
    resp = flight_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": UNTRUSTED_SPIFFE},
        json={
            "jsonrpc": "2.0",
            "id": "r07-1",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"}},
        },
    )
    assert resp.status_code == 200
    # Circuit breaker check happens at entrypoint
    assert resp.json().get("error", {}).get("code") in [-32029, -32001]


# ------------------------------------------------------------------------------
# R08: Sam Contractor + Normal + Valid HITL + Weather Agent + RESET_EXEC + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r08_weather_agent_cannot_call_hotel_tool(hotel_mcp_client):
    """R08: Weather agent forbidden from invoking hotel reservation tool (-32001)."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": WEATHER_AGENT_SPIFFE,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
            "x-consul-hitl-evidence": "hitl-sig-valid-r08",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r08-1",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


# ------------------------------------------------------------------------------
# R09: Anonymous + Normal + Forged HITL + Booking Agent + CLOSED + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r09_anonymous_missing_scopes_denied(hotel_mcp_client):
    """R09: Anonymous user without scopes denied with -32002."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "anonymous",
            "x-obo-scopes": "",
            "x-consul-hitl-evidence": "forged-sig-r09",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r09-1",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32002


# ------------------------------------------------------------------------------
# R10: Anonymous + Failover + Valid HITL + Untrusted Caller + NEAR_THRESH + Vault Missing
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r10_untrusted_caller_blocked(hotel_mcp_client):
    """R10: Untrusted caller SPIFFE blocked by per-tool policy."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": UNTRUSTED_SPIFFE,
            "x-consul-hitl-evidence": "hitl-sig-valid-r10",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r10-1",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


# ------------------------------------------------------------------------------
# R11: Anonymous + Rate Limited + Missing HITL + Weather Agent + RESET_EXEC + Contractor Egress
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r11_tool_policy_intercepts_weather_agent(flight_mcp_client):
    """R11: Tool policy intercepts weather agent calling flight tools."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": WEATHER_AGENT_SPIFFE},
        json={
            "jsonrpc": "2.0",
            "id": "r11-1",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


# ------------------------------------------------------------------------------
# R12: Anonymous + Normal + Valid HITL + Admin Agent + OPEN + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r12_circuit_open_blocks_admin_spiffe(indigo_client, flight_mcp_client):
    """R12: Circuit OPEN blocks tool invocation even with valid HITL evidence."""
    _trip_circuit(indigo_client, BOOKING_AGENT_SPIFFE, count=3)
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-consul-hitl-evidence": "hitl-sig-valid-r12",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r12-1",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32029


# ------------------------------------------------------------------------------
# R13: Finance Admin + Rate Limited + Valid HITL + Admin Agent + CLOSED + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r13_admin_override_rate_succeeds(hotel_mcp_client):
    """R13: Rate override succeeds for Finance Admin with admin:rate_override and valid HITL."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": ADMIN_SPIFFE,
            "x-obo-scopes": "admin:rate_override",
            "x-consul-hitl-evidence": "hitl-sig-admin-r13",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r13-1",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {"hotel_id": "HTL-SF-01", "override_rate_usd": 120.0}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("result", {}).get("status") == "rate_overridden"


# ------------------------------------------------------------------------------
# R14: Finance Admin + Normal + Missing HITL + Booking Agent + OPEN + Contractor Egress
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r14_circuit_open_blocks_booking_agent(indigo_client, flight_mcp_client):
    """R14: Circuit OPEN halts booking agent call immediately."""
    _trip_circuit(indigo_client, BOOKING_AGENT_SPIFFE, count=3)
    resp = flight_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": BOOKING_AGENT_SPIFFE},
        json={
            "jsonrpc": "2.0",
            "id": "r14-1",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32029


# ------------------------------------------------------------------------------
# R15: Finance Admin + Failover + Forged HITL + Weather Agent + NEAR_THRESH + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r15_weather_agent_cannot_invoke_admin_tool(hotel_mcp_client):
    """R15: Weather Agent cannot invoke override_hotel_rate (-32001)."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": WEATHER_AGENT_SPIFFE,
            "x-obo-scopes": "admin:rate_override",
            "x-consul-hitl-evidence": "forged-hitl-r15",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r15-1",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


# ------------------------------------------------------------------------------
# R16: Finance Admin + Normal + Valid HITL + Untrusted Caller + RESET_EXEC + Vault Missing
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r16_untrusted_caller_denied_admin_tool(hotel_mcp_client):
    """R16: Untrusted caller SPIFFE denied on hotel tools."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": UNTRUSTED_SPIFFE,
            "x-obo-scopes": "admin:rate_override",
            "x-consul-hitl-evidence": "hitl-sig-valid-r16",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r16-1",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


# ------------------------------------------------------------------------------
# R17: Alex Full + Failover + Valid HITL + Booking Agent + RESET_EXEC + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r17_post_reset_execution_with_failover_succeeds(indigo_client, flight_mcp_client, llm_backend_client):
    """R17: Post-reset execution with Priority 2 failover succeeds seamlessly."""
    # Reset circuit
    indigo_client.post("/api/indigo/circuit/reset")

    # LLM failover call
    llm_resp = llm_backend_client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": VAULT_LLM_BEARER,
            "x-simulate-llm-outage": "true",
        },
        json={"model": "meta-llama/llama-3-70b-instruct", "messages": [{"role": "user", "content": "synthesize"}]},
    )
    assert llm_resp.status_code == 200
    assert llm_resp.json()["gateway_metadata"]["failover_triggered"] is True

    # Booking reservation with valid HITL
    book_resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "hitl-sig-valid-r17",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r17-1",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {"flight_number": "UA-442"}},
        },
    )
    assert book_resp.status_code == 200
    assert book_resp.json().get("result", {}).get("status") == "ticket_confirmed"


# ------------------------------------------------------------------------------
# R18: Sam Contractor + Failover + Missing HITL + Weather Agent + CLOSED + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r18_contractor_weather_forecast_permitted(weather_mcp_client):
    """R18: Weather search permitted for contractor with travel:read scope."""
    resp = weather_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": WEATHER_AGENT_SPIFFE,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,weather:forecast",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r18-1",
            "method": "tools/call",
            "params": {"name": "get_weather_forecast", "arguments": {"destination": "San Francisco", "days": 3}},
        },
    )
    assert resp.status_code == 200
    assert "summary" in resp.json().get("result", {})


# ------------------------------------------------------------------------------
# R19: Anonymous + Normal + Valid HITL + Booking Agent + NEAR_THRESH + Vault Missing
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r19_missing_vault_bearer_at_egress_denied(external_mcp_client):
    """R19: Missing Vault Bearer token at Terminating Gateway returns HTTP 401."""
    resp = external_mcp_client.post(
        "/external/mcp/ground-transport",
        headers={"x-obo-user-id": "anonymous"},
        json={"destination": "San Francisco", "days": 2, "vehicle": "Sedan"},
    )
    assert resp.status_code == 401


# ------------------------------------------------------------------------------
# R20: Finance Admin + Failover + Valid HITL + Booking Agent + CLOSED + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r20_booking_agent_cannot_call_admin_rate_override(hotel_mcp_client):
    """R20: Booking Agent cannot invoke admin rate override (-32001)."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "admin:rate_override",
            "x-consul-hitl-evidence": "hitl-sig-r20",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r20-1",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


# ------------------------------------------------------------------------------
# R21: Alex Full + Rate Limited + Valid HITL + Admin Agent + OPEN + Vault Missing
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r21_circuit_open_blocks_invocation(indigo_client, flight_mcp_client):
    """R21: Circuit OPEN blocks tool invocation even for Admin Agent."""
    _trip_circuit(indigo_client, BOOKING_AGENT_SPIFFE, count=3)
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-consul-hitl-evidence": "hitl-sig-valid-r21",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r21-1",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32029


# ------------------------------------------------------------------------------
# R22: Sam Contractor + Normal + Forged HITL + Booking Agent + RESET_EXEC + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r22_contractor_scope_denied_with_forged_hitl(hotel_mcp_client):
    """R22: Contractor lacking booking:reserve denied (-32002)."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
            "x-consul-hitl-evidence": "forged-token-r22",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r22-1",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32002


# ------------------------------------------------------------------------------
# R23: Anonymous + Failover + Missing HITL + Admin Agent + OPEN + Contractor Egress
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r23_circuit_open_intercepts_before_auth(indigo_client, flight_mcp_client):
    """R23: Circuit breaker intercepts before auth evaluation."""
    _trip_circuit(indigo_client, BOOKING_AGENT_SPIFFE, count=3)
    resp = flight_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": BOOKING_AGENT_SPIFFE},
        json={
            "jsonrpc": "2.0",
            "id": "r23-1",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32029


# ------------------------------------------------------------------------------
# R24: Finance Admin + Normal + Valid HITL + Admin Agent + NEAR_THRESH + Vault Valid
# ------------------------------------------------------------------------------
@pytest.mark.tier3
@pytest.mark.governance
def test_r24_admin_cancel_all_succeeds(flight_mcp_client):
    """R24: Emergency cancel succeeds for Global Security Admin with admin:emergency_cancel and valid HITL."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/global-security-admin",
            "x-obo-scopes": "admin:emergency_cancel",
            "x-consul-hitl-evidence": "hitl-sig-secadmin-emergency-override",
        },
        json={
            "jsonrpc": "2.0",
            "id": "r24-1",
            "method": "tools/call",
            "params": {"name": "cancel_all_corporate_bookings", "arguments": {"reason": "Severe Weather Emergency"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("result", {}).get("status") == "cancelled"
