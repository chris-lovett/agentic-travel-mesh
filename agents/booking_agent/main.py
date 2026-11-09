"""
Booking Agent (Agent + Envoy Sidecars)
Coordinates Hotel MCP, Flight MCP, and External Partner MCP tools across the Consul Mesh.
"""
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import httpx
import os

app = FastAPI(title="CAMP Booking Agent", version="1.0.0")

HOTEL_MCP_URL = os.getenv("HOTEL_MCP_URL", "http://hotel-mcp:8083")
FLIGHT_MCP_URL = os.getenv("FLIGHT_MCP_URL", "http://flight-mcp:8084")
TERMINATING_GW_URL = os.getenv("TERMINATING_GW_URL", "http://terminating-gw:10002")

class BookingPlanRequest(BaseModel):
    origin: str = "JFK"
    destination: str = "SFO"
    traveler_name: str = "Alex Mercer"
    nights: int = 4
    budget_usd: float = 2500.0
    needs_ground_transport: bool = True

@app.post("/agent/booking/plan")
async def plan_bookings(req: BookingPlanRequest, request: Request):
    obo_user = request.headers.get("x-obo-user-id", "traveler-101")
    headers = {"x-obo-user-id": obo_user}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Search Flights
        flight_resp = await client.post(
            f"{FLIGHT_MCP_URL}/mcp/flights/search",
            json={"origin": req.origin, "destination": req.destination},
            headers=headers,
        )
        flights = flight_resp.json().get("available_flights", [])
        selected_flight = flights[0] if flights else {}

        # 2. Search Hotels
        hotel_resp = await client.post(
            f"{HOTEL_MCP_URL}/mcp/hotels/search",
            json={"destination": req.destination, "max_budget_per_night": req.budget_usd / (req.nights + 1)},
            headers=headers,
        )
        hotels = hotel_resp.json().get("available_hotels", [])
        selected_hotel = hotels[0] if hotels else {}

        # 3. Query External Ground Transport via Terminating Gateway
        ground_transport = None
        if req.needs_ground_transport:
            try:
                car_resp = await client.post(
                    f"{TERMINATING_GW_URL}/external/mcp/ground-transport",
                    json={"destination": req.destination, "rental_days": req.nights},
                    headers=headers,
                )
                ground_transport = car_resp.json()
            except Exception as e:
                ground_transport = {"status": "unavailable", "detail": str(e)}

    # Calculate Total Estimates
    flight_cost = selected_flight.get("price_usd", 0.0)
    hotel_cost = selected_hotel.get("price_per_night", 0.0) * req.nights
    car_cost = ground_transport.get("total_amount_usd", 0.0) if ground_transport and "total_amount_usd" in ground_transport else 0.0
    total_estimated = flight_cost + hotel_cost + car_cost

    return {
        "agent": "booking-agent",
        "traveler": req.traveler_name,
        "origin": req.origin,
        "destination": req.destination,
        "nights": req.nights,
        "selected_flight": selected_flight,
        "selected_hotel": selected_hotel,
        "ground_transport": ground_transport,
        "total_estimated_usd": round(total_estimated, 2),
        "within_budget": total_estimated <= req.budget_usd,
    }

@app.post("/agent/booking/confirm")
async def confirm_bookings(req: Dict[str, Any], request: Request):
    """Execute final booking reservations upon Human-in-the-Loop (HITL) approval"""
    obo_user = request.headers.get("x-obo-user-id", "traveler-101")
    traveler = req.get("traveler_name", "Alex Mercer")
    nights = req.get("nights", 4)
    flight = req.get("flight", {})
    hotel = req.get("hotel", {})

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Confirm Flight
        f_resp = await client.post(
            f"{FLIGHT_MCP_URL}/mcp/flights/reserve",
            json={
                "flight_number": flight.get("flight_number", "UA-442"),
                "passenger_name": traveler,
                "origin": flight.get("origin", "JFK"),
                "destination": flight.get("destination", "SFO"),
            },
        )
        flight_confirmation = f_resp.json()

        # Confirm Hotel
        h_resp = await client.post(
            f"{HOTEL_MCP_URL}/mcp/hotels/reserve",
            json={
                "hotel_id": hotel.get("id", "HTL-SF-01"),
                "guest_name": traveler,
                "nights": nights,
            },
        )
        hotel_confirmation = h_resp.json()

    return {
        "status": "all_reservations_confirmed",
        "flight_booking": flight_confirmation,
        "hotel_booking": hotel_confirmation,
        "ground_transport": req.get("ground_transport"),
    }

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "booking-agent"}
