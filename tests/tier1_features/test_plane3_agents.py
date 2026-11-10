"""
Tier 1 Feature Tests — Architectural Plane 3: Agent Plane + Multi-Agent Orchestration & Governance
Covers:
- Feature 11: Baseline Multi-Agent Trip Planning (5 tests)
- Feature 13: Act 2a: MCP Per-Tool Invocation Policy (5 tests)
- Feature 14: Act 2b: Cryptographic HITL Approval Gate (5 tests)
- Feature 15: Act 3: Identity Plane RFC 8693 OBO Delegation (5 tests)
Total: 20 tests
"""
import pytest
from fastapi.testclient import TestClient

BOOKING_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"
ADMIN_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/finance-admin-agent"


# ==============================================================================
# Feature 11: Baseline Multi-Agent Trip Planning
# ==============================================================================
@pytest.mark.tier1
@pytest.mark.asyncio
async def test_f11_01_orchestrator_trip_plan(mesh_client):
    """Verify trip planning returns plan_ready_for_review with detailed itinerary."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 4,
            "budget_usd": 2500.0,
            "trip_purpose": "Summit",
            "scenario_mode": "normal",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "plan_ready_for_review"
    assert "trip_id" in data
    assert "booking_proposals" in data
    assert "weather_advisory" in data


@pytest.mark.tier1
@pytest.mark.asyncio
async def test_f11_02_weather_analysis_included(mesh_client):
    """Verify planned trip includes weather advisory and daily forecast breakdown."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 4,
            "budget_usd": 2500.0,
            "trip_purpose": "Summit",
            "scenario_mode": "normal",
        },
    )
    assert resp.status_code == 200
    weather = resp.json().get("weather_advisory", {})
    assert "forecast_summary" in weather
    assert "daily_breakdown" in weather
    assert len(weather["daily_breakdown"]) > 0


@pytest.mark.tier1
@pytest.mark.asyncio
async def test_f11_03_hotel_flight_selected(mesh_client):
    """Verify planned trip selects matching flight and hotel options."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 4,
            "budget_usd": 2500.0,
            "trip_purpose": "Summit",
            "scenario_mode": "normal",
        },
    )
    assert resp.status_code == 200
    bookings = resp.json().get("booking_proposals", {})
    assert "selected_flight" in bookings
    assert "selected_hotel" in bookings
    assert bookings["selected_flight"].get("flight_number") == "UA-442"
    assert "The Westin" in bookings["selected_hotel"].get("name", "")


@pytest.mark.tier1
@pytest.mark.asyncio
async def test_f11_04_budget_calculation(mesh_client):
    """Verify budget USD calculation and within_budget flag."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 4,
            "budget_usd": 2500.0,
            "trip_purpose": "Summit",
            "scenario_mode": "normal",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    total_est = data.get("total_estimated_usd", 0)
    assert total_est > 0
    assert data.get("within_budget") is True


@pytest.mark.tier1
@pytest.mark.asyncio
async def test_f11_05_obo_delegation_chain(mesh_client):
    """Verify response includes 3-hop OBO delegation chain metadata."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 4,
            "budget_usd": 2500.0,
            "trip_purpose": "Summit",
            "scenario_mode": "normal",
        },
    )
    assert resp.status_code == 200
    chain = resp.json().get("obo_delegation_chain", [])
    assert len(chain) >= 2
    assert any("weather-agent" in str(c.get("actor", "")) for c in chain)
    assert any("booking-agent" in str(c.get("actor", "")) for c in chain)


# ==============================================================================
# Feature 13: Act 2a: MCP Per-Tool Invocation Policy
# ==============================================================================
@pytest.mark.tier1
def test_f13_01_tools_list_discovery(hotel_mcp_client, flight_mcp_client):
    """Verify tools/list exposes full catalog independently of caller permissions."""
    h_resp = hotel_mcp_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "list-1", "method": "tools/list", "params": {}},
    )
    assert h_resp.status_code == 200
    tools = [t["name"] for t in h_resp.json()["result"]["tools"]]
    assert "search_hotels" in tools
    assert "reserve_hotel" in tools
    assert "override_hotel_rate" in tools

    f_resp = flight_mcp_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "list-2", "method": "tools/list", "params": {}},
    )
    assert f_resp.status_code == 200
    f_tools = [t["name"] for t in f_resp.json()["result"]["tools"]]
    assert "search_flights" in f_tools
    assert "reserve_flight" in f_tools
    assert "cancel_all_corporate_bookings" in f_tools


@pytest.mark.tier1
def test_f13_02_authorized_tool_call(hotel_mcp_client):
    """Verify booking-agent can invoke search_hotels without denial."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {"name": "search_hotels", "arguments": {"destination": "San Francisco"}},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert "available_hotels" in data["result"]
    assert len(data["result"]["available_hotels"]) > 0


@pytest.mark.tier1
def test_f13_03_per_tool_policy_denial_override_rate(hotel_mcp_client):
    """Verify booking-agent calling override_hotel_rate is denied with error code -32001."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
        },
        json={
            "jsonrpc": "2.0",
            "id": "call-2",
            "method": "tools/call",
            "params": {
                "name": "override_hotel_rate",
                "arguments": {"hotel_id": "HTL-SFO-01", "override_rate_usd": 50.0},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32001
    assert "Per-Tool Policy Denied" in data["error"]["message"]


@pytest.mark.tier1
def test_f13_04_per_tool_policy_denial_cancel_all(flight_mcp_client):
    """Verify booking-agent calling cancel_all_corporate_bookings is denied with error code -32001."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
        },
        json={
            "jsonrpc": "2.0",
            "id": "call-3",
            "method": "tools/call",
            "params": {"name": "cancel_all_corporate_bookings", "arguments": {"reason": "Test"}},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32001
    assert "Per-Tool Policy Denied" in data["error"]["message"]


@pytest.mark.tier1
def test_f13_05_unknown_tool_error(hotel_mcp_client):
    """Verify calling non-existent tool name returns JSON-RPC error -32601."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": BOOKING_AGENT_SPIFFE},
        json={
            "jsonrpc": "2.0",
            "id": "call-4",
            "method": "tools/call",
            "params": {"name": "non_existent_tool", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32601
    assert "Unknown MCP tool" in data["error"]["message"]


# ==============================================================================
# Feature 14: Act 2b: Cryptographic HITL Approval Gate
# ==============================================================================
@pytest.mark.tier1
def test_f14_01_hotel_reserve_requires_hitl(hotel_mcp_client):
    """Verify reserve_hotel without HITL token returns JSON-RPC error -32003."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-obo-user-id": "traveler-101",
        },
        json={
            "jsonrpc": "2.0",
            "id": "hitl-1",
            "method": "tools/call",
            "params": {
                "name": "reserve_hotel",
                "arguments": {
                    "hotel_id": "HTL-SFO-01",
                    "guest_name": "Alex Mercer",
                    "nights": 4,
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32003
    assert "HITL" in data["error"]["message"]


@pytest.mark.tier1
def test_f14_02_flight_reserve_requires_hitl(flight_mcp_client):
    """Verify reserve_flight without HITL token returns JSON-RPC error -32003."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-obo-user-id": "traveler-101",
        },
        json={
            "jsonrpc": "2.0",
            "id": "hitl-2",
            "method": "tools/call",
            "params": {
                "name": "reserve_flight",
                "arguments": {
                    "flight_number": "UA-442",
                    "passenger_name": "Alex Mercer",
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32003
    assert "HITL" in data["error"]["message"]


@pytest.mark.tier1
def test_f14_03_hotel_reserve_with_hitl_evidence(hotel_mcp_client):
    """Verify reserve_hotel with hitl-sig-* confirms booking reservation."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-obo-user-id": "traveler-101",
            "x-consul-hitl-evidence": "hitl-sig-verified-12345678",
        },
        json={
            "jsonrpc": "2.0",
            "id": "hitl-3",
            "method": "tools/call",
            "params": {
                "name": "reserve_hotel",
                "arguments": {
                    "hotel_id": "HTL-SFO-01",
                    "guest_name": "Alex Mercer",
                    "nights": 4,
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert data["result"]["status"] == "confirmed"
    assert "booking_reference" in data["result"]
    assert data["result"]["hitl_evidence_verified"] == "hitl-sig-verified-12345678"


@pytest.mark.tier1
def test_f14_04_flight_reserve_with_hitl_evidence(flight_mcp_client):
    """Verify reserve_flight with hitl-sig-* confirms airline ticket."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-obo-user-id": "traveler-101",
            "x-consul-hitl-evidence": "hitl-sig-verified-12345678",
        },
        json={
            "jsonrpc": "2.0",
            "id": "hitl-4",
            "method": "tools/call",
            "params": {
                "name": "reserve_flight",
                "arguments": {
                    "flight_number": "UA-442",
                    "passenger_name": "Alex Mercer",
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert data["result"]["status"] == "ticket_confirmed"
    assert "pnr" in data["result"]
    assert data["result"]["hitl_evidence_verified"] == "hitl-sig-verified-12345678"


@pytest.mark.tier1
@pytest.mark.asyncio
async def test_f14_05_review_action_mints_signature(mesh_client):
    """Verify /api/travel/review-action mints signature and completes booking."""
    plan_resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 4,
            "budget_usd": 2500.0,
            "trip_purpose": "Summit",
            "scenario_mode": "normal",
        },
    )
    trip_id = plan_resp.json()["trip_id"]

    review_resp = await mesh_client.post(
        "/api/travel/review-action",
        json={"trip_id": trip_id, "action": "APPROVE", "approver": "Alex Mercer"},
    )
    assert review_resp.status_code == 200
    data = review_resp.json()
    assert data.get("status") == "APPROVED_AND_BOOKED"
    token = data.get("details", {}).get("hitl_evidence_token", "")
    assert token.startswith("hitl-sig-")


# ==============================================================================
# Feature 15: Act 3: Identity Plane RFC 8693 OBO Delegation
# ==============================================================================
@pytest.mark.tier1
def test_f15_01_obo_token_exchange_alex(frontend_client):
    """Verify traveler-101 receives 4 scopes including booking:reserve."""
    resp = frontend_client.post("/api/auth/obo-token", json={"user_id": "traveler-101"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["obo_subject"] == "traveler-101"
    assert "booking:reserve" in data["scopes"]
    assert "partner:gds_egress" in data["scopes"]
    assert "obo_delegation_token" in data


@pytest.mark.tier1
def test_f15_02_obo_token_exchange_sam(frontend_client):
    """Verify contractor-202 is restricted to travel:read and travel:plan scopes."""
    resp = frontend_client.post("/api/auth/obo-token", json={"user_id": "contractor-202"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["obo_subject"] == "contractor-202"
    assert "travel:read" in data["scopes"]
    assert "travel:plan" in data["scopes"]
    assert "booking:reserve" not in data["scopes"]
    assert "partner:gds_egress" not in data["scopes"]


@pytest.mark.tier1
def test_f15_03_contractor_search_permitted(flight_mcp_client):
    """Verify contractor can search flights with travel:plan scope."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "obo-1",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SFO"}},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert "available_flights" in data["result"]


@pytest.mark.tier1
def test_f15_04_contractor_reserve_denied(flight_mcp_client):
    """Verify contractor reserve_flight is denied with error code -32002 (OBO_SCOPE_DENIED)."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
            "x-consul-hitl-evidence": "hitl-sig-any-token",
        },
        json={
            "jsonrpc": "2.0",
            "id": "obo-2",
            "method": "tools/call",
            "params": {
                "name": "reserve_flight",
                "arguments": {"flight_number": "UA-442", "passenger_name": "Sam Taylor"},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32002
    assert "OBO" in data["error"]["message"]


@pytest.mark.tier1
def test_f15_05_contractor_gds_egress_denied(external_mcp_client):
    """Verify contractor lacking partner:gds_egress is rejected with HTTP 403 Forbidden."""
    resp = external_mcp_client.post(
        "/external/mcp/ground-transport",
        headers={
            "Authorization": "Bearer vault:secret/data/partners/amadeus#gds_token_9918",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={"destination": "San Francisco", "days": 4, "vehicle": "Executive Sedan"},
    )
    assert resp.status_code == 403
    assert "obo denied" in resp.json().get("detail", "").lower()
