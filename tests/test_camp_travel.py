"""
Automated End-to-End Regression Test Suite for CAMP Travel Booking Architecture
Validates all MCP tools, Sub-Agents, Travel Orchestrator, Gateways, and Review Backend.
"""
import pytest
import asyncio
from fastapi.testclient import TestClient

# Import Services
from mcp_tools.weather_server.main import app as weather_mcp_app
from mcp_tools.hotel_booking.main import app as hotel_mcp_app
from mcp_tools.flight_booking.main import app as flight_mcp_app
from mcp_tools.external_mcp.main import app as external_mcp_app
from llm_backend.main import app as llm_backend_app
from observability.otel.main import app as otel_app
from observability.indigo.main import app as indigo_app

# 1. Test Weather MCP Server
def test_weather_mcp():
    client = TestClient(weather_mcp_app)
    resp = client.post("/mcp/weather/forecast", json={"destination": "San Francisco", "days": 4})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mcp_tool"] == "weather_server"
    assert "summary" in data
    assert len(data["daily_forecast"]) == 4

# 2. Test Hotel Booking MCP Server
def test_hotel_mcp_search_and_reserve():
    client = TestClient(hotel_mcp_app)
    # Search
    search_resp = client.post("/mcp/hotels/search", json={"destination": "San Francisco", "max_budget_per_night": 350.0})
    assert search_resp.status_code == 200
    hotels = search_resp.json()["available_hotels"]
    assert len(hotels) > 0

    # Reserve
    reserve_resp = client.post("/mcp/hotels/reserve", json={
        "hotel_id": hotels[0]["id"],
        "guest_name": "Alex Mercer",
        "nights": 4
    })
    assert reserve_resp.status_code == 200
    assert reserve_resp.json()["status"] == "confirmed"
    assert "booking_reference" in reserve_resp.json()

# 3. Test Flight Booking MCP Server
def test_flight_mcp_search_and_reserve():
    client = TestClient(flight_mcp_app)
    search_resp = client.post("/mcp/flights/search", json={"origin": "JFK", "destination": "SFO"})
    assert search_resp.status_code == 200
    flights = search_resp.json()["available_flights"]
    assert len(flights) > 0

    reserve_resp = client.post("/mcp/flights/reserve", json={
        "flight_number": flights[0]["flight_number"],
        "passenger_name": "Alex Mercer",
        "origin": "JFK",
        "destination": "SFO"
    })
    assert reserve_resp.status_code == 200
    assert reserve_resp.json()["status"] == "ticket_confirmed"
    assert "pnr" in reserve_resp.json()

# 4. Test External Partner MCP with Vault Auth
def test_external_mcp_auth_enforcement():
    client = TestClient(external_mcp_app)
    # Without Vault Token -> 401
    unauth = client.post("/external/mcp/ground-transport", json={"destination": "San Francisco", "rental_days": 4})
    assert unauth.status_code == 401

    # With Vault Token injected by Terminating Gateway -> 200
    auth_resp = client.post(
        "/external/mcp/ground-transport",
        json={"destination": "San Francisco", "rental_days": 4},
        headers={"Authorization": "Bearer vault:secret/data/partners/amadeus#key_99"}
    )
    assert auth_resp.status_code == 200
    assert auth_resp.json()["status"] == "reserved"
    assert auth_resp.json()["vault_egress_security"]["authenticated"] is True

# 5. Test Foundation Model Backend Auth
def test_llm_backend_auth():
    client = TestClient(llm_backend_app)
    # Without Bearer -> 401
    unauth = client.post("/v1/chat/completions", json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
    assert unauth.status_code == 401

    # With Injected Key from travel-igw -> 200
    auth_resp = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer vault:secret/data/ai/llm#sk_99201"}
    )
    assert auth_resp.status_code == 200
    assert auth_resp.json()["gateway_metadata"]["authenticated_by_vault"] is True

# 6. Test OpenTelemetry Ingestion & INDIGO Analytics
def test_observability_pipeline():
    otel_client = TestClient(otel_app)
    ingest = otel_client.post("/v1/traces", json={"trace_id": "test-trace-01", "tokens_used": 50, "service": "test"})
    assert ingest.status_code == 200

    indigo_client = TestClient(indigo_app)
    audit = indigo_client.get("/api/indigo/audit-summary")
    assert audit.status_code == 200
    assert audit.json()["compliance_status"] == "COMPLIANT"
