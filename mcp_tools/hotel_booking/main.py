"""
Hotel Booking MCP Server (mcp-server + csl-mcp-sc Sidecar Enforcement)
Supports:
- Real Model Context Protocol (MCP) JSON-RPC 2.0 endpoint (POST /mcp: tools/list, tools/call)
- csl-mcp-sc Per-Tool Policy Enforcement, Destination-Side OBO Verification, Proxy HITL Gate, and Zero-Code OTel Spans
- Backwards-compatible REST endpoints (/mcp/hotels/search, /mcp/hotels/reserve)
"""
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import httpx
import os
import uuid
import time

app = FastAPI(title="Hotel Booking MCP Server (csl-mcp-sc governed)", version="2.1.0")

OTEL_COLLECTOR_URL = os.getenv("OTEL_COLLECTOR_URL", "http://otel-collector:4318")
INDIGO_ANALYTICS_URL = os.getenv("INDIGO_ANALYTICS_URL", "http://indigo-analytics:8089")


class HotelSearchRequest(BaseModel):
    destination: str
    check_in: Optional[str] = "2026-12-01"
    check_out: Optional[str] = "2026-12-05"
    max_budget_per_night: Optional[float] = 400.0


class HotelBookingRequest(BaseModel):
    hotel_id: str
    guest_name: str
    nights: int = 4
    room_type: str = "Deluxe King"


HOTEL_CATALOG = [
    {"id": "HTL-SF-01", "name": "The Westin St. Francis", "city": "San Francisco", "price_per_night": 289.0, "rating": 4.6, "amenities": ["WiFi", "Fitness Center", "Conference Center"]},
    {"id": "HTL-SF-02", "name": "Palace Hotel San Francisco", "city": "San Francisco", "price_per_night": 349.0, "rating": 4.8, "amenities": ["Indoor Pool", "Fine Dining", "Historic Lobby"]},
    {"id": "HTL-NY-01", "name": "The Langham Fifth Avenue", "city": "New York", "price_per_night": 450.0, "rating": 4.9, "amenities": ["Spa", "Michelin Dining", "Central Park Views"]},
    {"id": "HTL-LON-01", "name": "The Savoy London", "city": "London", "price_per_night": 395.0, "rating": 4.8, "amenities": ["River Thames View", "Butler Service", "Afternoon Tea"]},
    {"id": "HTL-GEN-01", "name": "Grand Hyatt Central", "city": "General", "price_per_night": 220.0, "rating": 4.5, "amenities": ["Breakfast Included", "High-speed WiFi", "Business Lounge"]},
]

# Per-Tool Access Policy enforced by csl-mcp-sc (Discovery != Execution Permission)
MCP_TOOL_POLICY = {
    "search_hotels": {
        "allowed_spiffe_Callers": [
            "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator",
        ],
        "required_obo_scope": "travel:plan",
        "requires_hitl_approval": False,
    },
    "reserve_hotel": {
        "allowed_spiffe_Callers": [
            "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        ],
        "required_obo_scope": "booking:reserve",
        "requires_hitl_approval": True,
    },
    "override_hotel_rate": {
        "allowed_spiffe_Callers": [
            "spiffe://cluster.local/ns/camp-travel/sa/finance-admin-agent",
        ],
        "required_obo_scope": "admin:rate_override",
        "requires_hitl_approval": True,
    },
}


async def emit_mcp_sidecar_span(
    trace_id: str,
    caller_spiffe: str,
    obo_user: str,
    tool_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any],
    span_type: str = "mcp_tool_call",
    detail: Optional[str] = None,
):
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            await client.post(
                f"{OTEL_COLLECTOR_URL}/v1/traces",
                json={
                    "trace_id": trace_id,
                    "span_type": span_type,
                    "span_name": f"csl-mcp-sc.hotel-mcp.{tool_name}",
                    "instrumented_by": "csl-mcp-sc (MCP Sidecar Zero-Code ext-proc)",
                    "service": "hotel-mcp",
                    "mcp_server": "hotel-mcp",
                    "agent_spiffe_id": caller_spiffe,
                    "user_obo": obo_user,
                    "tool_name": tool_name,
                    "tool_arguments": arguments,
                    "tool_result": result,
                    "tokens_used": 18,
                    "detail": detail,
                },
            )
    except Exception:
        pass


def _execute_search_hotels(args: Dict[str, Any]) -> Dict[str, Any]:
    destination = str(args.get("destination", "San Francisco"))
    max_budget = float(args.get("max_budget_per_night", 400.0))
    dest = destination.strip().lower()
    matches = [h for h in HOTEL_CATALOG if dest in h["city"].lower() and h["price_per_night"] <= max_budget]
    if not matches:
        matches = [HOTEL_CATALOG[-1]]
    return {
        "mcp_tool": "hotel_booking",
        "destination": destination,
        "available_hotels": matches,
    }


def _execute_reserve_hotel(args: Dict[str, Any]) -> Dict[str, Any]:
    hotel_id = str(args.get("hotel_id", "HTL-SF-01"))
    guest_name = str(args.get("guest_name", "Alex Mercer"))
    nights = int(args.get("nights", 4))
    hotel = next((h for h in HOTEL_CATALOG if h["id"] == hotel_id), HOTEL_CATALOG[0])
    total_cost = hotel["price_per_night"] * nights
    booking_ref = f"HTL-CONF-{uuid.uuid4().hex[:8].upper()}"
    return {
        "mcp_tool": "hotel_booking",
        "status": "confirmed",
        "booking_reference": booking_ref,
        "hotel_name": hotel["name"],
        "city": hotel["city"],
        "nights": nights,
        "total_amount_usd": total_cost,
        "guest_name": guest_name,
    }


@app.post("/mcp")
async def mcp_jsonrpc_endpoint(request: Request):
    """
    Model Context Protocol (MCP) JSON-RPC 2.0 endpoint governed by csl-mcp-sc sidecar processor.
    Separates catalog visibility (tools/list) from per-tool policy, OBO authority, and HITL approval (tools/call).
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
                        "name": "search_hotels",
                        "description": "Search corporate-compliant hotels by destination and nightly budget.",
                        "inputSchema": {"type": "object", "properties": {"destination": {"type": "string"}, "max_budget_per_night": {"type": "number"}}},
                    },
                    {
                        "name": "reserve_hotel",
                        "description": "Issue binding hotel reservation (Requires HITL Approval & booking:reserve OBO scope).",
                        "inputSchema": {"type": "object", "properties": {"hotel_id": {"type": "string"}, "guest_name": {"type": "string"}, "nights": {"type": "integer"}}},
                    },
                    {
                        "name": "override_hotel_rate",
                        "description": "Privileged finance tool to override negotiated corporate hotel rate caps.",
                        "inputSchema": {"type": "object", "properties": {"hotel_id": {"type": "string"}, "new_rate_usd": {"type": "number"}}},
                    },
                ]
            },
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        policy = MCP_TOOL_POLICY.get(tool_name)

        if not policy:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32601, "message": f"Unknown MCP tool '{tool_name}'"},
            }

        # 1. csl-mcp-sc Per-Tool Access Policy Check (Workload SPIFFE ID)
        if caller_spiffe not in policy["allowed_spiffe_Callers"]:
            detail = (
                f"csl-mcp-sc Per-Tool Policy Denied: workload '{caller_spiffe}' discovered tool '{tool_name}' "
                f"in catalog, but policy forbids invocation (allowed: {policy['allowed_spiffe_Callers']})"
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
                    "data": {
                        "enforced_by": "csl-mcp-sc (Consul MCP Sidecar ext-proc)",
                        "caller_spiffe_id": caller_spiffe,
                        "tool": tool_name,
                        "layer": "per-tool-policy",
                    },
                },
            }

        # 2. Destination-Side Identity Processor (OBO Delegated User Scope Check)
        req_scope = policy["required_obo_scope"]
        if req_scope not in obo_scopes:
            detail = (
                f"Identity Plane OBO Verification Denied: delegated token for user '{obo_user}' "
                f"(scopes={obo_scopes}) lacks required scope '{req_scope}' at destination 'hotel-mcp/{tool_name}'"
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
                        "user_scopes": obo_scopes,
                        "required_scope": req_scope,
                        "layer": "identity-plane-obo",
                    },
                },
            }

        # 3. csl-mcp-sc Human-in-the-Loop (HITL) Approval Enforcement
        if policy["requires_hitl_approval"] and not hitl_evidence.startswith("hitl-sig-"):
            detail = (
                f"csl-mcp-sc HITL Gate Intercepted: tool '{tool_name}' is marked require_human_approval=true. "
                f"Missing cryptographic approval evidence bound to this action."
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

        # Execute underlying MCP tool business logic
        if tool_name == "search_hotels":
            res = _execute_search_hotels(arguments)
        elif tool_name == "reserve_hotel":
            res = _execute_reserve_hotel(arguments)
            res["hitl_evidence_verified"] = hitl_evidence
        else:
            res = {"status": "rate_overridden"}

        await emit_mcp_sidecar_span(trace_id, caller_spiffe, obo_user, tool_name, arguments, res)
        return {"jsonrpc": "2.0", "id": rpc_id, "result": res}

    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32600, "message": "Invalid MCP request"}}


@app.post("/mcp/hotels/search")
async def search_hotels(req: HotelSearchRequest, request: Request):
    res = _execute_search_hotels({"destination": req.destination, "max_budget_per_night": req.max_budget_per_night})
    await emit_mcp_sidecar_span(
        request.headers.get("x-trace-id", f"trace-{int(time.time()*1000)}"),
        request.headers.get("x-caller-spiffe-id", "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"),
        request.headers.get("x-obo-user-id", "traveler-101"),
        "search_hotels",
        {"destination": req.destination, "max_budget_per_night": req.max_budget_per_night},
        res,
    )
    return res


@app.post("/mcp/hotels/reserve")
async def reserve_hotel(req: HotelBookingRequest, request: Request):
    res = _execute_reserve_hotel({"hotel_id": req.hotel_id, "guest_name": req.guest_name, "nights": req.nights})
    await emit_mcp_sidecar_span(
        request.headers.get("x-trace-id", f"trace-{int(time.time()*1000)}"),
        request.headers.get("x-caller-spiffe-id", "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"),
        request.headers.get("x-obo-user-id", "traveler-101"),
        "reserve_hotel",
        {"hotel_id": req.hotel_id, "guest_name": req.guest_name, "nights": req.nights},
        res,
    )
    return res


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "hotel-mcp-server", "ai_role": "mcp-server"}
