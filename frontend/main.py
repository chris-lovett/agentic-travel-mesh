"""
Review UI Backend & Experience UI
Provides the interactive Traveler Workspace, Human-in-the-Loop (HITL) approval flows,
and IBM Verify On-Behalf-Of (OBO) token exchange.
"""
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import httpx
import os
import time

app = FastAPI(title="CAMP Experience UI & Review Backend", version="1.0.0")

# Mount Static Assets
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gw:10000")
BOOKING_AGENT_URL = os.getenv("BOOKING_AGENT_URL", "http://booking-agent:8086")

# In-memory storage for active trip proposals and HITL approval states
trips_database: Dict[str, Any] = {}
audit_events: List[Dict[str, Any]] = []

class UserTripSubmission(BaseModel):
    user_id: str = "traveler-101"
    user_name: str = "Alex Mercer"
    origin: str = "JFK"
    destination: str = "San Francisco"
    duration_days: int = 4
    budget_usd: float = 2500.0
    trip_purpose: str = "HashiCorp & AI Architecture Summit"
    notes: Optional[str] = "Prefer hotels with business center"

class ApprovalAction(BaseModel):
    trip_id: str
    action: str # "APPROVE" or "REJECT"
    approver: str = "Manager / Finance Compliance"

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return FileResponse("frontend/static/index.html")

@app.post("/api/auth/obo-token")
async def exchange_obo_token(req: Dict[str, str]):
    """Simulates IBM Verify On-Behalf-Of (OBO) Token Exchange"""
    user_id = req.get("user_id", "traveler-101")
    return {
        "status": "authenticated",
        "identity_provider": "IBM Verify",
        "obo_subject": user_id,
        "token_type": "Bearer",
        "obo_delegation_token": f"ibm-verify-obo-{user_id}-{int(time.time())}",
        "scopes": ["travel:plan", "booking:reserve", "mcp:access"],
    }

@app.post("/api/travel/plan")
async def plan_trip(submission: UserTripSubmission):
    """Entry point from Traveler Workspace into the Agentic Fabric API Gateway"""
    obo_token = f"obo-{submission.user_id}"

    headers = {
        "x-obo-user-id": submission.user_id,
        "x-obo-token": obo_token,
        "x-tenant-id": "corporate-travel",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        # Call API Gateway entry point -> Travel Orchestrator
        resp = await client.post(
            f"{API_GATEWAY_URL}/agent/orchestrate/trip",
            json={
                "traveler_name": submission.user_name,
                "origin": submission.origin,
                "destination": submission.destination,
                "duration_days": submission.duration_days,
                "budget_usd": submission.budget_usd,
                "trip_purpose": submission.trip_purpose,
                "special_notes": submission.notes,
            },
            headers=headers,
        )
        plan_data = resp.json()

    trip_id = plan_data.get("trip_id", f"TRIP-{int(time.time())}")
    trips_database[trip_id] = plan_data

    audit_events.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": "TRIP_PLAN_GENERATED",
        "trip_id": trip_id,
        "traveler": submission.user_name,
        "destination": submission.destination,
        "cost_usd": plan_data.get("total_estimated_usd"),
        "trace_id": plan_data.get("trace_id"),
    })

    return plan_data

@app.post("/api/travel/review-action")
async def review_action(action: ApprovalAction):
    """Human-in-the-Loop (HITL) approval from the Review UI"""
    trip = trips_database.get(action.trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip proposal not found")

    if action.action == "APPROVE":
        booking_proposal = trip.get("booking_proposals", {})
        async with httpx.AsyncClient(timeout=15.0) as client:
            conf_resp = await client.post(
                f"{BOOKING_AGENT_URL}/agent/booking/confirm",
                json={
                    "traveler_name": trip.get("traveler"),
                    "nights": trip.get("duration_days"),
                    "flight": booking_proposal.get("selected_flight"),
                    "hotel": booking_proposal.get("selected_hotel"),
                    "ground_transport": booking_proposal.get("ground_transport"),
                },
            )
            confirmation_data = conf_resp.json()

        trip["status"] = "APPROVED_AND_BOOKED"
        trip["confirmation_details"] = confirmation_data
        result_message = "Trip itinerary approved. All flight, hotel, and transport reservations confirmed via MCP tools."
    else:
        trip["status"] = "REJECTED_BY_REVIEWER"
        result_message = "Trip proposal rejected. No reservations made."

    audit_events.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": f"TRIP_{action.action}D",
        "trip_id": action.trip_id,
        "approver": action.approver,
    })

    return {
        "trip_id": action.trip_id,
        "status": trip["status"],
        "message": result_message,
        "details": trip.get("confirmation_details"),
    }

@app.get("/api/travel/audit-stream")
async def get_audit_stream():
    return {"audit_events": list(reversed(audit_events[-20:]))}

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "experience-ui-backend"}
