"""
Booking Agent (ai-agent workload + csl-mcp-sc Sidecar)
Coordinates Hotel MCP, Flight MCP, and External Partner MCP tools across the Consul Agentic Runtime Fabric
using Model Context Protocol (JSON-RPC 2.0).
Supports interactive governance demonstrations:
- Per-tool policy enforcement (csl-mcp-sc)
- Proxy-enforced Human-in-the-Loop (HITL) cryptographic evidence verification
- Hop-by-hop On-Behalf-Of (OBO) scope enforcement
- Runaway tool-call loop triggering Agentic Analytics (csl-ag-ana) cycle detection & circuit breaking
"""
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import httpx
import os
import time

app = FastAPI(title="CAMP Booking Agent (ai-agent)", version="2.1.0")

HOTEL_MCP_URL = os.getenv("HOTEL_MCP_URL", "http://hotel-mcp:8083")
FLIGHT_MCP_URL = os.getenv("FLIGHT_MCP_URL", "http://flight-mcp:8084")
TERMINATING_GW_URL = os.getenv("TERMINATING_GW_URL", "http://terminating-gw:10002")
AGENT_SPIFFE_ID = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"


class BookingPlanRequest(BaseModel):
    origin: str = "JFK"
    destination: str = "SFO"
    traveler_name: str = "Alex Mercer"
    nights: int = 4
    budget_usd: float = 2500.0
    needs_ground_transport: bool = True
    scenario_mode: str = "normal"


@app.post("/agent/booking/plan")
async def plan_bookings(req: BookingPlanRequest, request: Request):
    trace_id = request.headers.get("x-trace-id", f"trace-booking-{int(time.time()*1000)}")
    obo_user = request.headers.get("x-obo-user-id", "traveler-101")
    obo_scopes = request.headers.get(
        "x-obo-scopes",
        "travel:read,travel:plan,booking:reserve,partner:gds_egress",
    )

    mcp_headers = {
        "x-trace-id": trace_id,
        "x-caller-spiffe-id": AGENT_SPIFFE_ID,
        "x-obo-user-id": obo_user,
        "x-obo-scopes": obo_scopes,
        "x-consul-obo-token": f"obo-hop2-booking-{obo_user}",
    }

    governance_interceptions: List[Dict[str, Any]] = []
    loop_iterations: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=12.0) as client:
        # Scenario Act 4: Runaway Agent Retry Loop -> Cycle Detection & Agent-Scoped Circuit Breaker
        if req.scenario_mode == "act4_cycle_loop":
            for attempt in range(1, 5):
                loop_resp = await client.post(
                    f"{FLIGHT_MCP_URL}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": f"rpc-loop-{attempt}",
                        "method": "tools/call",
                        "params": {
                            "name": "search_flights",
                            "arguments": {"origin": req.origin, "destination": "SOLDOUT-LOOP", "flight_number": "UA-999-SOLDOUT"},
                        },
                    },
                    headers=mcp_headers,
                )
                rpc_json = loop_resp.json()
                if "error" in rpc_json:
                    err = rpc_json["error"]
                    loop_iterations.append({
                        "attempt": attempt,
                        "tool": "flight-mcp/search_flights",
                        "arguments": {"origin": req.origin, "destination": "SOLDOUT-LOOP"},
                        "outcome": "CIRCUIT_OPEN_REJECTED",
                        "circuit_state": "OPEN",
                        "message": err.get("message"),
                    })
                    governance_interceptions.append({
                        "layer": "Cycle Detection & Agent Circuit Breaker (csl-ag-ana + csl-mcp-sc)",
                        "status": "AGENT_CIRCUIT_OPEN",
                        "code": err.get("code"),
                        "message": err.get("message"),
                    })
                    break
                else:
                    res_data = rpc_json.get("result", {})
                    ana = res_data.get("_analytics_telemetry", {}) or {}
                    loop_iterations.append({
                        "attempt": attempt,
                        "tool": "flight-mcp/search_flights",
                        "arguments": {"origin": req.origin, "destination": "SOLDOUT-LOOP"},
                        "outcome": res_data.get("status", "NO_INVENTORY_RETRYABLE"),
                        "repetition_count": ana.get("repetition_count", attempt),
                        "circuit_state": ana.get("circuit_state", "OPEN" if attempt >= 3 else "CLOSED"),
                        "fingerprint": ana.get("fingerprint", "f9a1c3"),
                    })

        # Scenario Act 2a: Unauthorized Per-Tool Invocation (Discovery != Execution Permission)
        if req.scenario_mode == "act2_unauthorized_tool":
            unauth_resp = await client.post(
                f"{HOTEL_MCP_URL}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": "rpc-unauth-tool",
                    "method": "tools/call",
                    "params": {
                        "name": "override_hotel_rate",
                        "arguments": {"hotel_id": "HTL-SF-01", "new_rate_usd": 49.0},
                    },
                },
                headers=mcp_headers,
            )
            unauth_json = unauth_resp.json()
            if "error" in unauth_json:
                governance_interceptions.append({
                    "layer": "MCP Sidecar Per-Tool Policy (csl-mcp-sc)",
                    "status": "DENIED_AT_SIDECAR",
                    "tool": "hotel-mcp/override_hotel_rate",
                    "code": unauth_json["error"].get("code"),
                    "message": unauth_json["error"].get("message"),
                })

        # Scenario Act 2b / Act 3: Unapproved State Mutation or Contractor Scope Violation on reserve_flight
        if req.scenario_mode in ("act2_unapproved_mutation", "act3_contractor_obo"):
            mut_resp = await client.post(
                f"{FLIGHT_MCP_URL}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": "rpc-direct-reserve",
                    "method": "tools/call",
                    "params": {
                        "name": "reserve_flight",
                        "arguments": {
                            "flight_number": "UA-442",
                            "passenger_name": req.traveler_name,
                            "origin": req.origin,
                            "destination": req.destination,
                        },
                    },
                },
                headers=mcp_headers,  # Note: No x-consul-hitl-evidence header or contractor scopes
            )
            mut_json = mut_resp.json()
            if "error" in mut_json:
                governance_interceptions.append({
                    "layer": mut_json["error"].get("data", {}).get("enforced_by", "csl-mcp-sc"),
                    "status": "INTERCEPTED",
                    "tool": "flight-mcp/reserve_flight",
                    "code": mut_json["error"].get("code"),
                    "message": mut_json["error"].get("message"),
                })

        # 1. Search Flights via MCP JSON-RPC 2.0
        flight_resp = await client.post(
            f"{FLIGHT_MCP_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "rpc-flight-search",
                "method": "tools/call",
                "params": {
                    "name": "search_flights",
                    "arguments": {"origin": req.origin, "destination": req.destination},
                },
            },
            headers=mcp_headers,
        )
        flight_rpc = flight_resp.json()
        if "error" in flight_rpc:
            flights = []
            governance_interceptions.append({
                "layer": "Flight MCP Sidecar (csl-mcp-sc)",
                "status": "BLOCKED",
                "tool": "flight-mcp/search_flights",
                "code": flight_rpc["error"].get("code"),
                "message": flight_rpc["error"].get("message"),
            })
        else:
            flights = flight_rpc.get("result", {}).get("available_flights", [])
        selected_flight = flights[0] if flights else {}

        # 2. Search Hotels via MCP JSON-RPC 2.0
        hotel_resp = await client.post(
            f"{HOTEL_MCP_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "rpc-hotel-search",
                "method": "tools/call",
                "params": {
                    "name": "search_hotels",
                    "arguments": {
                        "destination": req.destination,
                        "max_budget_per_night": req.budget_usd / (req.nights + 1),
                    },
                },
            },
            headers=mcp_headers,
        )
        hotel_rpc = hotel_resp.json()
        hotels = hotel_rpc.get("result", {}).get("available_hotels", [])
        selected_hotel = hotels[0] if hotels else {}

        # 3. Query External Ground Transport via Terminating Gateway
        ground_transport = None
        if req.needs_ground_transport:
            try:
                car_resp = await client.post(
                    f"{TERMINATING_GW_URL}/external/mcp/ground-transport",
                    json={"destination": req.destination, "rental_days": req.nights},
                    headers=mcp_headers,
                )
                if car_resp.status_code >= 400:
                    err_detail = car_resp.json().get("detail", "Blocked at Terminating Gateway")
                    ground_transport = {"status": "blocked_by_obo_policy", "detail": err_detail}
                    governance_interceptions.append({
                        "layer": "Terminating Gateway & Identity Plane OBO",
                        "status": "DENIED_EGRESS",
                        "tool": "external-mcp/ground-transport",
                        "code": car_resp.status_code,
                        "message": err_detail,
                    })
                else:
                    ground_transport = car_resp.json()
            except Exception as e:
                ground_transport = {"status": "unavailable", "detail": str(e)}

    flight_cost = selected_flight.get("price_usd", 0.0)
    hotel_cost = selected_hotel.get("price_per_night", 0.0) * req.nights
    car_cost = (
        ground_transport.get("total_amount_usd", 0.0)
        if ground_transport and "total_amount_usd" in ground_transport
        else 0.0
    )
    total_estimated = flight_cost + hotel_cost + car_cost

    return {
        "agent": "booking-agent",
        "spiffe_id": AGENT_SPIFFE_ID,
        "traveler": req.traveler_name,
        "origin": req.origin,
        "destination": req.destination,
        "nights": req.nights,
        "selected_flight": selected_flight,
        "selected_hotel": selected_hotel,
        "ground_transport": ground_transport,
        "total_estimated_usd": round(total_estimated, 2),
        "within_budget": total_estimated <= req.budget_usd,
        "governance_interceptions": governance_interceptions,
        "loop_iterations": loop_iterations,
        "obo_delegation_hop": {
            "caller": "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator",
            "actor": AGENT_SPIFFE_ID,
            "audiences": [
                "spiffe://cluster.local/ns/camp-travel/sa/flight-mcp",
                "spiffe://cluster.local/ns/camp-travel/sa/hotel-mcp",
                "spiffe://cluster.local/ns/camp-travel/sa/terminating-gw",
            ],
            "subject": obo_user,
            "narrowed_scopes": [s.strip() for s in obo_scopes.split(",") if s.strip()],
        },
    }


@app.post("/agent/booking/confirm")
async def confirm_bookings(req: Dict[str, Any], request: Request):
    """
    Executes final binding reservations via MCP JSON-RPC tools/call.
    csl-mcp-sc verifies the cryptographic x-consul-hitl-evidence header bound to the human approval!
    """
    trace_id = request.headers.get("x-trace-id", f"trace-confirm-{int(time.time()*1000)}")
    obo_user = request.headers.get("x-obo-user-id", req.get("obo_user", "traveler-101"))
    obo_scopes = request.headers.get("x-obo-scopes", req.get("obo_scopes", "travel:read,travel:plan,booking:reserve"))
    hitl_evidence = request.headers.get("x-consul-hitl-evidence", req.get("hitl_evidence_token", f"hitl-sig-{int(time.time())}"))

    traveler = req.get("traveler_name", "Alex Mercer")
    nights = req.get("nights", 4)
    flight = req.get("flight", {}) or {}
    hotel = req.get("hotel", {}) or {}

    mcp_headers = {
        "x-trace-id": trace_id,
        "x-caller-spiffe-id": AGENT_SPIFFE_ID,
        "x-obo-user-id": obo_user,
        "x-obo-scopes": obo_scopes,
        "x-consul-hitl-evidence": hitl_evidence,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Confirm Flight via MCP JSON-RPC 2.0 (with HITL evidence header)
        f_resp = await client.post(
            f"{FLIGHT_MCP_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "rpc-confirm-flight",
                "method": "tools/call",
                "params": {
                    "name": "reserve_flight",
                    "arguments": {
                        "flight_number": flight.get("flight_number", "UA-442"),
                        "passenger_name": traveler,
                        "origin": flight.get("origin", "JFK"),
                        "destination": flight.get("destination", "SFO"),
                    },
                },
            },
            headers=mcp_headers,
        )
        f_rpc = f_resp.json()
        if "error" in f_rpc:
            return {
                "status": "blocked_by_mcp_sidecar",
                "error": f_rpc["error"],
            }
        flight_confirmation = f_rpc.get("result", {})

        # 2. Confirm Hotel via MCP JSON-RPC 2.0 (with HITL evidence header)
        h_resp = await client.post(
            f"{HOTEL_MCP_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "rpc-confirm-hotel",
                "method": "tools/call",
                "params": {
                    "name": "reserve_hotel",
                    "arguments": {
                        "hotel_id": hotel.get("id", "HTL-SF-01"),
                        "guest_name": traveler,
                        "nights": nights,
                    },
                },
            },
            headers=mcp_headers,
        )
        h_rpc = h_resp.json()
        if "error" in h_rpc:
            return {
                "status": "blocked_by_mcp_sidecar",
                "error": h_rpc["error"],
            }
        hotel_confirmation = h_rpc.get("result", {})

    return {
        "status": "all_reservations_confirmed",
        "hitl_evidence_token": hitl_evidence,
        "flight_booking": flight_confirmation,
        "hotel_booking": hotel_confirmation,
        "ground_transport": req.get("ground_transport"),
    }


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "booking-agent", "ai_role": "ai-agent"}
