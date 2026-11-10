"""
Weather Server (mcp-server + csl-mcp-sc Sidecar Enforcement)
Supports:
- Real Model Context Protocol (MCP) JSON-RPC 2.0 endpoint (POST /mcp: tools/list, tools/call)
- Zero-code auto-instrumentation via csl-mcp-sc
- Backwards-compatible REST endpoint (/mcp/weather/forecast)
"""
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
import httpx
import os
import random
import time

app = FastAPI(title="Weather MCP Server (csl-mcp-sc governed)", version="2.1.0")

OTEL_COLLECTOR_URL = os.getenv("OTEL_COLLECTOR_URL", "http://otel-collector:4318")


class WeatherQuery(BaseModel):
    destination: str
    days: int = 4


WEATHER_DATABASE = {
    "san francisco": {"temp_c": 18, "condition": "Partly Cloudy / Coastal Fog", "precipitation_chance": 15, "packing": "Light layers, light jacket, walking shoes"},
    "new york": {"temp_c": 22, "condition": "Sunny", "precipitation_chance": 5, "packing": "Comfortable summer/fall attire, umbrella just in case"},
    "london": {"temp_c": 15, "condition": "Light Rain / Overcast", "precipitation_chance": 65, "packing": "Waterproof jacket, umbrella, warm layers"},
    "tokyo": {"temp_c": 24, "condition": "Clear & Mild", "precipitation_chance": 10, "packing": "Breathable clothing, comfortable sneakers"},
    "paris": {"temp_c": 20, "condition": "Breezy & Sunny", "precipitation_chance": 20, "packing": "Smart casual, cardigan or light coat"},
}


def _execute_weather_forecast(destination: str, days: int) -> Dict[str, Any]:
    city_key = destination.strip().lower()
    data = WEATHER_DATABASE.get(
        city_key,
        {
            "temp_c": 21,
            "condition": "Mild & Clear",
            "precipitation_chance": 20,
            "packing": "Standard seasonal attire and a light jacket",
        },
    )
    forecast = []
    base_temp = data["temp_c"]
    for day in range(1, days + 1):
        forecast.append({
            "day": f"Day {day}",
            "high_c": base_temp + 2,
            "low_c": base_temp - 3,
            "condition": data["condition"],
            "precipitation": f"{data['precipitation_chance']}%",
        })
    return {
        "mcp_tool": "weather_server",
        "destination": destination,
        "summary": f"{data['condition']}, averaging {base_temp}°C ({int(base_temp * 9/5 + 32)}°F)",
        "packing_recommendation": data["packing"],
        "daily_forecast": forecast,
    }


async def emit_weather_mcp_span(trace_id: str, caller_spiffe: str, obo_user: str, args: Dict[str, Any], res: Dict[str, Any]):
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            await client.post(
                f"{OTEL_COLLECTOR_URL}/v1/traces",
                json={
                    "trace_id": trace_id,
                    "span_type": "mcp_tool_call",
                    "span_name": "csl-mcp-sc.weather-mcp.get_weather_forecast",
                    "instrumented_by": "csl-mcp-sc (MCP Sidecar Zero-Code ext-proc)",
                    "service": "weather-mcp",
                    "mcp_server": "weather-mcp",
                    "agent_spiffe_id": caller_spiffe,
                    "user_obo": obo_user,
                    "tool_name": "get_weather_forecast",
                    "tool_arguments": args,
                    "tool_result": {"summary": res.get("summary")},
                    "tokens_used": 14,
                },
            )
    except Exception:
        pass


@app.post("/mcp")
async def mcp_jsonrpc_endpoint(request: Request):
    payload = await request.json()
    rpc_id = payload.get("id", "rpc-1")
    method = payload.get("method", "tools/list")
    params = payload.get("params", {})

    trace_id = request.headers.get("x-trace-id", f"trace-mcp-{int(time.time()*1000)}")
    caller_spiffe = request.headers.get(
        "x-caller-spiffe-id",
        "spiffe://cluster.local/ns/camp-travel/sa/weather-agent",
    )
    obo_user = request.headers.get("x-obo-user-id", "traveler-101")

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "tools": [
                    {
                        "name": "get_weather_forecast",
                        "description": "Retrieve multi-day destination weather forecast and packing advisory.",
                        "inputSchema": {"type": "object", "properties": {"destination": {"type": "string"}, "days": {"type": "integer"}}},
                    }
                ]
            },
        }

    if method == "tools/call":
        args = params.get("arguments", {})
        res = _execute_weather_forecast(str(args.get("destination", "San Francisco")), int(args.get("days", 4)))
        await emit_weather_mcp_span(trace_id, caller_spiffe, obo_user, args, res)
        return {"jsonrpc": "2.0", "id": rpc_id, "result": res}

    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32600, "message": "Invalid MCP request"}}


@app.post("/mcp/weather/forecast")
async def get_weather_forecast(query: WeatherQuery, request: Request):
    res = _execute_weather_forecast(query.destination, query.days)
    await emit_weather_mcp_span(
        request.headers.get("x-trace-id", f"trace-{int(time.time()*1000)}"),
        request.headers.get("x-caller-spiffe-id", "spiffe://cluster.local/ns/camp-travel/sa/weather-agent"),
        request.headers.get("x-obo-user-id", "traveler-101"),
        {"destination": query.destination, "days": query.days},
        res,
    )
    return res


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "weather-mcp-server", "ai_role": "mcp-server"}
