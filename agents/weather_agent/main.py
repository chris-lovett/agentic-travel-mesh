"""
Weather Agent (Agent + Envoy Sidecars)
Queries Weather MCP server and uses travel-igw foundation model for climate reasoning.
"""
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
import httpx
import os

app = FastAPI(title="CAMP Weather Agent", version="1.0.0")

WEATHER_MCP_URL = os.getenv("WEATHER_MCP_URL", "http://weather-mcp:8082")
TRAVEL_IGW_URL = os.getenv("TRAVEL_IGW_URL", "http://travel-igw:10001")

class WeatherAnalysisRequest(BaseModel):
    destination: str
    duration_days: int = 4
    trip_type: str = "Business Conference"

@app.post("/agent/weather/analyze")
async def analyze_destination_weather(req: WeatherAnalysisRequest, request: Request):
    obo_user = request.headers.get("x-obo-user-id", "traveler-101")

    # 1. Query Weather MCP Tool over the Consul mesh
    async with httpx.AsyncClient(timeout=10.0) as client:
        mcp_resp = await client.post(
            f"{WEATHER_MCP_URL}/mcp/weather/forecast",
            json={"destination": req.destination, "days": req.duration_days},
        )
        weather_data = mcp_resp.json()

        # 2. Call travel-igw AI Gateway to summarize packing insights
        llm_payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": f"Summarize weather for a {req.duration_days}-day {req.trip_type} trip to {req.destination}. Climate: {weather_data['summary']}. Advise packing list.",
                }
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "x-tenant-id": "travel-planning-dept",
            "x-obo-user-id": obo_user,
        }
        try:
            llm_resp = await client.post(
                f"{TRAVEL_IGW_URL}/v1/chat/completions",
                json=llm_payload,
                headers=headers,
            )
            llm_data = llm_resp.json()
            ai_notes = llm_data["choices"][0]["message"]["content"]
        except Exception as e:
            ai_notes = f"Climate is expected to be {weather_data['summary']}. Pack appropriate light layers."

    return {
        "agent": "weather-agent",
        "destination": req.destination,
        "forecast_summary": weather_data["summary"],
        "packing_recommendations": weather_data["packing_recommendation"],
        "daily_breakdown": weather_data["daily_forecast"],
        "ai_advisory": ai_notes,
    }

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "weather-agent"}
