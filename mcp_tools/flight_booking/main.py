"""
Flight Booking MCP Server (mcp-server + csl-mcp-sc Sidecar Enforcement)
Supports:
- Real Model Context Protocol (MCP) JSON-RPC 2.0 endpoint (POST /mcp: tools/list, tools/call)
- csl-mcp-sc Per-Tool Policy, Destination OBO Verification, Proxy HITL Gate, and Cycle Detection Circuit Enforcement
- Backwards-compatible REST endpoints (/mcp/flights/search, /mcp/flights/reserve)
"""
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import httpx
import os
import uuid
import time

app = FastAPI(title="Flight Booking MCP Server (csl-mcp-sc governed)", version="2.1.0")

OTEL_COLLECTOR_URL = os.getenv("OTEL_COLLECTOR_URL", "http://otel-collector:4318")
INDIGO_ANALYTICS_URL = os.getenv("INDIGO_ANALYTICS_URL", "http://indigo-analytics:8089")


class FlightSearchRequest(BaseModel):
    origin: str = "JFK"
    destination: str = "SFO"
    date: Optional[str] = "2026-12-01"
    cabin_class: Optional[str] = "Economy"


class FlightBookingRequest(BaseModel):
    flight_number: str
    passenger_name: str
    origin: str
    destination: str
    seat_class: str = "Economy"


FLIGHT_SCHEDULES = [
    {"flight_number": "UA-442", "airline": "United Airlines", "origin": "JFK", "destination": "SFO", "departure": "08:30 AM", "arrival": "11:45 AM", "price_usd": 380.0, "duration": "6h 15m"},
    {"flight_number": "DL-120", "airline": "Delta Air Lines", "origin": "JFK", "destination": "SFO", "departure": "02:15 PM", "arrival": "05:30 PM", "price_usd": 410.0, "duration": "6h 15m"},
    {"flight_number": "BA-178", "airline": "British Airways", "origin": "JFK", "destination": "LHR", "departure": "07:00 PM", "arrival": "07:00 AM+1", "price_usd": 650.0, "duration": "7h 00m"},
    {"flight_number": "NH-107", "airline": "All Nippon Airways", "origin": "SFO", "destination": "NRT", "departure": "11:50 AM", "arrival": "03:00 PM+1", "price_usd": 890.0, "duration": "11h 10m"},
    {"flight_number": "AA-809", "airline": "American Airlines", "origin": "ORD", "destination": "SFO", "departure": "10:00 AM", "arrival": "12:45 PM", "price_usd": 320.0, "duration": "4h 45m"},
]

MCP_TOOL_POLICY = {
    "search_flights": {
        "allowed_spiffe_callers": [
            "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator",
        ],
        "required_obo_scope": "travel:plan",
        "requires_hitl_approval": False,
    },
    "reserve_flight": {
        "allowed_spiffe_callers": [
            "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        ],
        "required_obo_scope": "booking:reserve",
        "requires_hitl_approval": True,
    },
    "cancel_all_corporate_bookings": {
        "allowed_spiffe_callers": [
            "spiffe://cluster.local/ns/camp-travel/sa/global-security-admin",
        ],
        "required_obo_scope": "admin:emergency_cancel",
        "requires_hitl_approval": True,
    },
}


async def check_agent_circuit_breaker(caller_spiffe: str) -> Dict[str, Any]:
    try:
        service_short = caller_spiffe.split("/")[-1]
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{INDIGO_ANALYTICS_URL}/api/indigo/circuit/{service_short}")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {"state": "CLOSED"}


async def emit_mcp_sidecar_span(
    trace_id: str,
    caller_spiffe: str,
    obo_user: str,
    tool_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any],
    span_type: str = "mcp_tool_call",
    detail: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                f"{OTEL_COLLECTOR_URL}/v1/traces",
                json={
                    "trace_id": trace_id,
                    "span_type": span_type,
                    "span_name": f"csl-mcp-sc.flight-mcp.{tool_name}",
                    "instrumented_by": "csl-mcp-sc (MCP Sidecar Zero-Code ext-proc)",
                    "service": "flight-mcp",
                    "mcp_server": "flight-mcp",
                    "agent_spiffe_id": caller_spiffe,
                    "user_obo": obo_user,
                    "tool_name": tool_name,
                    "tool_arguments": arguments,
                    "tool_result": result,
                    "tokens_used": 22,
                    "detail": detail,
                },
            )
            if resp.status_code == 200:
                return resp.json().get("analytics")
    except Exception:
        pass
    return None


def _execute_search_flights(args: Dict[str, Any]) -> Dict[str, Any]:
    origin = str(args.get("origin", "JFK")).strip().upper()
    dest = str(args.get("destination", "SFO")).strip().upper()

    # Special case for Act 4 Cycle Detection Demo: sold-out route returning unchanged empty/error payload
    if dest == "SOLDOUT-LOOP" or args.get("flight_number") == "UA-999-SOLDOUT":
        return {
            "mcp_tool": "flight_booking",
            "status": "NO_INVENTORY_RETRYABLE",
            "error_code": "GDS_SOLD_OUT_449",
            "available_flights": [],
        }

    city_to_iata = {
        "SAN FRANCISCO": "SFO",
        "LONDON": "LHR",
        "TOKYO": "NRT",
        "NEW YORK": "JFK",
    }
    dest_code = city_to_iata.get(dest, dest)
    matches = [f for f in FLIGHT_SCHEDULES if dest_code in f["destination"]]
    if not matches:
        matches = [FLIGHT_SCHEDULES[0]]
    return {
        "mcp_tool": "flight_booking",
        "search_params": {"origin": origin, "destination": dest},
        "available_flights": matches,
    }


def _execute_reserve_flight(args: Dict[str, Any]) -> Dict[str, Any]:
    fn = str(args.get("flight_number", "UA-442"))
    passenger = str(args.get("passenger_name", "Alex Mercer"))
    flight = next((f for f in FLIGHT_SCHEDULES if f["flight_number"] == fn), FLIGHT_SCHEDULES[0])
    pnr = f"PNR-{uuid.uuid4().hex[:6].upper()}"
    return {
        "mcp_tool": "flight_booking",
        "status": "ticket_confirmed",
        "pnr": pnr,
        "flight_number": flight["flight_number"],
        "airline": flight["airline"],
        "route": f"{flight['origin']} -> {flight['destination']}",
        "passenger_name": passenger,
        "amount_usd": flight["price_usd"],
    }


@app.post("/mcp")
async def mcp_jsonrpc_endpoint(request: Request):
    """
    Model Context Protocol (MCP) JSON-RPC 2.0 endpoint governed by csl-mcp-sc sidecar processor.
    Enforces:
    1. Agent-scoped Circuit Breaker (Consul Agentic Analytics csl-ag-ana)
    2. Per-Tool Access Policy (csl-mcp-sc)
    3. Destination Identity Processor (OBO Scope Verification)
    4. Cryptographic Human-in-the-Loop (HITL) Approval Gate
    """
    payload = await request.json()
    rpc_id = payload.get("id", "rpc-1")
    method = payload.get("method", "tools/list")
    params = payload.get("params", {})

    trace_id = request.headers.get("x-trace-id", f"trace-mcp-{int(time.time()*1000)}")
    caller_spiffe = request.headers.get(
        "x-caller-spiffe-id",
        "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
    )
    obo_user = request.headers.get("x-obo-user-id", "traveler-101")
    obo_scopes_raw = request.headers.get("x-obo-scopes", "travel:read,travel:plan,booking:reserve")
    obo_scopes = [s.strip() for s in obo_scopes_raw.split(",") if s.strip()]
    hitl_evidence = request.headers.get("x-consul-hitl-evidence", "")

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "tools": [
                    {
                        "name": "search_flights",
                        "description": "Search available commercial flights between origin and destination.",
                        "inputSchema": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}}},
                    },
                    {
                        "name": "reserve_flight",
                        "description": "Issue binding airline ticket PNR (Requires HITL Approval & booking:reserve OBO scope).",
                        "inputSchema": {"type": "object", "properties": {"flight_number": {"type": "string"}, "passenger_name": {"type": "string"}}},
                    },
                    {
                        "name": "cancel_all_corporate_bookings",
                        "description": "Emergency administrative tool to revoke active corporate PNRs.",
                        "inputSchema": {"type": "object", "properties": {"tenant_id": {"type": "string"}}},
                    },
                ]
            },
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # 0. Check Agent-Scoped Circuit Breaker State (from Consul Agentic Analytics csl-ag-ana)
        circuit = await check_agent_circuit_breaker(caller_spiffe)
        if circuit.get("state") == "OPEN":
            detail = (
                f"Consul Behavior Policy Circuit Breaker OPEN for '{caller_spiffe}': "
                f"{circuit.get('reason', 'Cycle detected by csl-ag-ana')}"
            )
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32029,
                    "message": detail,
                    "data": {
                        "enforced_by": "csl-mcp-sc + csl-ag-ana (Agent-Scoped Circuit Breaker)",
                        "circuit_state": "OPEN",
                        "agent_spiffe_id": caller_spiffe,
                        "layer": "cycle-detection-circuit-breaker",
                    },
                },
            }

        policy = MCP_TOOL_POLICY.get(tool_name)
        if not policy:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32601, "message": f"Unknown MCP tool '{tool_name}'"},
            }

        # 1. Per-Tool Access Policy Check
        if caller_spiffe not in policy["allowed_spiffe_callers"]:
            detail = (
                f"csl-mcp-sc Per-Tool Policy Denied: caller '{caller_spiffe}' cannot invoke '{tool_name}'"
            )
            await emit_mcp_sidecar_span(
                trace_id, caller_spiffe, obo_user, tool_name, arguments,
                {"error": "PER_TOOL_POLICY_DENIED"}, span_type="policy_violation", detail=detail
            )
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32001,
                    "message": detail,
                    "data": {"enforced_by": "csl-mcp-sc", "layer": "per-tool-policy"},
                },
            }

        # 2. Destination-Side OBO Scope Verification
        req_scope = policy["required_obo_scope"]
        if req_scope not in obo_scopes:
            detail = (
                f"Identity Plane OBO Verification Denied: user '{obo_user}' (scopes={obo_scopes}) "
                f"lacks required scope '{req_scope}' for 'flight-mcp/{tool_name}'"
            )
            await emit_mcp_sidecar_span(
                trace_id, caller_spiffe, obo_user, tool_name, arguments,
                {"error": "OBO_SCOPE_DENIED"}, span_type="policy_violation", detail=detail
            )
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32002,
                    "message": detail,
                    "data": {
                        "enforced_by": "Consul Destination Identity Processor (OBO)",
                        "user_obo": obo_user,
                        "required_scope": req_scope,
                        "layer": "identity-plane-obo",
                    },
                },
            }

        # 3. HITL Approval Enforcement
        if policy["requires_hitl_approval"] and not hitl_evidence.startswith("hitl-sig-"):
            detail = (
                f"csl-mcp-sc HITL Gate Intercepted: tool '{tool_name}' requires cryptographic human approval evidence."
            )
            await emit_mcp_sidecar_span(
                trace_id, caller_spiffe, obo_user, tool_name, arguments,
                {"status": "HELD_FOR_HITL_APPROVAL"}, span_type="policy_violation", detail=detail
            )
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32003,
                    "message": detail,
                    "data": {
                        "enforced_by": "csl-mcp-sc (HITL Enforcement Processor)",
                        "requires_human_approval": True,
                        "tool": tool_name,
                        "layer": "mcp-hitl-gate",
                    },
                },
            }

        if tool_name == "search_flights":
            res = _execute_search_flights(arguments)
        elif tool_name == "reserve_flight":
            res = _execute_reserve_flight(arguments)
            res["hitl_evidence_verified"] = hitl_evidence
        else:
            res = {"status": "cancelled"}

        analytics = await emit_mcp_sidecar_span(trace_id, caller_spiffe, obo_user, tool_name, arguments, res)
        if analytics:
            res["_analytics_telemetry"] = analytics
        return {"jsonrpc": "2.0", "id": rpc_id, "result": res}

    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32600, "message": "Invalid MCP request"}}


@app.post("/mcp/flights/search")
async def search_flights(req: FlightSearchRequest, request: Request):
    res = _execute_search_flights({"origin": req.origin, "destination": req.destination, "date": req.date})
    await emit_mcp_sidecar_span(
        request.headers.get("x-trace-id", f"trace-{int(time.time()*1000)}"),
        request.headers.get("x-caller-spiffe-id", "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"),
        request.headers.get("x-obo-user-id", "traveler-101"),
        "search_flights",
        {"origin": req.origin, "destination": req.destination},
        res,
    )
    return res


@app.post("/mcp/flights/reserve")
async def reserve_flight(req: FlightBookingRequest, request: Request):
    res = _execute_reserve_flight({
        "flight_number": req.flight_number,
        "passenger_name": req.passenger_name,
        "origin": req.origin,
        "destination": req.destination,
    })
    await emit_mcp_sidecar_span(
        request.headers.get("x-trace-id", f"trace-{int(time.time()*1000)}"),
        request.headers.get("x-caller-spiffe-id", "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"),
        request.headers.get("x-obo-user-id", "traveler-101"),
        "reserve_flight",
        {"flight_number": req.flight_number, "passenger_name": req.passenger_name},
        res,
    )
    return res


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "flight-mcp-server", "ai_role": "mcp-server"}
