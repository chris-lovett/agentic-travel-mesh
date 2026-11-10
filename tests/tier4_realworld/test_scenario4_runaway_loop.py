"""
Tier 4 Real-World Interactive User Journey — Scenario 4: Runaway Loop & Circuit Recovery (5 Acts)
Scenario: Malfunctioning Agent Runaway Loop Detection & Self-Healing Circuit Breaker
- Act I: Initial Baseline State Verification (Circuit CLOSED)
- Act II: Runaway Query Iterations (destination: SOLDOUT-LOOP)
- Act III: Agentic Analytics Cycle Detection & Circuit Tripping (CLOSED -> OPEN)
- Act IV: MCP Sidecar Immediate Rejection (-32029)
- Act V: Admin Remediation & System Self-Healing (Reset -> CLOSED)
"""
import pytest


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario4_full_5act_runaway_loop_and_recovery(frontend_client, flight_mcp_client, indigo_analytics_client):
    """
    Complete 5-Act user journey testing runaway tool-calling detection, circuit breaking, and administrative reset.
    Validates Agentic Analytics (csl-ag-ana) fingerprinting and MCP sidecar (csl-mcp-sc) circuit interception.
    """
    # --------------------------------------------------------------------------
    # ACT I: Initial Baseline State Verification (Circuit CLOSED)
    # --------------------------------------------------------------------------
    c_resp = indigo_analytics_client.get("/api/indigo/circuit/booking-agent")
    assert c_resp.status_code == 200
    assert c_resp.json().get("state") == "CLOSED"

    # --------------------------------------------------------------------------
    # ACT II & ACT III: Runaway Query Iterations & Circuit Tripping
    # --------------------------------------------------------------------------
    plan_resp = frontend_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "user_name": "Alex Mercer",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 3,
            "budget_usd": 2000.0,
            "scenario_mode": "act4_cycle_loop",
        },
    )
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()

    loop_iters = plan_data.get("loop_iterations", [])
    assert len(loop_iters) >= 3, "Act II: Runaway loop must record >= 3 search attempts"

    # Verify transition to OPEN
    last_iter = loop_iters[-1]
    assert last_iter.get("circuit_state") == "OPEN" or last_iter.get("outcome") == "CIRCUIT_OPEN_REJECTED"

    # --------------------------------------------------------------------------
    # ACT IV: MCP Sidecar Immediate Rejection (-32029)
    # --------------------------------------------------------------------------
    subsequent_call = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act4-blocked",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SFO"}},
        },
    )
    assert subsequent_call.status_code == 200
    sub_json = subsequent_call.json()
    assert "error" in sub_json
    assert sub_json["error"]["code"] == -32029
    assert "Consul Behavior Policy Circuit Breaker OPEN" in sub_json["error"]["message"]

    # --------------------------------------------------------------------------
    # ACT V: Admin Remediation & System Self-Healing
    # --------------------------------------------------------------------------
    reset_resp = frontend_client.post("/api/governance/reset-circuit")
    assert reset_resp.status_code == 200
    reset_data = reset_resp.json()
    assert reset_data.get("status") == "reset"

    # Verify circuit is CLOSED again
    c_after = indigo_analytics_client.get("/api/indigo/circuit/booking-agent")
    assert c_after.status_code == 200
    assert c_after.json().get("state") == "CLOSED"

    # Verify next call succeeds
    recovered_call = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act5-recovered",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SFO"}},
        },
    )
    assert recovered_call.status_code == 200
    assert "result" in recovered_call.json()
    assert "available_flights" in recovered_call.json().get("result", {})


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario4_act1_initial_circuit_closed(indigo_analytics_client):
    """Act I In-depth: Verifies agent circuit starts in CLOSED state."""
    resp = indigo_analytics_client.get("/api/indigo/circuit/booking-agent")
    assert resp.status_code == 200
    assert resp.json().get("state") == "CLOSED"


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario4_act2_cycle_repetition_counting(indigo_analytics_client):
    """Act II In-depth: Submitting repetitive cycle increments repetition counter."""
    payload = {
        "trace_id": "cycle-act2-1",
        "agent_spiffe_id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        "span_type": "mcp_tool_call",
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        "tool_result": {"status": "sold_out"},
    }
    r1 = indigo_analytics_client.post("/api/indigo/ingest-span", json=payload)
    assert r1.status_code == 200
    assert r1.json()["circuit_state"] == "CLOSED"


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario4_act3_circuit_trip_at_threshold(indigo_analytics_client):
    """Act III In-depth: Submitting 3 cycles trips the circuit to OPEN."""
    payload = {
        "trace_id": "trip-act3-1",
        "agent_spiffe_id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        "span_type": "mcp_tool_call",
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "LOOP"},
        "tool_result": {"status": "sold_out"},
    }
    indigo_analytics_client.post("/api/indigo/ingest-span", json=payload)
    indigo_analytics_client.post("/api/indigo/ingest-span", json=payload)
    r3 = indigo_analytics_client.post("/api/indigo/ingest-span", json=payload)
    assert r3.status_code == 200
    assert r3.json()["circuit_state"] == "OPEN"


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario4_act4_mcp_circuit_breaker_code(flight_mcp_client, indigo_analytics_client):
    """Act IV In-depth: flight-mcp rejects with JSON-RPC error code -32029 when circuit is OPEN."""
    # Trip circuit via ingest-span
    payload = {
        "trace_id": "act4-trip-trace",
        "agent_spiffe_id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        "span_type": "mcp_tool_call",
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        "tool_result": {"status": "sold_out"},
    }
    indigo_analytics_client.post("/api/indigo/ingest-span", json=payload)
    indigo_analytics_client.post("/api/indigo/ingest-span", json=payload)
    indigo_analytics_client.post("/api/indigo/ingest-span", json=payload)

    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={"jsonrpc": "2.0", "id": "act4-test", "method": "tools/call", "params": {"name": "search_flights", "arguments": {}}},
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32029


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario4_act5_remediation_reset(indigo_analytics_client):
    """Act V In-depth: Indigo circuit reset clears trip and restores CLOSED state."""
    resp = indigo_analytics_client.post("/api/indigo/circuit/reset", json={})
    assert resp.status_code == 200
    circuits = resp.json().get("circuits", {})
    for spiffe, circ in circuits.items():
        assert circ.get("state") == "CLOSED"
