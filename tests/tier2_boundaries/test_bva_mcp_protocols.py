"""
Tier 2 Boundary Value Analysis — Agent Plane & MCP Protocol Boundaries
Covers Boundary Value Analysis for Features 11, 13, 14, 15 (20 tests)
"""
import pytest
from fastapi.testclient import TestClient

BOOKING_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"
WEATHER_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/weather-agent"


# ==============================================================================
# Feature 11 BVA: Multi-Agent Trip Planning Parameter Boundaries
# ==============================================================================
@pytest.mark.tier2
@pytest.mark.asyncio
async def test_bva_f11_01_single_day_trip(mesh_client):
    """Verify trip planning with duration_days=1 calculates single day lodging and car rental."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 1,
            "budget_usd": 1500.0,
            "trip_purpose": "Single Day Meeting",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["duration_days"] == 1
    assert data["within_budget"] is True


@pytest.mark.tier2
@pytest.mark.asyncio
async def test_bva_f11_02_extended_trip(mesh_client):
    """Verify trip planning with duration_days=14 calculates costs without overflow."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 14,
            "budget_usd": 10000.0,
            "trip_purpose": "Extended Residency",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["duration_days"] == 14
    assert data["total_estimated_usd"] > 3000.0


@pytest.mark.tier2
@pytest.mark.asyncio
async def test_bva_f11_03_zero_budget_exceeded(mesh_client):
    """Verify budget_usd=0.0 flags within_budget=False while completing itinerary proposal."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 4,
            "budget_usd": 0.0,
            "trip_purpose": "Zero Budget Test",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["within_budget"] is False
    assert data["total_estimated_usd"] > 0


@pytest.mark.tier2
@pytest.mark.asyncio
async def test_bva_f11_04_excessive_budget(mesh_client):
    """Verify budget_usd=1000000.0 flags within_budget=True."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 3,
            "budget_usd": 1000000.0,
            "trip_purpose": "High Net Worth",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["within_budget"] is True


@pytest.mark.tier2
@pytest.mark.asyncio
async def test_bva_f11_05_unknown_destination_catalog_fallback(mesh_client):
    """Verify unknown destination falls back gracefully to default catalog options."""
    resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "Atlantis-Lost-City",
            "duration_days": 2,
            "budget_usd": 2000.0,
            "trip_purpose": "Exploration",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "booking_proposals" in data
    assert "selected_hotel" in data["booking_proposals"]


# ==============================================================================
# Feature 13 BVA: MCP Per-Tool Policy Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f13_01_missing_spiffe_header(hotel_mcp_client):
    """Verify request with empty x-caller-spiffe-id is denied for protected tool."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": ""},
        json={
            "jsonrpc": "2.0",
            "id": "bva-p1",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


@pytest.mark.tier2
def test_bva_f13_02_substring_spiffe_spoofing(hotel_mcp_client):
    """Verify partial substring match (booking-agent-rogue) is strictly rejected."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": f"{BOOKING_AGENT_SPIFFE}-rogue"},
        json={
            "jsonrpc": "2.0",
            "id": "bva-p2",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


@pytest.mark.tier2
def test_bva_f13_03_weather_agent_calling_flight_tool(flight_mcp_client):
    """Verify weather-agent cannot invoke flight booking tools."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": WEATHER_AGENT_SPIFFE},
        json={
            "jsonrpc": "2.0",
            "id": "bva-p3",
            "method": "tools/call",
            "params": {"name": "cancel_all_corporate_bookings", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32001


@pytest.mark.tier2
def test_bva_f13_04_invalid_jsonrpc_method_name(hotel_mcp_client):
    """Verify invalid method name returns JSON-RPC error -32600."""
    resp = hotel_mcp_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "bva-p4", "method": "tools/execute_action"},
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32600


@pytest.mark.tier2
def test_bva_f13_05_admin_caller_allowed(hotel_mcp_client):
    """Verify authorized finance-admin-agent can invoke override_hotel_rate with admin scope and HITL token."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/finance-admin-agent",
            "x-obo-scopes": "admin:rate_override",
            "x-consul-hitl-evidence": "hitl-sig-admin-verified",
        },
        json={
            "jsonrpc": "2.0",
            "id": "bva-p5",
            "method": "tools/call",
            "params": {
                "name": "override_hotel_rate",
                "arguments": {"hotel_id": "HTL-SF-01", "override_rate_usd": 150.0},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert data["result"]["status"] == "rate_overridden"


# ==============================================================================
# Feature 14 BVA: Cryptographic HITL Approval Gate Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f14_01_empty_hitl_header(hotel_mcp_client):
    """Verify empty string HITL evidence returns -32003."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "",
        },
        json={
            "jsonrpc": "2.0",
            "id": "hitl-b1",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32003


@pytest.mark.tier2
def test_bva_f14_02_wrong_hitl_prefix(hotel_mcp_client):
    """Verify evidence token with wrong prefix (sig-xxx instead of hitl-sig-xxx) returns -32003."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "sig-approved-12345",
        },
        json={
            "jsonrpc": "2.0",
            "id": "hitl-b2",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32003


@pytest.mark.tier2
def test_bva_f14_03_whitespace_only_hitl(flight_mcp_client):
    """Verify whitespace-only HITL evidence returns -32003."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "   ",
        },
        json={
            "jsonrpc": "2.0",
            "id": "hitl-b3",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32003


@pytest.mark.tier2
def test_bva_f14_04_read_only_tools_no_hitl_needed(hotel_mcp_client, flight_mcp_client):
    """Verify read-only tools (search_hotels, search_flights) do not require HITL evidence."""
    h_resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "ro-1",
            "method": "tools/call",
            "params": {"name": "search_hotels", "arguments": {"destination": "San Francisco"}},
        },
    )
    assert h_resp.status_code == 200
    assert "result" in h_resp.json()

    f_resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan",
        },
        json={
            "jsonrpc": "2.0",
            "id": "ro-2",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"destination": "San Francisco"}},
        },
    )
    assert f_resp.status_code == 200
    assert "result" in f_resp.json()


@pytest.mark.tier2
@pytest.mark.asyncio
async def test_bva_f14_05_review_action_reject(mesh_client):
    """Verify reviewer REJECT action terminates proposal without minting booking mutations."""
    plan = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 4,
            "budget_usd": 2500.0,
            "trip_purpose": "Reject Test",
        },
    )
    trip_id = plan.json()["trip_id"]

    review = await mesh_client.post(
        "/api/travel/review-action",
        json={"trip_id": trip_id, "action": "REJECT", "approver": "Finance Reviewer"},
    )
    assert review.status_code == 200
    data = review.json()
    assert data["status"] == "REJECTED_BY_REVIEWER"


# ==============================================================================
# Feature 15 BVA: RFC 8693 OBO Delegation Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f15_01_empty_obo_scopes_denied(flight_mcp_client):
    """Verify empty string x-obo-scopes fails authorization with -32002."""
    resp = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "",
            "x-consul-hitl-evidence": "hitl-sig-valid123",
        },
        json={
            "jsonrpc": "2.0",
            "id": "obo-b1",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32002


@pytest.mark.tier2
def test_bva_f15_02_single_insufficient_scope_denied(hotel_mcp_client):
    """Verify single scope travel:read is insufficient for booking:reserve tool."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "travel:read",
            "x-consul-hitl-evidence": "hitl-sig-valid123",
        },
        json={
            "jsonrpc": "2.0",
            "id": "obo-b2",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("error", {}).get("code") == -32002


@pytest.mark.tier2
def test_bva_f15_03_whitespace_padded_scopes(hotel_mcp_client):
    """Verify scopes with leading and trailing spaces are parsed and trimmed correctly."""
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": " travel:read , travel:plan , booking:reserve ",
            "x-consul-hitl-evidence": "hitl-sig-valid123",
        },
        json={
            "jsonrpc": "2.0",
            "id": "obo-b3",
            "method": "tools/call",
            "params": {
                "name": "reserve_hotel",
                "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Alex", "nights": 2},
            },
        },
    )
    assert resp.status_code == 200
    assert "result" in resp.json()
    assert resp.json()["result"]["status"] == "confirmed"


@pytest.mark.tier2
def test_bva_f15_04_large_scopes_csv_list(hotel_mcp_client):
    """Verify CSV list containing 20 scopes correctly identifies required permission."""
    many_scopes = ",".join([f"scope_{i}" for i in range(18)] + ["booking:reserve", "travel:read"])
    resp = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": many_scopes,
            "x-consul-hitl-evidence": "hitl-sig-valid123",
        },
        json={
            "jsonrpc": "2.0",
            "id": "obo-b4",
            "method": "tools/call",
            "params": {
                "name": "reserve_hotel",
                "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Alex", "nights": 2},
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("result", {}).get("status") == "confirmed"


@pytest.mark.tier2
def test_bva_f15_05_terminating_gw_missing_egress_scope_403(external_mcp_client):
    """Verify terminating gateway rejects caller lacking partner:gds_egress and booking:reserve with 403."""
    resp = external_mcp_client.post(
        "/external/mcp/ground-transport",
        headers={
            "Authorization": "Bearer vault:secret/data/partners/amadeus#gds_token_9918",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",  # contractor scopes
        },
        json={"destination": "San Francisco", "days": 4, "vehicle": "Executive Sedan"},
    )
    assert resp.status_code == 403
    assert "partner:gds_egress" in resp.json().get("detail", "")
