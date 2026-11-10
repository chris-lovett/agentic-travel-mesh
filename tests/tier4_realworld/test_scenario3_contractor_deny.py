"""
Tier 4 Real-World Interactive User Journey — Scenario 3: Contractor Scope Boundary Defense (5 Acts)
Scenario: Sam Taylor (contractor-202) Boundary Defense & Egress Protection
- Act I: Contractor Persona Authentication & Restricted Scope Minting
- Act II: Permitted Read-Only Planning Search
- Act III: Unauthorized Reservation Blocked by MCP Sidecar (-32002)
- Act IV: Unauthorized GDS Egress Blocked by Terminating Gateway (403)
- Act V: Security Audit & Interception Telemetry
"""
import pytest


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario3_full_5act_contractor_deny(frontend_client, flight_mcp_client, terminating_gw_client):
    """
    Complete 5-Act user journey testing zero-trust scope boundary enforcement for contractor-202.
    Ensures read operations succeed while mutation and egress attempts are strictly denied.
    """
    # --------------------------------------------------------------------------
    # ACT I: Contractor Persona Authentication & Scope Minting
    # --------------------------------------------------------------------------
    auth_resp = frontend_client.post(
        "/api/auth/obo-token",
        json={"user_id": "contractor-202"},
    )
    assert auth_resp.status_code == 200
    auth_data = auth_resp.json()
    assert auth_data.get("obo_subject") == "contractor-202"
    assert "booking:reserve" not in auth_data.get("scopes", [])
    assert "partner:gds_egress" not in auth_data.get("scopes", [])
    assert set(auth_data.get("scopes", [])) == {"travel:read", "travel:plan"}

    # --------------------------------------------------------------------------
    # ACT II: Permitted Read-Only Planning Search
    # --------------------------------------------------------------------------
    plan_resp = frontend_client.post(
        "/api/travel/plan",
        json={
            "user_id": "contractor-202",
            "user_name": "Sam Taylor",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 2,
            "budget_usd": 1000.0,
            "scenario_mode": "act3_contractor_obo",
        },
    )
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()

    proposals = plan_data.get("booking_proposals", {})
    assert "selected_flight" in proposals
    assert "selected_hotel" in proposals

    # --------------------------------------------------------------------------
    # ACT III: Direct Reservation Blocked by MCP Sidecar (-32002)
    # --------------------------------------------------------------------------
    direct_reserve = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
            "x-consul-hitl-evidence": "hitl-sig-forged-or-unauthorized",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act3-reserve",
            "method": "tools/call",
            "params": {
                "name": "reserve_flight",
                "arguments": {
                    "flight_number": "UA-442",
                    "passenger_name": "Sam Taylor",
                    "origin": "JFK",
                    "destination": "SFO",
                },
            },
        },
    )
    assert direct_reserve.status_code == 200
    res_json = direct_reserve.json()
    assert "error" in res_json
    assert res_json["error"]["code"] == -32002
    assert "Identity Plane OBO Verification Denied" in res_json["error"]["message"]
    assert "booking:reserve" in res_json["error"]["message"]

    # --------------------------------------------------------------------------
    # ACT IV: Unauthorized GDS Egress Blocked by Terminating Gateway (403)
    # --------------------------------------------------------------------------
    egress_resp = terminating_gw_client.post(
        "/external/mcp/ground-transport",
        headers={
            "Authorization": "Bearer gds_token_9918",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        },
        json={"destination": "San Francisco", "rental_days": 2},
    )
    assert egress_resp.status_code == 403
    assert "partner:gds_egress" in egress_resp.json().get("detail", "")

    # --------------------------------------------------------------------------
    # ACT V: Security Audit & Interception Telemetry
    # --------------------------------------------------------------------------
    interceptions = plan_data.get("governance_interceptions", [])
    assert len(interceptions) >= 1
    codes = [i.get("code") for i in interceptions]
    assert -32002 in codes or 403 in codes


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario3_act1_obo_token_minting(frontend_client):
    """Act I In-depth: Validates IBM Verify OBO token issuance for contractor-202."""
    resp = frontend_client.post("/api/auth/obo-token", json={"user_id": "contractor-202"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["obo_subject"] == "contractor-202"
    assert "booking:reserve" not in data["scopes"]


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario3_act2_permitted_weather_lookup(weather_server_client):
    """Act II In-depth: Contractor can invoke weather lookup tool without restriction."""
    resp = weather_server_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/weather-agent",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act2-weather",
            "method": "tools/call",
            "params": {"name": "get_weather_forecast", "arguments": {"destination": "San Francisco"}},
        },
    )
    assert resp.status_code == 200
    assert "daily_forecast" in resp.json().get("result", {})


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario3_act3_hotel_reservation_denied(hotel_mcp_client):
    """Act III In-depth: Contractor attempting reserve_hotel is denied with -32002."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
            "x-consul-hitl-evidence": "hitl-sig-valid",
        },
        json={
            "jsonrpc": "2.0",
            "id": "act3-hotel",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Sam Taylor"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32002


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario3_act4_ground_transport_egress_denied(terminating_gw_client):
    """Act IV In-depth: Terminating Gateway blocks ground transport egress with HTTP 403."""
    resp = terminating_gw_client.post(
        "/external/mcp/ground-transport",
        headers={
            "Authorization": "Bearer gds_token_9918",
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={"destination": "San Francisco", "rental_days": 2},
    )
    assert resp.status_code == 403


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario3_act5_audit_stream_logging(frontend_client):
    """Act V In-depth: Verifies audit trail logs interception."""
    frontend_client.post(
        "/api/travel/plan",
        json={
            "user_id": "contractor-202",
            "user_name": "Sam Taylor",
            "scenario_mode": "act3_contractor_obo",
        },
    )
    resp = frontend_client.get("/api/travel/audit-stream")
    assert resp.status_code == 200
    events = resp.json().get("audit_events", [])
    assert len(events) > 0
