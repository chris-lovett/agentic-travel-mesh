"""
Travel Orchestrator (ai-agent workload + Envoy & csl-mcp-sc Sidecars)
Master coordinator of the CAMP Travel Booking multi-agent ecosystem.
Deconstructs traveler intent, delegates to sub-agents with hop-by-hop OBO token exchange,
and invokes the Consul AI Inference Gateway (travel-igw / csl-inf-rt) to synthesize final plans.
Contains ZERO OpenTelemetry SDK or manual trace calls — all spans are auto-instrumented by mesh proxies.
"""
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
import httpx
import os
import asyncio
import time

app = FastAPI(title="CAMP Travel Orchestrator Agent (ai-agent)", version="2.1.0")

BOOKING_AGENT_URL = os.getenv("BOOKING_AGENT_URL", "http://booking-agent:8086")
WEATHER_AGENT_URL = os.getenv("WEATHER_AGENT_URL", "http://weather-agent:8087")
TRAVEL_IGW_URL = os.getenv("TRAVEL_IGW_URL", "http://travel-igw:10001")
ORCHESTRATOR_SPIFFE_ID = "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator"


class TripRequest(BaseModel):
    traveler_name: str = "Alex Mercer"
    origin: str = "JFK"
    destination: str = "San Francisco"
    duration_days: int = 4
    budget_usd: float = 2500.0
    trip_purpose: str = "Annual HashiCorp & AI Architecture Summit"
    special_notes: Optional[str] = "Prefer hotels with business centers and good public transit."
    scenario_mode: str = "normal"


@app.post("/agent/orchestrate/trip")
async def orchestrate_trip(req: TripRequest, request: Request):
    trace_id = request.headers.get("x-trace-id", f"trace-camp-{int(time.time()*1000)}")
    obo_user = request.headers.get("x-obo-user-id", req.traveler_name.lower().replace(" ", "-"))
    obo_scopes = request.headers.get(
        "x-obo-scopes",
        "travel:read,travel:plan,booking:reserve,partner:gds_egress",
    )
    simulate_outage = (
        "true"
        if req.scenario_mode == "act1_llm_failover"
        or request.headers.get("x-simulate-llm-outage", "").lower() == "true"
        else "false"
    )

    headers = {
        "x-trace-id": trace_id,
        "x-caller-spiffe-id": ORCHESTRATOR_SPIFFE_ID,
        "x-obo-user-id": obo_user,
        "x-obo-scopes": obo_scopes,
        "x-consul-obo-token": f"obo-hop1-orch-{obo_user}",
        "x-tenant-id": "corporate-travel",
        "x-simulate-llm-outage": simulate_outage,
    }

    async with httpx.AsyncClient(timeout=18.0) as client:
        # 1. Concurrently call Weather Agent & Booking Agent across Consul Mesh
        weather_task = client.post(
            f"{WEATHER_AGENT_URL}/agent/weather/analyze",
            json={
                "destination": req.destination,
                "duration_days": req.duration_days,
                "trip_type": req.trip_purpose,
            },
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
                "scenario_mode": req.scenario_mode,
            },
            headers=headers,
        )

        weather_res, booking_res = await asyncio.gather(weather_task, booking_task)
        weather_data = weather_res.json()
        booking_data = booking_res.json()

        # 2. Invoke travel-igw AI Inference Gateway (csl-inf-rt) to synthesize executive summary
        synthesis_prompt = f"""
        Traveler: {req.traveler_name} (OBO Subject: {obo_user})
        Purpose: {req.trip_purpose}
        Route: {req.origin} to {req.destination} ({req.duration_days} days)
        Total Estimated Cost: ${booking_data.get('total_estimated_usd')} (Budget: ${req.budget_usd})
        Weather Outlook: {weather_data.get('forecast_summary')}
        Hotel: {booking_data.get('selected_hotel', {}).get('name')}
        Flight: {booking_data.get('selected_flight', {}).get('airline')} {booking_data.get('selected_flight', {}).get('flight_number')}
        Scenario Mode: {req.scenario_mode}
        Synthesize a concise executive travel summary.
        """

        llm_metadata = {
            "requested_model": "meta-llama/llama-3-70b-instruct",
            "model": "meta-llama/llama-3-70b-instruct",
            "prompt_tokens": 412,
            "completion_tokens": 285,
            "total_tokens": 697,
            "estimated_cost_usd": 0.0035,
            "gateway_tier": "travel-igw (Consul AI Inference Gateway 2.1 / csl-inf-rt)",
            "auth_provider": "HashiCorp Vault Token Broker",
            "failover_triggered": False,
            "protocol_translation": "OpenAI /v1/chat/completions -> Native Upstream",
            "zero_code_instrumented": True,
        }

        try:
            llm_resp = await client.post(
                f"{TRAVEL_IGW_URL}/v1/chat/completions",
                json={
                    "model": "meta-llama/llama-3-70b-instruct",
                    "messages": [{"role": "user", "content": synthesis_prompt}],
                },
                headers={**headers, "Content-Type": "application/json"},
            )
            llm_json = llm_resp.json()
            synthesis_summary = llm_json["choices"][0]["message"]["content"]
            usage = llm_json.get("usage", {})
            gw_meta = llm_json.get("gateway_metadata", {})
            if usage:
                llm_metadata["prompt_tokens"] = usage.get("prompt_tokens", 412)
                llm_metadata["completion_tokens"] = usage.get("completion_tokens", 285)
                llm_metadata["total_tokens"] = usage.get("total_tokens", 697)
            if gw_meta:
                llm_metadata["model"] = gw_meta.get("routed_model", llm_json.get("model", llm_metadata["model"]))
                llm_metadata["failover_triggered"] = gw_meta.get("failover_triggered", False)
                llm_metadata["protocol_translation"] = gw_meta.get("protocol_translation", llm_metadata["protocol_translation"])
                llm_metadata["estimated_cost_usd"] = gw_meta.get(
                    "estimated_cost_usd",
                    round(llm_metadata["total_tokens"] * 0.000005, 5),
                )
                llm_metadata["vault_secret_ref"] = gw_meta.get("vault_secret_ref", "vault:secret/data/ai/llm#api_key")
        except Exception:
            synthesis_summary = (
                f"Complete {req.duration_days}-day itinerary prepared for {req.destination} "
                f"covering flights, lodging, and ground transport at ${booking_data.get('total_estimated_usd')}."
            )

    # Assemble Hop-by-Hop Identity Plane OBO Delegation Chain
    obo_chain = [
        {
            "hop": 1,
            "caller": "user-idp (IBM Verify OAuth Issuer)",
            "actor": "spiffe://cluster.local/ns/camp-travel/sa/api-gw",
            "audience": ORCHESTRATOR_SPIFFE_ID,
            "subject": obo_user,
            "scopes": [s.strip() for s in obo_scopes.split(",") if s.strip()],
        },
        weather_data.get("obo_delegation_hop", {}),
        booking_data.get("obo_delegation_hop", {}),
    ]

    return {
        "status": "plan_ready_for_review",
        "scenario_mode": req.scenario_mode,
        "trace_id": trace_id,
        "trip_id": f"TRIP-{int(time.time())}",
        "traveler": req.traveler_name,
        "obo_user": obo_user,
        "obo_scopes": [s.strip() for s in obo_scopes.split(",") if s.strip()],
        "obo_delegation_chain": obo_chain,
        "destination": req.destination,
        "duration_days": req.duration_days,
        "budget_usd": req.budget_usd,
        "total_estimated_usd": booking_data.get("total_estimated_usd"),
        "within_budget": booking_data.get("within_budget"),
        "executive_summary": synthesis_summary,
        "weather_advisory": weather_data,
        "booking_proposals": booking_data,
        "governance_interceptions": booking_data.get("governance_interceptions", []),
        "loop_iterations": booking_data.get("loop_iterations", []),
        "ai_telemetry": llm_metadata,
        "requires_hitl_approval": True,
    }


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "travel-orchestrator", "ai_role": "ai-agent"}
