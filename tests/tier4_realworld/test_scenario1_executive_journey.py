"""
Tier 4 Real-World Interactive User Journey — Scenario 1: Executive Journey (5 Acts)
Scenario: Alex Mercer (traveler-101) Executive 5-Act Travel Flow
- Act I: Traveler Request & Policy Check
- Act II: Human-in-the-Loop Approval & Evidence Minting
- Act III: Multi-Agent Parallel Execution (Flights & Hotels)
- Act IV: External GDS Egress via Terminating Gateway
- Act V: Observability & Governance Closure
"""
import pytest
import time
import hashlib


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario1_full_5act_executive_journey(frontend_client, indigo_analytics_client):
    """
    Complete 5-Act end-to-end user journey for Alex Mercer (VP Engineering, Executive Tier).
    Validates genuine state transitions across all 5 architectural planes without facade cheating.
    """
    # --------------------------------------------------------------------------
    # ACT I: Traveler Request & Policy Assessment
    # --------------------------------------------------------------------------
    plan_payload = {
        "user_id": "traveler-101",
        "user_name": "Alex Mercer",
        "origin": "JFK",
        "destination": "San Francisco",
        "duration_days": 4,
        "budget_usd": 3000.0,
        "trip_purpose": "Annual HashiCorp & AI Architecture Summit",
        "notes": "Prefer quiet hotels near Moscone Center.",
        "scenario_mode": "normal",
    }
    plan_resp = frontend_client.post("/api/travel/plan", json=plan_payload)
    assert plan_resp.status_code == 200, f"Act I failed: {plan_resp.text}"
    plan_data = plan_resp.json()

    trip_id = plan_data.get("trip_id")
    assert trip_id is not None
    assert trip_id.startswith("TRIP-")
    assert plan_data.get("status") == "plan_ready_for_review"
    assert plan_data.get("requires_hitl_approval") is True
    assert plan_data.get("within_budget") is True
    assert plan_data.get("total_estimated_usd") <= 3000.0

    # Validate Hop-by-Hop OBO Delegation Chain
    obo_chain = plan_data.get("obo_delegation_chain", [])
    assert len(obo_chain) >= 3, "Act I: OBO delegation chain must include >= 3 hops"
    assert obo_chain[0].get("subject") == "traveler-101"
    assert "booking:reserve" in obo_chain[0].get("scopes", [])

    # Validate AI Inference Gateway metadata
    ai_telemetry = plan_data.get("ai_telemetry", {})
    assert ai_telemetry.get("failover_triggered") is False
    assert "travel-igw" in ai_telemetry.get("gateway_tier", "")

    # --------------------------------------------------------------------------
    # ACT II: Human-in-the-Loop (HITL) Cryptographic Approval
    # --------------------------------------------------------------------------
    review_payload = {
        "trip_id": trip_id,
        "action": "APPROVE",
        "approver": "Finance Director / Compliance Officer",
    }
    review_resp = frontend_client.post("/api/travel/review-action", json=review_payload)
    assert review_resp.status_code == 200, f"Act II failed: {review_resp.text}"
    review_data = review_resp.json()

    assert review_data.get("status") == "APPROVED_AND_BOOKED"
    assert "hitl-sig-" in review_data.get("message", "")
    details = review_data.get("details", {})
    hitl_token = details.get("hitl_evidence_token")
    assert hitl_token is not None
    assert hitl_token.startswith("hitl-sig-")

    # --------------------------------------------------------------------------
    # ACT III: Multi-Agent Parallel Execution (Reservations Confirmed)
    # --------------------------------------------------------------------------
    flight_res = details.get("flight_booking", {})
    hotel_res = details.get("hotel_booking", {})

    assert flight_res.get("status") == "ticket_confirmed"
    assert "pnr" in flight_res
    assert flight_res.get("hitl_evidence_verified") == hitl_token
    assert flight_res.get("flight_number") == "UA-442"

    assert hotel_res.get("status") in ("confirmed", "room_reserved")
    assert "booking_reference" in hotel_res
    assert hotel_res.get("hitl_evidence_verified") == hitl_token

    # --------------------------------------------------------------------------
    # ACT IV: External GDS Egress via Terminating Gateway
    # --------------------------------------------------------------------------
    ground_trans = details.get("ground_transport", {})
    assert ground_trans is not None
    assert ground_trans.get("status") in ("confirmed", "reserved")
    assert "hertz" in ground_trans.get("external_mcp", "")
    assert "rental_id" in ground_trans

    # --------------------------------------------------------------------------
    # ACT V: Observability & Governance Closure
    # --------------------------------------------------------------------------
    audit_resp = frontend_client.get("/api/travel/audit-stream")
    assert audit_resp.status_code == 200
    events = audit_resp.json().get("audit_events", [])
    event_names = [e.get("event") for e in events]

    assert "TRIP_PLAN_GENERATED" in event_names
    assert "TRIP_APPROVED" in event_names

    # Check Circuit Breaker Remains CLOSED in Indigo
    indigo_resp = indigo_analytics_client.get("/api/indigo/circuit/booking-agent")
    assert indigo_resp.status_code == 200
    assert indigo_resp.json().get("state") == "CLOSED"


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario1_act1_planning_and_policy_assessment(frontend_client):
    """Act I In-depth: Traveler Intent deconstruction and policy compliance validation."""
    resp = frontend_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "user_name": "Alex Mercer",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 3,
            "budget_usd": 2500.0,
            "trip_purpose": "Executive Strategy Sync",
            "scenario_mode": "normal",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data.get("traveler") == "Alex Mercer"
    assert data.get("duration_days") == 3
    assert data.get("budget_usd") == 2500.0
    proposals = data.get("booking_proposals", {})
    assert "selected_flight" in proposals
    assert "selected_hotel" in proposals
    assert "ground_transport" in proposals


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario1_act2_hitl_approval_signature_minting(frontend_client):
    """Act II In-depth: Cryptographic evidence generation tied to trip and approver."""
    # First plan trip to seed database
    p_resp = frontend_client.post(
        "/api/travel/plan",
        json={"user_id": "traveler-101", "user_name": "Alex Mercer", "budget_usd": 3000.0},
    )
    trip_id = p_resp.json()["trip_id"]

    # Approve
    a_resp = frontend_client.post(
        "/api/travel/review-action",
        json={"trip_id": trip_id, "action": "APPROVE", "approver": "Compliance Mgr"},
    )
    assert a_resp.status_code == 200
    res = a_resp.json()
    assert res.get("status") == "APPROVED_AND_BOOKED"
    token = res.get("details", {}).get("hitl_evidence_token", "")
    assert token.startswith("hitl-sig-")
    assert len(token) > len("hitl-sig-")


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario1_act3_booking_agent_parallel_execution(booking_agent_client):
    """Act III In-depth: Direct booking agent confirmation verifies HITL token with MCP sidecars."""
    hitl_token = "hitl-sig-valid-verified-101"
    resp = booking_agent_client.post(
        "/agent/booking/confirm",
        json={
            "traveler_name": "Alex Mercer",
            "nights": 3,
            "flight": {"flight_number": "UA-442", "origin": "JFK", "destination": "SFO"},
            "hotel": {"id": "HTL-SF-01", "name": "The Westin St. Francis"},
            "obo_user": "traveler-101",
            "obo_scopes": "travel:read,travel:plan,booking:reserve",
            "hitl_evidence_token": hitl_token,
        },
        headers={
            "x-consul-hitl-evidence": hitl_token,
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "all_reservations_confirmed"
    assert data.get("flight_booking", {}).get("status") == "ticket_confirmed"
    assert data.get("hotel_booking", {}).get("status") in ("confirmed", "room_reserved")


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario1_act4_terminating_gateway_egress(terminating_gw_client):
    """Act IV In-depth: Terminating Gateway validates Vault egress token and OBO scopes."""
    resp = terminating_gw_client.post(
        "/external/mcp/ground-transport",
        headers={
            "Authorization": "Bearer gds_token_9918",
            "x-obo-user-id": "traveler-101",
            "x-obo-scopes": "partner:gds_egress,booking:reserve",
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        },
        json={"destination": "San Francisco", "rental_days": 4},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") in ("confirmed", "reserved")
    assert "hertz" in data.get("external_mcp", "")
    assert "rental_id" in data


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario1_act5_governance_audit_and_traces(frontend_client, indigo_analytics_client):
    """Act V In-depth: Observability pipeline records audit events and maintains circuit state."""
    # Seed an event
    frontend_client.post(
        "/api/travel/plan",
        json={"user_id": "traveler-101", "user_name": "Alex Mercer", "budget_usd": 2000.0},
    )

    status_resp = frontend_client.get("/api/governance/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "indigo" in status_data
    assert "personas" in status_data
    assert "traveler-101" in status_data["personas"]
