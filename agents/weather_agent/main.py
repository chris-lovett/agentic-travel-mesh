"""
Weather Agent (ai-agent workload + csl-mcp-sc Sidecar)
Queries Weather MCP server via Model Context Protocol (JSON-RPC 2.0) and uses travel-igw
(Consul AI Inference Gateway) for climate reasoning.
Contains ZERO OpenTelemetry or Vault credential code — all telemetry and auth are handled by mesh proxies.
"""
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
import httpx
import os
import time

app = FastAPI(title="CAMP Weather Agent (ai-agent)", version="2.1.0")

WEATHER_MCP_URL = os.getenv("WEATHER_MCP_URL", "http://weather-mcp:8082")
TRAVEL_IGW_URL = os.getenv("TRAVEL_IGW_URL", "http://travel-igw:10001")
AGENT_SPIFFE_ID = "spiffe://cluster.local/ns/camp-travel/sa/weather-agent"


class WeatherAnalysisRequest(BaseModel):
    destination: str
    duration_days: int = 4
    trip_type: str = "Business Conference"


@app.post("/agent/weather/analyze")
async def analyze_destination_weather(req: WeatherAnalysisRequest, request: Request):
    trace_id = request.headers.get("x-trace-id", f"trace-weather-{int(time.time()*1000)}")
    obo_user = request.headers.get("x-obo-user-id", "traveler-101")
    # Caller-side Identity Processor narrows OBO scopes specifically for weather-mcp hop
    narrowed_scopes = "travel:read,weather:forecast"

    mcp_headers = {
        "x-trace-id": trace_id,
        "x-caller-spiffe-id": AGENT_SPIFFE_ID,
        "x-obo-user-id": obo_user,
        "x-obo-scopes": narrowed_scopes,
        "x-consul-obo-token": f"obo-hop2-weather-{obo_user}",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Invoke Weather MCP Server via JSON-RPC 2.0 (governed by csl-mcp-sc)
        mcp_resp = await client.post(
            f"{WEATHER_MCP_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": f"rpc-weather-{int(time.time()*1000)}",
                "method": "tools/call",
                "params": {
                    "name": "get_weather_forecast",
                    "arguments": {"destination": req.destination, "days": req.duration_days},
                },
            },
            headers=mcp_headers,
        )
        rpc_body = mcp_resp.json()
        weather_data = rpc_body.get("result", {})

        # 2. Call travel-igw AI Inference Gateway (csl-inf-rt) to summarize packing insights
        llm_payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": f"Summarize weather for a {req.duration_days}-day {req.trip_type} trip to {req.destination}. Climate: {weather_data.get('summary')}. Advise packing list.",
                }
            ],
        }
        igw_headers = {
            "Content-Type": "application/json",
            "x-trace-id": trace_id,
            "x-caller-spiffe-id": AGENT_SPIFFE_ID,
            "x-tenant-id": "travel-planning-dept",
            "x-obo-user-id": obo_user,
            "x-simulate-llm-outage": request.headers.get("x-simulate-llm-outage", "false"),
        }
        try:
            llm_resp = await client.post(
                f"{TRAVEL_IGW_URL}/v1/chat/completions",
                json=llm_payload,
                headers=igw_headers,
            )
            llm_data = llm_resp.json()
            ai_notes = llm_data["choices"][0]["message"]["content"]
        except Exception:
            ai_notes = f"Climate is expected to be {weather_data.get('summary', 'mild')}. Pack appropriate light layers."

    return {
        "agent": "weather-agent",
        "spiffe_id": AGENT_SPIFFE_ID,
        "destination": req.destination,
        "forecast_summary": weather_data.get("summary", "Mild & Clear"),
        "packing_recommendations": weather_data.get("packing_recommendation", "Standard business attire"),
        "daily_breakdown": weather_data.get("daily_forecast", []),
        "ai_advisory": ai_notes,
        "obo_delegation_hop": {
            "caller": "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator",
            "actor": AGENT_SPIFFE_ID,
            "audience": "spiffe://cluster.local/ns/camp-travel/sa/weather-mcp",
            "subject": obo_user,
            "narrowed_scopes": narrowed_scopes.split(","),
        },
    }


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "weather-agent", "ai_role": "ai-agent"}
