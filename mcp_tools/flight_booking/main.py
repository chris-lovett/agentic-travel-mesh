"""
Flight Booking MCP Server (MCP + Envoy Sidecar)
Provides flight route search, schedule lookup, and reservation issuance.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid

app = FastAPI(title="Flight Booking MCP Server", version="1.0.0")

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
    {"flight_number": "AA-809", "airline": "American Airlines", "origin": "ORD", "destination": "SFO", "departure": "10:00 AM", "arrival": "12:45 PM", "price_usd": 320.0, "duration": "4h 45m"},
]

@app.post("/mcp/flights/search")
async def search_flights(req: FlightSearchRequest):
    orig = req.origin.strip().upper()
    dest = req.destination.strip().upper()
    matches = [f for f in FLIGHT_SCHEDULES if (dest in f["destination"] or "SFO" in f["destination"])]
    if not matches:
        matches = [FLIGHT_SCHEDULES[0]]

    return {
        "mcp_tool": "flight_booking",
        "search_params": {"origin": req.origin, "destination": req.destination, "date": req.date},
        "available_flights": matches,
    }

@app.post("/mcp/flights/reserve")
async def reserve_flight(req: FlightBookingRequest):
    flight = next((f for f in FLIGHT_SCHEDULES if f["flight_number"] == req.flight_number), FLIGHT_SCHEDULES[0])
    pnr = f"PNR-{uuid.uuid4().hex[:6].upper()}"

    return {
        "mcp_tool": "flight_booking",
        "status": "ticket_confirmed",
        "pnr": pnr,
        "flight_number": flight["flight_number"],
        "airline": flight["airline"],
        "route": f"{flight['origin']} -> {flight['destination']}",
        "passenger_name": req.passenger_name,
        "amount_usd": flight["price_usd"],
    }

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "flight-mcp-server"}
