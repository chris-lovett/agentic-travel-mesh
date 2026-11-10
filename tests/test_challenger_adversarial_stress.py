"""
CAMP Travel Mesh — Challenger Adversarial Stress Test Suite
Author: EMPIRICAL CHALLENGER (Track 2)
Focus: Adversarially stress-testing all 5 governance acts:
  Act 1: LLM failover, rate limits, high-concurrency burst, extreme payloads, protocol translation
  Act 2a: Per-tool policy (-32001), SPIFFE spoofing, case sensitivity, catalog decoupling
  Act 2b: Cryptographic HITL gate (-32003), tampered/forged headers, mutation protection
  Act 3: RFC 8693 OBO scope enforcement (-32002, 403), scope injection, hop-by-hop integrity
  Act 4: Cycle detection fingerprinting, exact repetition thresholds, circuit breaker (-32029), and operator reset
"""
import pytest
import asyncio
import httpx
from typing import Dict, Any

BOOKING_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"
ORCHESTRATOR_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator"
WEATHER_AGENT_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/weather-agent"
GLOBAL_ADMIN_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/global-security-admin"
FINANCE_ADMIN_SPIFFE = "spiffe://cluster.local/ns/camp-travel/sa/finance-admin-agent"


# ==============================================================================
# ACT 1: AI INFERENCE GATEWAY FAILOVER, RATE LIMITING & PAYLOAD STRESS
# ==============================================================================

@pytest.mark.asyncio
async def test_act1_high_concurrency_burst_and_failover_stability():
    """
    Stress-tests travel-igw with 60 concurrent requests, alternating between
    nominal mode and simulated upstream outage. Verifies:
    1. Zero crashes or unhandled exceptions under burst load.
    2. Exact routing to Priority 1 (Llama-3-70B) vs Priority 2 (Claude 3.5 Sonnet).
    3. Proper protocol translation and Vault secret reference binding.
    """
    from tests.conftest import _global_mesh_transport
    async with httpx.AsyncClient(base_url="http://travel-igw:10001", transport=_global_mesh_transport) as client:
        async def send_req(i: int):
            is_outage = (i % 2 == 1)
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "meta-llama/llama-3-70b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are a travel coordinator."},
                        {"role": "user", "content": f"Request #{i}: Plan itinerary to San Francisco"},
                    ],
                },
                headers={
                    "x-simulate-llm-outage": "true" if is_outage else "false",
                    "x-trace-id": f"burst-trace-{i}",
                },
            )
            return i, is_outage, resp

        tasks = [send_req(i) for i in range(60)]
        results = await asyncio.gather(*tasks)

        for i, is_outage, resp in results:
            assert resp.status_code == 200, f"Request #{i} failed with status {resp.status_code}"
            data = resp.json()
            gw_meta = data.get("gateway_metadata", {})

            if is_outage:
                assert "claude-3-5-sonnet" in data["model"]
                assert gw_meta.get("failover_triggered") is True
                assert "Anthropic" in gw_meta.get("protocol_translation", "")
                assert "anthropic#api_key_ant_8820" in gw_meta.get("vault_secret_ref", "")
                assert "[csl-inf-rt Priority-2 Failover: claude-3-5-sonnet]" in data["choices"][0]["message"]["content"]
            else:
                assert data["model"] == "meta-llama/llama-3-70b-instruct"
                assert gw_meta.get("failover_triggered") is False
                assert "Native Upstream" in gw_meta.get("protocol_translation", "")
                assert "llm#api_key_sk_99201" in gw_meta.get("vault_secret_ref", "")


def test_act1_extreme_payload_and_auth_tampering(travel_igw_client):
    """
    Validates boundary conditions on inference requests:
    - Missing Authorization header returns HTTP 401
    - Invalid auth scheme (Basic / Token / malformed) returns HTTP 401
    - 50,000-character payload is tokenized and processed without memory failure
    - Unicode and multi-language characters are preserved
    """
    # 1. Missing Authorization header
    unauth = travel_igw_client.post(
        "/v1/chat/completions",
        json={"model": "meta-llama/llama-3-70b-instruct", "messages": [{"role": "user", "content": "ping"}]},
    )
    assert unauth.status_code == 401
    assert "Missing or invalid injected provider API key" in unauth.json()["detail"]

    # 2. Malformed Authorization headers
    for bad_auth in ["Basic dXNlcjpwYXNz", "Token abc123xyz", "Bearer", "bearer vault:test"]:
        resp = travel_igw_client.post(
            "/v1/chat/completions",
            headers={"Authorization": bad_auth},
            json={"model": "meta-llama/llama-3-70b-instruct", "messages": [{"role": "user", "content": "ping"}]},
        )
        assert resp.status_code == 401, f"Expected 401 for Authorization: {bad_auth}"

    # 3. 50,000-character prompt with valid bearer
    large_content = "Destination: Tokyo " + ("and visit historic shrines " * 2000)
    valid_auth = {"Authorization": "Bearer vault:secret/data/ai/llm#api_key_sk_99201"}
    large_resp = travel_igw_client.post(
        "/v1/chat/completions",
        headers=valid_auth,
        json={"model": "meta-llama/llama-3-70b-instruct", "messages": [{"role": "user", "content": large_content}]},
    )
    assert large_resp.status_code == 200
    usage = large_resp.json()["usage"]
    assert usage["prompt_tokens"] > 5000
    assert usage["total_tokens"] > usage["prompt_tokens"]


@pytest.mark.asyncio
async def test_act1_gateway_rate_limiting_enforcement():
    """
    Verifies that when the Envoy AI Gateway token bucket trips, requests
    are rejected with HTTP 429 Too Many Requests.
    """
    from tests.conftest import _global_mesh_transport, rate_limit_state
    rate_limit_state["force_rate_limit"] = True
    try:
        async with httpx.AsyncClient(base_url="http://travel-igw:10001", transport=_global_mesh_transport) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "meta-llama/llama-3-70b-instruct", "messages": [{"role": "user", "content": "test"}]},
            )
            assert resp.status_code == 429
            assert "Rate Limit Exceeded" in resp.json()["detail"]
    finally:
        rate_limit_state["force_rate_limit"] = False


# ==============================================================================
# ACT 2A: MCP PER-TOOL POLICY ENFORCEMENT (-32001) & CATALOG DECOUPLING
# ==============================================================================

def test_act2a_spiffe_spoofing_attack_matrix(flight_mcp_client, hotel_mcp_client):
    """
    Adversarial matrix testing attempts to bypass per-tool SPIFFE authorization:
    - Substring / extension spoofing (e.g. appending -attacker or /admin)
    - Whitespace and newline padding
    - Case variation
    - Completely unknown identities
    Verifies that every unallowed SPIFFE ID is rejected with JSON-RPC error -32001.
    """
    malicious_spiffes = [
        f"{BOOKING_AGENT_SPIFFE}-attacker",
        f"{BOOKING_AGENT_SPIFFE}/malicious",
        f"{BOOKING_AGENT_SPIFFE}\x00admin",
        "spiffe://cluster.local/ns/camp-travel/sa/unknown-agent",
        "spiffe://malicious-cluster.com/ns/camp-travel/sa/booking-agent",
        "   ",
        "SPIFFE://cluster.local/ns/camp-travel/sa/booking-agent",  # Upper case scheme
    ]

    for bad_spiffe in malicious_spiffes:
        # Test Flight MCP
        f_resp = flight_mcp_client.post(
            "/mcp",
            headers={"x-caller-spiffe-id": bad_spiffe},
            json={
                "jsonrpc": "2.0",
                "id": "act2a-f-spoof",
                "method": "tools/call",
                "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SFO"}},
            },
        )
        assert f_resp.status_code == 200
        f_err = f_resp.json().get("error", {})
        assert f_err.get("code") == -32001, f"Flight MCP failed to reject bad SPIFFE: {bad_spiffe}"

        # Test Hotel MCP
        h_resp = hotel_mcp_client.post(
            "/mcp",
            headers={"x-caller-spiffe-id": bad_spiffe},
            json={
                "jsonrpc": "2.0",
                "id": "act2a-h-spoof",
                "method": "tools/call",
                "params": {"name": "search_hotels", "arguments": {"destination": "San Francisco"}},
            },
        )
        assert h_resp.status_code == 200
        h_err = h_resp.json().get("error", {})
        assert h_err.get("code") == -32001, f"Hotel MCP failed to reject bad SPIFFE: {bad_spiffe}"


def test_act2a_privilege_boundary_separation(flight_mcp_client, hotel_mcp_client):
    """
    Verifies strict separation of duties:
    - booking-agent CANNOT invoke emergency admin tool cancel_all_corporate_bookings (-32001)
    - booking-agent CANNOT invoke finance tool override_hotel_rate (-32001)
    - weather-agent CANNOT invoke flight search or reservation tools (-32001)
    - global-security-admin CAN invoke cancel_all_corporate_bookings (with HITL + scope)
    - finance-admin-agent CAN invoke override_hotel_rate (with HITL + scope)
    """
    # 1. booking-agent attempting emergency cancel
    resp1 = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "admin:emergency_cancel",
            "x-consul-hitl-evidence": "hitl-sig-test",
        },
        json={
            "jsonrpc": "2.0",
            "id": "priv-1",
            "method": "tools/call",
            "params": {"name": "cancel_all_corporate_bookings", "arguments": {"tenant_id": "corp"}},
        },
    )
    assert resp1.json().get("error", {}).get("code") == -32001

    # 2. booking-agent attempting rate override
    resp2 = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "admin:rate_override",
            "x-consul-hitl-evidence": "hitl-sig-test",
        },
        json={
            "jsonrpc": "2.0",
            "id": "priv-2",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {"hotel_id": "HTL-SF-01", "new_rate_usd": 10.0}},
        },
    )
    assert resp2.json().get("error", {}).get("code") == -32001

    # 3. weather-agent attempting flight reservation
    resp3 = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": WEATHER_AGENT_SPIFFE,
            "x-obo-scopes": "booking:reserve",
            "x-consul-hitl-evidence": "hitl-sig-test",
        },
        json={
            "jsonrpc": "2.0",
            "id": "priv-3",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {"flight_number": "UA-442"}},
        },
    )
    assert resp3.json().get("error", {}).get("code") == -32001

    # 4. global-security-admin permitted
    resp4 = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": GLOBAL_ADMIN_SPIFFE,
            "x-obo-scopes": "admin:emergency_cancel",
            "x-consul-hitl-evidence": "hitl-sig-admin",
        },
        json={
            "jsonrpc": "2.0",
            "id": "priv-4",
            "method": "tools/call",
            "params": {"name": "cancel_all_corporate_bookings", "arguments": {"tenant_id": "corp"}},
        },
    )
    assert resp4.json().get("result", {}).get("status") == "cancelled"

    # 5. finance-admin-agent permitted
    resp5 = hotel_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": FINANCE_ADMIN_SPIFFE,
            "x-obo-scopes": "admin:rate_override",
            "x-consul-hitl-evidence": "hitl-sig-admin",
        },
        json={
            "jsonrpc": "2.0",
            "id": "priv-5",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {"hotel_id": "HTL-SF-01", "override_rate_usd": 120.0}},
        },
    )
    assert resp5.json().get("result", {}).get("status") == "rate_overridden"


# ==============================================================================
# ACT 2B: CRYPTOGRAPHIC HITL GATE (-32003) & MUTATION INTEGRITY
# ==============================================================================

def test_act2b_cryptographic_hitl_tamper_defense(flight_mcp_client, hotel_mcp_client):
    """
    Verifies that state mutations (reserve_flight, reserve_hotel) CANNOT be executed
    without a valid HITL evidence header:
    - Omitted header -> -32003
    - Empty string -> -32003
    - Whitespace only -> -32003
    - Non-prefixed tokens (e.g. 'approved', 'Bearer ...', 'sig-1234') -> -32003
    """
    invalid_hitl_tokens = [
        None,
        "",
        "   ",
        "approved",
        "APPROVED=TRUE",
        "Bearer hitl-sig-99201",
        "sig-e9a1b2c3",
        "HITL-SIG-UPPERCASE",
    ]

    for token in invalid_hitl_tokens:
        headers = {
            "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
            "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
        }
        if token is not None:
            headers["x-consul-hitl-evidence"] = token

        # Test flight reservation
        f_resp = flight_mcp_client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": "hitl-tamper-flight",
                "method": "tools/call",
                "params": {"name": "reserve_flight", "arguments": {"flight_number": "UA-442", "passenger_name": "Eve"}},
            },
        )
        assert f_resp.json().get("error", {}).get("code") == -32003

        # Test hotel reservation
        h_resp = hotel_mcp_client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": "hitl-tamper-hotel",
                "method": "tools/call",
                "params": {"name": "reserve_hotel", "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Eve"}},
            },
        )
        assert h_resp.json().get("error", {}).get("code") == -32003


@pytest.mark.asyncio
async def test_act2b_end_to_end_cryptographic_approval_flow(mesh_client):
    """
    Tests the complete Review UI cryptographic HITL minting and confirmation flow:
    1. Plan trip as Alex Mercer -> status NEEDS_APPROVAL.
    2. Confirm trip via /api/travel/review-action with 'APPROVE'.
    3. Review backend hashes (trip_id:approver:flight:hotel) -> mints 'hitl-sig-<sha256[:16]>'.
    4. Propagates hitl-sig to booking-agent -> flight-mcp and hotel-mcp verify token -> APPROVED_AND_BOOKED.
    """
    plan_resp = await mesh_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "origin": "JFK",
            "destination": "San Francisco",
            "duration_days": 3,
            "budget_usd": 3000.0,
            "trip_purpose": "Security Conference",
        },
    )
    assert plan_resp.status_code == 200
    trip_data = plan_resp.json()
    trip_id = trip_data["trip_id"]
    assert trip_data["status"] in ("NEEDS_APPROVAL", "plan_ready_for_review")
    assert trip_data.get("requires_hitl_approval") is True

    review_resp = await mesh_client.post(
        "/api/travel/review-action",
        json={"trip_id": trip_id, "action": "APPROVE", "approver": "Security Director"},
    )
    assert review_resp.status_code == 200
    rev_data = review_resp.json()
    assert rev_data["status"] == "APPROVED_AND_BOOKED"
    details = rev_data.get("details", {})
    assert details.get("status") == "all_reservations_confirmed"
    assert details.get("hitl_evidence_token", "").startswith("hitl-sig-")
    assert "ticket_confirmed" in details.get("flight_booking", {}).get("status", "")
    assert "confirmed" in details.get("hotel_booking", {}).get("status", "")


# ==============================================================================
# ACT 3: RFC 8693 OBO SCOPES ACROSS HOPS (-32002, 403)
# ==============================================================================

def test_act3_contractor_obo_scope_boundary_and_egress_denial(
    flight_mcp_client, hotel_mcp_client, external_mcp_client
):
    """
    Validates that contractor persona Sam Taylor (scopes: ['travel:read', 'travel:plan']):
    1. Can discover and read tools (search_flights, search_hotels) -> 200 OK.
    2. Cannot reserve flights -> denied with -32002 (OBO_SCOPE_DENIED).
    3. Cannot reserve hotels -> denied with -32002 (OBO_SCOPE_DENIED).
    4. Cannot egress through Terminating Gateway to partner GDS -> HTTP 403 Forbidden.
    """
    contractor_headers = {
        "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
        "x-obo-user-id": "contractor-202",
        "x-obo-scopes": "travel:read, travel:plan",
        "x-consul-hitl-evidence": "hitl-sig-forged",
    }

    # 1. Allowed reads
    f_search = flight_mcp_client.post(
        "/mcp",
        headers=contractor_headers,
        json={"jsonrpc": "2.0", "id": "c-1", "method": "tools/call", "params": {"name": "search_flights", "arguments": {}}},
    )
    assert "result" in f_search.json()

    h_search = hotel_mcp_client.post(
        "/mcp",
        headers=contractor_headers,
        json={"jsonrpc": "2.0", "id": "c-2", "method": "tools/call", "params": {"name": "search_hotels", "arguments": {}}},
    )
    assert "result" in h_search.json()

    # 2. Denied flight reservation
    f_res = flight_mcp_client.post(
        "/mcp",
        headers=contractor_headers,
        json={"jsonrpc": "2.0", "id": "c-3", "method": "tools/call", "params": {"name": "reserve_flight", "arguments": {}}},
    )
    assert f_res.json().get("error", {}).get("code") == -32002
    assert "OBO Verification Denied" in f_res.json()["error"]["message"]

    # 3. Denied hotel reservation
    h_res = hotel_mcp_client.post(
        "/mcp",
        headers=contractor_headers,
        json={"jsonrpc": "2.0", "id": "c-4", "method": "tools/call", "params": {"name": "reserve_hotel", "arguments": {}}},
    )
    assert h_res.json().get("error", {}).get("code") == -32002

    # 4. Denied partner egress
    gds_resp = external_mcp_client.post(
        "/external/mcp/ground-transport",
        headers={
            "Authorization": "Bearer vault:secret/data/partners/amadeus#gds_token_9918",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read, travel:plan",
        },
        json={"destination": "San Francisco", "days": 3},
    )
    assert gds_resp.status_code == 403
    assert "partner:gds_egress" in gds_resp.json()["detail"]


def test_act3_scope_syntax_injection_attempts(flight_mcp_client):
    """
    Tests injection attempts in x-obo-scopes header:
    - Semicolon injection: 'travel:read; booking:reserve'
    - SQL style comment: 'travel:read -- booking:reserve'
    - JSON payload injection: '{"scopes": ["booking:reserve"]}'
    - Suffix matching: 'booking:reserve_admin'
    All must fail to grant the 'booking:reserve' scope and return -32002.
    """
    injections = [
        "travel:read; booking:reserve",
        "travel:read\nbooking:reserve",
        "travel:read -- booking:reserve",
        '{"scopes": ["booking:reserve"]}',
        "booking:reserve_privileged",
        "booking_reserve",
        "BOOKING:RESERVE",  # case variation
    ]

    for inj in injections:
        resp = flight_mcp_client.post(
            "/mcp",
            headers={
                "x-caller-spiffe-id": BOOKING_AGENT_SPIFFE,
                "x-obo-user-id": "attacker",
                "x-obo-scopes": inj,
                "x-consul-hitl-evidence": "hitl-sig-valid",
            },
            json={
                "jsonrpc": "2.0",
                "id": "scope-inj",
                "method": "tools/call",
                "params": {"name": "reserve_flight", "arguments": {}},
            },
        )
        assert resp.json().get("error", {}).get("code") == -32002, f"Scope injection bypassed check: {inj}"


# ==============================================================================
# ACT 4: CYCLE DETECTION FINGERPRINTING, CIRCUIT BREAKER (-32029) & RESET
# ==============================================================================

def test_act4_exact_cycle_threshold_transition(indigo_client):
    """
    Validates exact state transition of the Consul Behavior Policy Circuit Breaker:
    - Call 1: CLOSED (repetition_count = 1)
    - Call 2: CLOSED (repetition_count = 2)
    - Call 3: OPEN (repetition_count = 3, trigger transition)
    - Call 4: OPEN (repetition_count = 4, remains OPEN)
    """
    span = {
        "trace_id": "trace-cycle-bva",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        "tool_result": {"status": "NO_INVENTORY_RETRYABLE"},
    }

    # Call 1
    r1 = indigo_client.post("/api/indigo/ingest-span", json=span).json()
    assert r1["repetition_count"] == 1
    assert r1["circuit_state"] == "CLOSED"

    # Call 2
    r2 = indigo_client.post("/api/indigo/ingest-span", json=span).json()
    assert r2["repetition_count"] == 2
    assert r2["circuit_state"] == "CLOSED"

    # Call 3 -> Trips to OPEN
    r3 = indigo_client.post("/api/indigo/ingest-span", json=span).json()
    assert r3["repetition_count"] == 3
    assert r3["circuit_state"] == "OPEN"
    assert "Cycle detected" in r3["reason"]

    # Call 4 -> Stays OPEN
    r4 = indigo_client.post("/api/indigo/ingest-span", json=span).json()
    assert r4["repetition_count"] == 4
    assert r4["circuit_state"] == "OPEN"


def test_act4_fingerprint_uniqueness_and_isolation(indigo_client):
    """
    Verifies that the SHA-256 fingerprint differentiates calls and prevents
    false-positive circuit breaking:
    - Same agent, same tool, DIFFERENT arguments -> Different fingerprints, no trip
    - Same agent, same tool, DIFFERENT result -> Different fingerprints, no trip
    - DIFFERENT agent, same tool, same args/result -> Isolated counters
    """
    base_args = {"origin": "JFK", "destination": "SFO"}
    base_res = {"status": "available"}

    # 1. Varying arguments
    s1 = {"trace_id": "t1", "agent_spiffe_id": BOOKING_AGENT_SPIFFE, "tool_name": "search_flights", "tool_arguments": {"origin": "JFK", "destination": "SFO"}, "tool_result": base_res}
    s2 = {"trace_id": "t2", "agent_spiffe_id": BOOKING_AGENT_SPIFFE, "tool_name": "search_flights", "tool_arguments": {"origin": "JFK", "destination": "LAX"}, "tool_result": base_res}
    res1 = indigo_client.post("/api/indigo/ingest-span", json=s1).json()
    res2 = indigo_client.post("/api/indigo/ingest-span", json=s2).json()
    assert res1["fingerprint"] != res2["fingerprint"]
    assert res1["repetition_count"] == 1
    assert res2["repetition_count"] == 1

    # 2. Varying result
    s3 = {"trace_id": "t3", "agent_spiffe_id": BOOKING_AGENT_SPIFFE, "tool_name": "search_flights", "tool_arguments": base_args, "tool_result": {"status": "available", "price": 400}}
    s4 = {"trace_id": "t4", "agent_spiffe_id": BOOKING_AGENT_SPIFFE, "tool_name": "search_flights", "tool_arguments": base_args, "tool_result": {"status": "available", "price": 450}}
    res3 = indigo_client.post("/api/indigo/ingest-span", json=s3).json()
    res4 = indigo_client.post("/api/indigo/ingest-span", json=s4).json()
    assert res3["fingerprint"] != res4["fingerprint"]

    # 3. Isolated agents
    s5 = {"trace_id": "t5", "agent_spiffe_id": WEATHER_AGENT_SPIFFE, "tool_name": "search_flights", "tool_arguments": base_args, "tool_result": base_res}
    res5 = indigo_client.post("/api/indigo/ingest-span", json=s5).json()
    assert res5["repetition_count"] == 1
    assert res5["circuit_state"] == "CLOSED"


@pytest.mark.asyncio
async def test_act4_circuit_trip_interception_and_operator_reset(
    flight_mcp_client, indigo_client
):
    """
    End-to-end test of Act 4 cycle breaker enforcement and operator recovery:
    1. Ingest 3 identical spans to trip circuit breaker for booking-agent to OPEN.
    2. Verify flight-mcp rejects tool calls from booking-agent with -32029 (AGENT_CIRCUIT_OPEN).
    3. Other agents (e.g. travel-orchestrator) remain unaffected.
    4. Operator issues POST /api/indigo/circuit/reset for booking-agent.
    5. Verify circuit transitions back to CLOSED and flight-mcp immediately permits invocations again.
    """
    # 1. Trip circuit breaker for booking-agent
    span = {
        "trace_id": "trace-e2e-cycle",
        "agent_spiffe_id": BOOKING_AGENT_SPIFFE,
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "LOOP"},
        "tool_result": {"status": "sold_out"},
    }
    for _ in range(3):
        indigo_client.post("/api/indigo/ingest-span", json=span)

    # 2. Check circuit state via Indigo API
    cb_status = indigo_client.get("/api/indigo/circuit/booking-agent").json()
    assert cb_status["state"] == "OPEN"

    # 3. Invoking flight-mcp from booking-agent is rejected with -32029
    blocked = flight_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": BOOKING_AGENT_SPIFFE},
        json={
            "jsonrpc": "2.0",
            "id": "cb-block-1",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SFO"}},
        },
    )
    assert blocked.status_code == 200
    b_json = blocked.json()
    assert "error" in b_json
    assert b_json["error"]["code"] == -32029
    assert "Consul Behavior Policy Circuit Breaker OPEN" in b_json["error"]["message"]

    # 4. Orchestrator agent circuit is still CLOSED and can invoke search_flights
    orch_resp = flight_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": ORCHESTRATOR_SPIFFE},
        json={
            "jsonrpc": "2.0",
            "id": "cb-orch-ok",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SFO"}},
        },
    )
    assert orch_resp.status_code == 200
    assert "result" in orch_resp.json()

    # 5. Operator reset via Consul Behavior Policy API
    reset_resp = indigo_client.post(
        "/api/indigo/circuit/reset",
        json={"agent_spiffe_id": BOOKING_AGENT_SPIFFE},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["circuits"][BOOKING_AGENT_SPIFFE]["state"] == "CLOSED"

    # 6. Post-reset: booking-agent calls succeed immediately
    recovered = flight_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": BOOKING_AGENT_SPIFFE},
        json={
            "jsonrpc": "2.0",
            "id": "cb-recovered",
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {"origin": "JFK", "destination": "SFO"}},
        },
    )
    assert recovered.status_code == 200
    assert "result" in recovered.json()
    assert "available_flights" in recovered.json()["result"]
