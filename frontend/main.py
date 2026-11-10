"""
Review UI Backend & Experience UI
Provides the interactive Traveler Workspace, 5-Act Consul 2.1 Governance Showcase,
cryptographic Human-in-the-Loop (HITL) approval evidence signing, and IBM Verify On-Behalf-Of (OBO) token exchange.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import hashlib
import httpx
import os
import time

app = FastAPI(title="CAMP Experience UI & Review Backend", version="2.1.0")

if os.path.isdir("frontend/static"):
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gw:10000")
BOOKING_AGENT_URL = os.getenv("BOOKING_AGENT_URL", "http://booking-agent:8086")
INDIGO_ANALYTICS_URL = os.getenv("INDIGO_ANALYTICS_URL", "http://indigo-analytics:8089")
OTEL_COLLECTOR_URL = os.getenv("OTEL_COLLECTOR_URL", "http://otel-collector:4318")

trips_database: Dict[str, Any] = {}
audit_events: List[Dict[str, Any]] = []

# Customer IAM Persona Directory (IBM Verify OBO Profiles)
IAM_PERSONAS = {
    "traveler-101": {
        "user_id": "traveler-101",
        "user_name": "Alex Mercer",
        "role": "VP Engineering (Full Authority)",
        "scopes": ["travel:read", "travel:plan", "booking:reserve", "partner:gds_egress"],
        "max_budget_usd": 5000.0,
    },
    "contractor-202": {
        "user_id": "contractor-202",
        "user_name": "Sam Taylor",
        "role": "External Contractor (Restricted Authority)",
        "scopes": ["travel:read", "travel:plan"],
        "max_budget_usd": 1200.0,
    },
}


class UserTripSubmission(BaseModel):
    user_id: str = "traveler-101"
    user_name: str = "Alex Mercer"
    origin: str = "JFK"
    destination: str = "San Francisco"
    duration_days: int = 4
    budget_usd: float = 2500.0
    trip_purpose: str = "HashiCorp & AI Architecture Summit"
    notes: Optional[str] = "Prefer hotels with business center"
    scenario_mode: str = "normal"


class ApprovalAction(BaseModel):
    trip_id: str
    action: str  # "APPROVE" or "REJECT"
    approver: str = "Manager / Finance Compliance"


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    if os.path.exists("frontend/static/index.html"):
        return FileResponse("frontend/static/index.html")
    with open("/app/static/index.html", "r") as f:
        return f.read()


@app.post("/api/auth/obo-token")
async def exchange_obo_token(req: Dict[str, str]):
    """Simulates IBM Verify On-Behalf-Of (OBO) Token Exchange for the Consul Identity Plane"""
    user_id = req.get("user_id", "traveler-101")
    persona = IAM_PERSONAS.get(user_id, IAM_PERSONAS["traveler-101"])
    return {
        "status": "authenticated",
        "identity_provider": "IBM Verify (OAuth 2.0 / RFC 8693 OBO)",
        "obo_subject": persona["user_id"],
        "user_name": persona["user_name"],
        "role": persona["role"],
        "token_type": "Bearer",
        "obo_delegation_token": f"ibm-verify-obo-{persona['user_id']}-{int(time.time())}",
        "scopes": persona["scopes"],
    }


@app.post("/api/travel/plan")
async def plan_trip(submission: UserTripSubmission):
    """Entry point from Traveler Workspace into the Consul Agentic Runtime Fabric API Gateway"""
    effective_user_id = "contractor-202" if submission.scenario_mode == "act3_contractor_obo" else submission.user_id
    persona = IAM_PERSONAS.get(effective_user_id, IAM_PERSONAS["traveler-101"])
    scopes_csv = ",".join(persona["scopes"])

    headers = {
        "x-obo-user-id": persona["user_id"],
        "x-obo-scopes": scopes_csv,
        "x-obo-token": f"obo-{persona['user_id']}",
        "x-tenant-id": "corporate-travel",
        "x-simulate-llm-outage": "true" if submission.scenario_mode == "act1_llm_failover" else "false",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{API_GATEWAY_URL}/agent/orchestrate/trip",
            json={
                "traveler_name": persona["user_name"] if submission.scenario_mode == "act3_contractor_obo" else submission.user_name,
                "origin": submission.origin,
                "destination": submission.destination,
                "duration_days": submission.duration_days,
                "budget_usd": submission.budget_usd,
                "trip_purpose": submission.trip_purpose,
                "special_notes": submission.notes,
                "scenario_mode": submission.scenario_mode,
            },
            headers=headers,
        )
        plan_data = resp.json()

    trip_id = plan_data.get("trip_id", f"TRIP-{int(time.time())}")
    trips_database[trip_id] = plan_data

    interceptions = plan_data.get("governance_interceptions", [])
    event_name = "TRIP_PLAN_GENERATED"
    if submission.scenario_mode == "act1_llm_failover" or plan_data.get("ai_telemetry", {}).get("failover_triggered"):
        event_name = "AI_GW_FAILOVER_CLAUDE_SONNET"
    elif submission.scenario_mode == "act4_cycle_loop":
        event_name = "CYCLE_DETECTED_CIRCUIT_OPEN"
    elif interceptions:
        event_name = "MCP_SIDECAR_POLICY_INTERCEPTED"

    audit_events.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": event_name,
        "trip_id": trip_id,
        "traveler": plan_data.get("traveler", submission.user_name),
        "destination": submission.destination,
        "cost_usd": plan_data.get("total_estimated_usd"),
        "trace_id": plan_data.get("trace_id"),
        "scenario_mode": submission.scenario_mode,
    })

    return plan_data


@app.post("/api/travel/review-action")
async def review_action(action: ApprovalAction):
    """
    Human-in-the-Loop (HITL) approval from the Review UI.
    Generates a cryptographic approval evidence token bound to the original action
    so the csl-mcp-sc enforcement processor permits reserve_flight & reserve_hotel.
    """
    trip = trips_database.get(action.trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip proposal not found")

    if action.action == "APPROVE":
        booking_proposal = trip.get("booking_proposals", {})
        fl = booking_proposal.get("selected_flight", {}) or {}
        ht = booking_proposal.get("selected_hotel", {}) or {}

        # Mint cryptographic HITL evidence bound to (trip_id, approver, flight_number, hotel_id)
        evidence_payload = f"{action.trip_id}:{action.approver}:{fl.get('flight_number')}:{ht.get('id')}"
        sig = hashlib.sha256(evidence_payload.encode("utf-8")).hexdigest()[:16]
        hitl_evidence_token = f"hitl-sig-{sig}"

        obo_user = trip.get("obo_user", "traveler-101")
        obo_scopes = ",".join(trip.get("obo_scopes", ["travel:read", "travel:plan", "booking:reserve"]))

        async with httpx.AsyncClient(timeout=15.0) as client:
            conf_resp = await client.post(
                f"{BOOKING_AGENT_URL}/agent/booking/confirm",
                json={
                    "traveler_name": trip.get("traveler"),
                    "nights": trip.get("duration_days"),
                    "flight": fl,
                    "hotel": ht,
                    "ground_transport": booking_proposal.get("ground_transport"),
                    "obo_user": obo_user,
                    "obo_scopes": obo_scopes,
                    "hitl_evidence_token": hitl_evidence_token,
                },
                headers={
                    "x-obo-user-id": obo_user,
                    "x-obo-scopes": obo_scopes,
                    "x-consul-hitl-evidence": hitl_evidence_token,
                },
            )
            confirmation_data = conf_resp.json()

        if confirmation_data.get("status") == "blocked_by_mcp_sidecar":
            trip["status"] = "BLOCKED_BY_SIDECAR_POLICY"
            result_message = confirmation_data.get("error", {}).get("message", "Blocked by MCP Sidecar")
        else:
            trip["status"] = "APPROVED_AND_BOOKED"
            trip["confirmation_details"] = confirmation_data
            result_message = (
                f"HITL Evidence ({hitl_evidence_token}) verified by csl-mcp-sc. "
                f"All reservations confirmed via JSON-RPC MCP tools."
            )
    else:
        trip["status"] = "REJECTED_BY_REVIEWER"
        result_message = "Trip proposal rejected. No reservations made."

    audit_events.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": f"TRIP_{action.action}D",
        "trip_id": action.trip_id,
        "approver": action.approver,
        "destination": trip.get("destination"),
    })

    return {
        "trip_id": action.trip_id,
        "status": trip["status"],
        "message": result_message,
        "details": trip.get("confirmation_details"),
    }


@app.get("/api/governance/status")
async def get_governance_status():
    """Fetches live Agentic Analytics (csl-ag-ana) & Span Relay (csl-nod-rly) status"""
    indigo_data = {}
    traces_data = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            r1 = await client.get(f"{INDIGO_ANALYTICS_URL}/api/indigo/audit-summary")
            if r1.status_code == 200:
                indigo_data = r1.json()
        except Exception:
            pass
        try:
            r2 = await client.get(f"{OTEL_COLLECTOR_URL}/v1/traces")
            if r2.status_code == 200:
                traces_data = r2.json()
        except Exception:
            pass
    return {
        "indigo": indigo_data,
        "otel": traces_data,
        "personas": IAM_PERSONAS,
    }


@app.post("/api/governance/reset-circuit")
async def reset_circuit_breaker():
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.post(f"{INDIGO_ANALYTICS_URL}/api/indigo/circuit/reset", json={})
        data = resp.json()
    audit_events.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": "CIRCUIT_BREAKER_RESET",
        "trip_id": "SYSTEM",
        "destination": "booking-agent circuit -> CLOSED",
    })
    return data


@app.post("/api/governance/toggle-llm-outage")
async def toggle_llm_outage(body: Dict[str, Any]):
    flag = bool(body.get("simulate_primary_llm_outage", False))
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.post(
            f"{INDIGO_ANALYTICS_URL}/api/indigo/flags",
            json={"simulate_primary_llm_outage": flag},
        )
        data = resp.json()
    audit_events.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": f"LLM_OUTAGE_SIM_{'ON' if flag else 'OFF'}",
        "trip_id": "SYSTEM",
        "destination": "travel-igw (csl-inf-rt)",
    })
    return data


@app.get("/api/travel/audit-stream")
async def get_audit_stream():
    return {"audit_events": list(reversed(audit_events[-25:]))}


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "experience-ui-backend"}
