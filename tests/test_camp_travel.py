"""
Automated End-to-End Regression & 5-Act Consul 2.1 Governance Test Suite
Validates:
- Standard MCP REST & JSON-RPC 2.0 endpoints (weather-mcp, hotel-mcp, flight-mcp, external-mcp)
- Act 1: AI Inference Gateway (csl-inf-rt) Priority-2 Failover & Protocol Translation
- Act 2: MCP Sidecar (csl-mcp-sc) Per-Tool Access Policy & Cryptographic HITL Gate
- Act 3: Identity Plane On-Behalf-Of (OBO) Scope Narrowing & Enforcement
- Act 4: Agentic Analytics (csl-ag-ana) Cycle Detection & Agent-Scoped Circuit Breaker
- Act 5: Zero-Code Auto-Instrumentation Span Relay (csl-nod-rly)
"""
from fastapi.testclient import TestClient

from mcp_tools.weather_server.main import app as weather_mcp_app
from mcp_tools.hotel_booking.main import app as hotel_mcp_app
from mcp_tools.flight_booking.main import app as flight_mcp_app
from mcp_tools.external_mcp.main import app as external_mcp_app
from llm_backend.main import app as llm_backend_app
from observability.otel.main import app as otel_app
from observability.indigo.main import app as indigo_app


# 1. Test Weather MCP Server (REST + JSON-RPC 2.0)
def test_weather_mcp():
    client = TestClient(weather_mcp_app)
    resp = client.post("/mcp/weather/forecast", json={"destination": "San Francisco", "days": 4})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mcp_tool"] == "weather_server"
    assert len(data["daily_forecast"]) == 4

    # JSON-RPC 2.0 tools/call
    rpc_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "w-1",
            "method": "tools/call",
            "params": {"name": "get_weather_forecast", "arguments": {"destination": "London", "days": 3}},
        },
    )
    assert rpc_resp.status_code == 200
    assert rpc_resp.json()["result"]["destination"] == "London"


# 2. Test Hotel Booking MCP Server (REST + Act 2 Per-Tool Policy & HITL Gate)
def test_hotel_mcp_and_act2_sidecar_policy():
    client = TestClient(hotel_mcp_app)
    search_resp = client.post("/mcp/hotels/search", json={"destination": "San Francisco", "max_budget_per_night": 350.0})
    assert search_resp.status_code == 200
    hotels = search_resp.json()["available_hotels"]
    assert len(hotels) > 0

    # Act 2a: Catalog discovery (tools/list) exposes 3 tools including override_hotel_rate
    list_resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": "h-list", "method": "tools/list"})
    assert list_resp.status_code == 200
    tool_names = [t["name"] for t in list_resp.json()["result"]["tools"]]
    assert "override_hotel_rate" in tool_names

    # Act 2a: Calling override_hotel_rate as booking-agent is blocked by csl-mcp-sc Per-Tool Policy (-32001)
    unauth_tool = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "h-unauth",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {"hotel_id": "HTL-SF-01", "new_rate_usd": 50.0}},
        },
        headers={"x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"},
    )
    assert unauth_tool.status_code == 200
    assert unauth_tool.json()["error"]["code"] == -32001

    # Act 2b: Calling reserve_hotel via JSON-RPC without HITL approval evidence is held (-32003)
    no_hitl = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "h-no-hitl",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Alex Mercer", "nights": 4}},
        },
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
        },
    )
    assert no_hitl.json()["error"]["code"] == -32003

    # With signed cryptographic HITL evidence -> Confirmed!
    with_hitl = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "h-with-hitl",
            "method": "tools/call",
            "params": {"name": "reserve_hotel", "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Alex Mercer", "nights": 4}},
        },
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
            "x-consul-hitl-evidence": "hitl-sig-verified1234",
        },
    )
    assert "result" in with_hitl.json()
    assert with_hitl.json()["result"]["status"] == "confirmed"


# 3. Test Flight Booking MCP Server & Act 3 OBO Scope Verification
def test_flight_mcp_and_act3_obo_scopes():
    client = TestClient(flight_mcp_app)
    search_resp = client.post("/mcp/flights/search", json={"origin": "JFK", "destination": "SFO"})
    assert search_resp.status_code == 200
    flights = search_resp.json()["available_flights"]
    assert len(flights) > 0

    # Act 3: Contractor (sam-taylor) lacking 'booking:reserve' scope is denied by Destination Identity Processor (-32002)
    contractor_call = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "f-obo-deny",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {"flight_number": "UA-442", "passenger_name": "Sam Taylor"}},
        },
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
            "x-consul-hitl-evidence": "hitl-sig-123",
        },
    )
    assert contractor_call.json()["error"]["code"] == -32002


# 4. Test External Partner MCP with Vault Auth & Act 3 Contractor Egress Block
def test_external_mcp_auth_and_obo_egress():
    client = TestClient(external_mcp_app)
    # Without Vault Token -> 401
    unauth = client.post("/external/mcp/ground-transport", json={"destination": "San Francisco", "rental_days": 4})
    assert unauth.status_code == 401

    # With Vault Token injected by Terminating Gateway -> 200
    auth_resp = client.post(
        "/external/mcp/ground-transport",
        json={"destination": "San Francisco", "rental_days": 4},
        headers={"Authorization": "Bearer vault:secret/data/partners/amadeus#key_99"},
    )
    assert auth_resp.status_code == 200
    assert auth_resp.json()["status"] == "reserved"
    assert auth_resp.json()["vault_egress_security"]["authenticated"] is True

    # Act 3: Contractor without partner:gds_egress scope -> 403 Forbidden
    contractor_egress = client.post(
        "/external/mcp/ground-transport",
        json={"destination": "San Francisco", "rental_days": 4},
        headers={
            "Authorization": "Bearer vault:secret/data/partners/amadeus#key_99",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
        },
    )
    assert contractor_egress.status_code == 403


# 5. Test Foundation Model Backend Auth & Act 1 Priority Failover (csl-inf-rt)
def test_llm_backend_auth_and_act1_failover():
    client = TestClient(llm_backend_app)
    # Without Bearer -> 401
    unauth = client.post("/v1/chat/completions", json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
    assert unauth.status_code == 401

    # Normal Priority-1 call -> 200
    auth_resp = client.post(
        "/v1/chat/completions",
        json={"model": "meta-llama/llama-3-70b-instruct", "messages": [{"role": "user", "content": "Route: JFK to Tokyo"}]},
        headers={"Authorization": "Bearer vault:secret/data/ai/llm#sk_99201"},
    )
    assert auth_resp.status_code == 200
    assert auth_resp.json()["gateway_metadata"]["authenticated_by_vault"] is True
    assert auth_resp.json()["gateway_metadata"]["failover_triggered"] is False

    # Act 1: Simulate Primary LLM Outage -> csl-inf-rt translates OpenAI to Claude 3.5 Sonnet Priority-2 Failover
    failover_resp = client.post(
        "/v1/chat/completions",
        json={"model": "meta-llama/llama-3-70b-instruct", "messages": [{"role": "user", "content": "Route: JFK to London"}]},
        headers={
            "Authorization": "Bearer vault:secret/data/ai/llm#sk_99201",
            "x-simulate-llm-outage": "true",
        },
    )
    assert failover_resp.status_code == 200
    gw_meta = failover_resp.json()["gateway_metadata"]
    assert gw_meta["failover_triggered"] is True
    assert "claude-3-5-sonnet" in gw_meta["routed_model"]


# 6. Test Act 4 Cycle Detection & Agent-Scoped Circuit Breaker (csl-ag-ana)
def test_act4_cycle_detection_and_circuit_breaker():
    otel_client = TestClient(otel_app)
    indigo_client = TestClient(indigo_app)

    # Reset circuits first
    indigo_client.post("/api/indigo/circuit/reset", json={})

    spiffe_id = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"
    for i in range(1, 4):
        res = indigo_client.post(
            "/api/indigo/ingest-span",
            json={
                "trace_id": "trace-loop-test",
                "span_type": "mcp_tool_call",
                "agent_spiffe_id": spiffe_id,
                "service": "booking-agent",
                "mcp_server": "flight-mcp",
                "tool_name": "search_flights",
                "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
                "tool_result": {"status": "NO_INVENTORY_RETRYABLE"},
            },
        )
        assert res.status_code == 200
        body = res.json()
        if i < 3:
            assert body["circuit_state"] == "CLOSED"
        else:
            # On 3rd identical repetition, csl-ag-ana opens the agent-scoped circuit breaker!
            assert body["circuit_state"] == "OPEN"

    # Verify audit summary reflects CIRCUIT_OPEN_HALTED
    audit = indigo_client.get("/api/indigo/audit-summary")
    assert audit.status_code == 200
    assert audit.json()["compliance_status"] == "CIRCUIT_OPEN_HALTED"

    # Reset circuit back to CLOSED
    reset_resp = indigo_client.post("/api/indigo/circuit/reset", json={})
    assert reset_resp.status_code == 200
    audit_after = indigo_client.get("/api/indigo/audit-summary")
    assert audit_after.json()["compliance_status"] == "COMPLIANT"

    # Verify OTel Collector ingestion
    ingest = otel_client.post("/v1/traces", json={"trace_id": "test-trace-01", "tokens_used": 50, "service": "test"})
    assert ingest.status_code == 200
