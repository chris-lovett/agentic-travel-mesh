"""
Hotel Booking MCP Server (MCP + Envoy Sidecar)
Provides hotel search, availability filtering, and reservation management.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid

app = FastAPI(title="Hotel Booking MCP Server", version="1.0.0")

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

@app.post("/mcp/hotels/search")
async def search_hotels(req: HotelSearchRequest):
    dest = req.destination.strip().lower()
    matches = [h for h in HOTEL_CATALOG if dest in h["city"].lower() and h["price_per_night"] <= req.max_budget_per_night]
    if not matches:
        matches = [HOTEL_CATALOG[-1]] # Fallback general hotel

    return {
        "mcp_tool": "hotel_booking",
        "destination": req.destination,
        "available_hotels": matches,
    }

@app.post("/mcp/hotels/reserve")
async def reserve_hotel(req: HotelBookingRequest):
    hotel = next((h for h in HOTEL_CATALOG if h["id"] == req.hotel_id), HOTEL_CATALOG[0])
    total_cost = hotel["price_per_night"] * req.nights
    booking_ref = f"HTL-CONF-{uuid.uuid4().hex[:8].upper()}"

    return {
        "mcp_tool": "hotel_booking",
        "status": "confirmed",
        "booking_reference": booking_ref,
        "hotel_name": hotel["name"],
        "city": hotel["city"],
        "nights": req.nights,
        "total_amount_usd": total_cost,
        "guest_name": req.guest_name,
    }

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "hotel-mcp-server"}
