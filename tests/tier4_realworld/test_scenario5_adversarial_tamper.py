"""
Tier 4 Real-World Interactive User Journey — Scenario 5: Adversarial Tamper & Zero-Trust Defense (5 Acts)
Scenario: Zero-Trust Defense Against Tampering, Privilege Escalation, and Cryptographic Forgery
- Act I: Unauthenticated Ingress Gateway Rejection (HTTP 401)
- Act II: Rogue Workload Identity Rejection (-32001)
- Act III: Forged Cryptographic HITL Signature Rejection (-32003)
- Act IV: Unauthorized Administrative Privilege Escalation Rejection (-32001)
- Act V: Security Ledger Audit & Layer Violation Aggregation
"""
import pytest


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario5_full_5act_adversarial_tamper_defense(
    travel_igw_client,
    flight_mcp_client,
    hotel_mcp_client,
    indigo_analytics_client,
    frontend_client,
):
    """
    Complete 5-Act user journey testing multi-layer zero-trust defense mechanisms against adversarial vectors.
    Validates cryptographic signature integrity, SPIFFE authorization, and audit trail aggregation.
    """
    # --------------------------------------------------------------------------
    # ACT I: Unauthenticated Ingress Gateway Rejection (HTTP 401)
    # --------------------------------------------------------------------------
    unauth_llm = travel_igw_client.post(
        "/v1/chat/completions",
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Adversarial exploit attempt"}],
        },
    )
    assert unauth_llm.status_code == 401, "Act I: Ingress gateway must reject unauthenticated call with 401"
    assert "Missing or invalid injected provider API key" in unauth_llm.json().get("detail", "")

    # --------------------------------------------------------------------------
    # ACT II: Rogue Workload Identity Rejection (-32001)
    # --------------------------------------------------------------------------
    rogue_resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/untrusted-rogue-attacker",
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act2-rogue",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SFO"}},
        },
    )
    assert rogue_resp.status_code == 200
    r_json = rogue_resp.json()
    assert "error" in r_json
    assert r_json["error"]["code"] == -32001
    assert "Per-Tool Policy Denied" in r_json["error"]["message"]
    assert "untrusted-rogue-attacker" in r_json["error"]["message"]

    # --------------------------------------------------------------------------
    # ACT III: Forged Cryptographic HITL Signature Rejection (-32003)
    # --------------------------------------------------------------------------
    forged_hitl = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "invalid-forged-signature-without-prefix",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act3-forged",
            "method": "tools/call",
            "params": {
                "name": "reserve_flight",
                "arguments": {
                    "flight_number": "UA-442",
                    "passenger_name": "Adversary",
                    "origin": "JFK",
                    "destination": "SFO",
                },
            },
        },
    )
    assert forged_hitl.status_code == 200
    f_json = forged_hitl.json()
    assert "error" in f_json
    assert f_json["error"]["code"] == -32003
    assert "HITL Gate Intercepted" in f_json["error"]["message"]

    # --------------------------------------------------------------------------
    # ACT IV: Unauthorized Administrative Privilege Escalation Rejection (-32001)
    # --------------------------------------------------------------------------
    escalate_resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "hitl-sig-valid",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act4-escalate",
            "method": "tools/call",
            "params": {
                "name": "override_hotel_rate",
                "arguments": {"hotel_id": "HTL-SF-01", "new_rate_usd": 1.0},
            },
        },
    )
    assert escalate_resp.status_code == 200
    e_json = escalate_resp.json()
    assert "error" in e_json
    assert e_json["error"]["code"] == -32001
    assert "override_hotel_rate" in e_json["error"]["message"]

    # --------------------------------------------------------------------------
    # ACT V: Security Ledger Audit & Layer Violation Aggregation
    # --------------------------------------------------------------------------
    audit_resp = indigo_analytics_client.get("/api/indigo/audit-summary")
    assert audit_resp.status_code == 200
    summary = audit_resp.json()
    assert "metrics" in summary
    assert "governance_events" in summary
    assert "agent_circuits" in summary


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario5_act1_unauthenticated_gateway_denial(travel_igw_client):
    """Act I In-depth: Ingress gateway returns 401 on unauthenticated calls."""
    resp = travel_igw_client.post(
        "/v1/chat/completions",
        json={"model": "meta-llama/llama-3-70b-instruct", "messages": []},
    )
    assert resp.status_code == 401


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario5_act2_untrusted_spiffe_workload_denial(hotel_mcp_client):
    """Act II In-depth: hotel-mcp rejects untrusted SPIFFE caller with -32001."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/untrusted-rogue"},
        json={"jsonrpc": "2.0", "id": "act2-test", "method": "tools/call", "params": {"name": "search_hotels", "arguments": {}}},
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario5_act3_forged_hitl_signature_format(flight_mcp_client):
    """Act III In-depth: flight-mcp rejects invalid or non-prefixed HITL signature with -32003."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-scopes": "booking:reserve",
            "x-consul-hitl-evidence": "invalid-token",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act3-format",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {"flight_number": "UA-442"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32003


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario5_act4_booking_agent_cannot_cancel_all(flight_mcp_client):
    """Act IV In-depth: booking-agent calling cancel_all_corporate_bookings is denied with -32001."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-scopes": "booking:reserve",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act4-cancel",
            "method": "tools/call",
            "params": {"name": "cancel_all_corporate_bookings", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario5_act5_indigo_ledger_record_violation(indigo_analytics_client):
    """Act V In-depth: Recording a policy violation registers in Indigo audit summary."""
    resp_ingest = indigo_analytics_client.post(
        "/api/indigo/ingest-span",
        json={
            "trace_id": "act5-trace-1",
            "agent_spiffe_id": "spiffe://cluster.local/ns/camp-travel/sa/untrusted-rogue",
            "obo_user_id": "traveler-101",
            "tool_name": "search_flights",
            "tool_arguments": {},
            "tool_result": {},
            "span_type": "policy_violation",
            "detail": "csl-mcp-sc Per-Tool Policy Denied",
        },
    )
    assert resp_ingest.status_code == 200
    resp = indigo_analytics_client.get("/api/indigo/audit-summary")
    assert resp.status_code == 200
    assert resp.json()["metrics"]["policy_violations_prevented"] >= 1
