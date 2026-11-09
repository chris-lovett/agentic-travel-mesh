"""
Travel Orchestrator (Agent + Envoy Sidecars)
Master coordinator of the CAMP Travel Booking multi-agent ecosystem.
Deconstructs traveler intent, delegates to sub-agents, and synthesizes final plans.
"""
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
import httpx
import os
import asyncio
import time

app = FastAPI(title="CAMP Travel Orchestrator Agent", version="1.0.0")

BOOKING_AGENT_URL = os.getenv("BOOKING_AGENT_URL", "http://booking-agent:8086")
WEATHER_AGENT_URL = os.getenv("WEATHER_AGENT_URL", "http://weather-agent:8087")
TRAVEL_IGW_URL = os.getenv("TRAVEL_IGW_URL", "http://travel-igw:10001")
OTEL_COLLECTOR_URL = os.getenv("OTEL_COLLECTOR_URL", "http://otel-collector:4318")

class TripRequest(BaseModel):
    traveler_name: str = "Alex Mercer"
    origin: str = "JFK"
    destination: str = "San Francisco"
    duration_days: int = 4
    budget_usd: float = 2500.0
    trip_purpose: str = "Annual HashiCorp & AI Architecture Summit"
    special_notes: Optional[str] = "Prefer hotels with business centers and good public transit."

@app.post("/agent/orchestrate/trip")
async def orchestrate_trip(req: TripRequest, request: Request):
    trace_id = f"trace-camp-{int(time.time()*1000)}"
    obo_user = request.headers.get("x-obo-user-id", req.traveler_name.lower().replace(" ", "-"))

    headers = {
        "x-trace-id": trace_id,
        "x-obo-user-id": obo_user,
        "x-tenant-id": "corporate-travel",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Concurrently call Weather Agent & Booking Agent across Consul Mesh
        weather_task = client.post(
            f"{WEATHER_AGENT_URL}/agent/weather/analyze",
            json={"destination": req.destination, "duration_days": req.duration_days, "trip_type": req.trip_purpose},
            headers=headers,
        )
        booking_task = client.post(
            f"{BOOKING_AGENT_URL}/agent/booking/plan",
            json={
                "origin": req.origin,
                "destination": req.destination,
                "traveler_name": req.traveler_name,
                "nights": req.duration_days,
                "budget_usd": req.budget_usd,
                "needs_ground_transport": True,
            },
            headers=headers,
        )

        weather_res, booking_res = await asyncio.gather(weather_task, booking_task)
        weather_data = weather_res.json()
        booking_data = booking_res.json()

        # 2. Invoke travel-igw AI Gateway to synthesize executive summary
        synthesis_prompt = f"""
        Traveler: {req.traveler_name}
        Purpose: {req.trip_purpose}
        Route: {req.origin} to {req.destination} ({req.duration_days} days)
        Total Estimated Cost: ${booking_data.get('total_estimated_usd')} (Budget: ${req.budget_usd})
        Weather Outlook: {weather_data.get('forecast_summary')}
        Hotel: {booking_data.get('selected_hotel', {}).get('name')}
        Flight: {booking_data.get('selected_flight', {}).get('airline')} {booking_data.get('selected_flight', {}).get('flight_number')}
        
        Synthesize a professional 3-sentence travel overview ready for executive review and booking approval.
        """

        try:
            llm_resp = await client.post(
                f"{TRAVEL_IGW_URL}/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": synthesis_prompt}],
                },
                headers={**headers, "Content-Type": "application/json"},
            )
            synthesis_summary = llm_resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            synthesis_summary = f"Complete {req.duration_days}-day itinerary prepared for {req.destination} covering flights, lodging, and ground transport at ${booking_data.get('total_estimated_usd')}."

        # 3. Emit Trace Event to AI Observability Layer
        try:
            await client.post(
                f"{OTEL_COLLECTOR_URL}/v1/traces",
                json={
                    "trace_id": trace_id,
                    "service": "travel-orchestrator",
                    "user_obo": obo_user,
                    "tokens_used": 65,
                    "destination": req.destination,
                    "cost_usd": booking_data.get("total_estimated_usd"),
                },
                headers=headers,
            )
        except Exception:
            pass

    return {
        "status": "plan_ready_for_review",
        "trace_id": trace_id,
        "trip_id": f"TRIP-{int(time.time())}",
        "traveler": req.traveler_name,
        "destination": req.destination,
        "duration_days": req.duration_days,
        "budget_usd": req.budget_usd,
        "total_estimated_usd": booking_data.get("total_estimated_usd"),
        "within_budget": booking_data.get("within_budget"),
        "executive_summary": synthesis_summary,
        "weather_advisory": weather_data,
        "booking_proposals": booking_data,
        "requires_hitl_approval": True,
    }

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "travel-orchestrator"}
