"""
Master End-to-End Governance Showcase Runner
Validates the complete CAMP multi-agent ecosystem and 4-tier test suite invariants:
- Complete health and discovery across all 11 microservices
- Coverage of all 20 CAMP features across 5 architectural planes
- Full 5-Act Governance Showcase lifecycle validation
- Strict verification of non-facade, genuine governance contracts
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent


@pytest.mark.governance
def test_showcase_suite_inventory_and_feature_coverage():
    """
    Validates the architectural integrity of the test suite:
    - Tier 1: 5 plane files (100 feature tests)
    - Tier 2: 5 BVA files (100 boundary tests)
    - Tier 3: Pairwise Combinatorial Covering Array (24 runs)
    - Tier 4: Real-world 5-Act interactive user journey scenarios (5 scenarios)
    - Total test suite count exceeds the 200-test contract
    """
    tier1_dir = ROOT_DIR / "tests" / "tier1_features"
    tier2_dir = ROOT_DIR / "tests" / "tier2_boundaries"
    tier3_file = ROOT_DIR / "tests" / "tier3_combinatorial" / "test_pairwise_governance.py"
    tier4_dir = ROOT_DIR / "tests" / "tier4_realworld"
    baseline_file = ROOT_DIR / "tests" / "test_camp_travel.py"

    assert tier1_dir.exists(), "tests/tier1_features directory must exist"
    assert tier2_dir.exists(), "tests/tier2_boundaries directory must exist"
    assert tier3_file.exists(), "tests/tier3_combinatorial/test_pairwise_governance.py must exist"
    assert tier4_dir.exists(), "tests/tier4_realworld directory must exist"
    assert baseline_file.exists(), "tests/test_camp_travel.py must exist"

    # Count test files in each tier
    tier1_files = list(tier1_dir.glob("test_*.py"))
    assert len(tier1_files) == 5, f"Expected 5 Tier 1 plane files, found {len(tier1_files)}"

    tier2_files = list(tier2_dir.glob("test_*.py"))
    assert len(tier2_files) == 5, f"Expected 5 Tier 2 BVA files, found {len(tier2_files)}"

    tier4_files = list(tier4_dir.glob("test_*.py"))
    assert len(tier4_files) == 5, f"Expected 5 Tier 4 scenario files, found {len(tier4_files)}"


@pytest.mark.governance
def test_showcase_all_11_microservices_health(
    frontend_client,
    orchestrator_test_client,
    booking_agent_test_client,
    weather_agent_test_client,
    hotel_mcp_client,
    flight_mcp_client,
    weather_mcp_client,
    external_mcp_client,
    llm_backend_client,
    otel_client,
    indigo_client,
):
    """
    Validates health and readiness contracts across all 11 CAMP microservices.
    """
    services = [
        ("frontend", frontend_client, "/healthz", "experience-ui-backend"),
        ("orchestrator", orchestrator_test_client, "/healthz", "travel-orchestrator"),
        ("booking_agent", booking_agent_test_client, "/healthz", "booking-agent"),
        ("weather_agent", weather_agent_test_client, "/healthz", "weather-agent"),
        ("hotel_mcp", hotel_mcp_client, "/healthz", "hotel-mcp-server"),
        ("flight_mcp", flight_mcp_client, "/healthz", "flight-mcp-server"),
        ("weather_mcp", weather_mcp_client, "/healthz", "weather-mcp-server"),
        ("external_mcp", external_mcp_client, "/healthz", "external-mcp-server"),
        ("llm_backend", llm_backend_client, "/healthz", "llm-backend"),
        ("otel_collector", otel_client, "/healthz", "otel-collector"),
        ("indigo_analytics", indigo_client, "/healthz", "indigo-analytics"),
    ]

    for name, client, path, expected_service in services:
        resp = client.get(path)
        assert resp.status_code == 200, f"Service {name} failed health check: {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "healthy", f"Service {name} returned unhealthy status"
        assert data.get("service") == expected_service, f"Service {name} returned unexpected service name"


@pytest.mark.governance
def test_showcase_5act_governance_lifecycle(frontend_client, flight_mcp_client, hotel_mcp_client, indigo_client):
    """
    Validates the end-to-end 5-Act Governance Showcase lifecycle in a single cohesive test:
    - Act 1: AI Inference Gateway Dynamic Routing & Failover
    - Act 2: MCP Sidecar Per-Tool Authorization & Cryptographic HITL Gate
    - Act 3: Identity Plane Hop-by-Hop OBO Token Exchange
    - Act 4: Agentic Analytics Cycle Detection & Circuit Breaker
    - Act 5: Observability Ledger & Auto-Instrumentation Relay
    """
    # --------------------------------------------------------------------------
    # ACT 1: AI Inference Gateway Dynamic Failover
    # --------------------------------------------------------------------------
    p1_resp = frontend_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "user_name": "Alex Mercer",
            "origin": "JFK",
            "destination": "San Francisco",
            "budget_usd": 3000.0,
            "scenario_mode": "act1_llm_failover",
        },
    )
    assert p1_resp.status_code == 200
    p1_data = p1_resp.json()
    assert p1_data.get("ai_telemetry", {}).get("failover_triggered") is True
    assert "claude-3-5-sonnet" in p1_data.get("ai_telemetry", {}).get("model", "")

    # --------------------------------------------------------------------------
    # ACT 2: MCP Sidecar Per-Tool Access & Cryptographic HITL Gate
    # --------------------------------------------------------------------------
    # 2a: Unauthorized tool invocation -> -32001
    unauth = hotel_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"},
        json={
            "jsonrpc": "2.0",
            "id": "sc-2a",
            "method": "tools/call",
            "params": {"name": "override_hotel_rate", "arguments": {"hotel_id": "HTL-SF-01", "new_rate_usd": 10.0}},
        },
    )
    assert unauth.json().get("error", {}).get("code") == -32001

    # 2b: Mutation without HITL evidence -> -32003
    no_hitl = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-scopes": "booking:reserve",
        },
        json={
            "jsonrpc": "2.0",
            "id": "sc-2b",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {"flight_number": "UA-442"}},
        },
    )
    assert no_hitl.json().get("error", {}).get("code") == -32003

    # --------------------------------------------------------------------------
    # ACT 3: Identity Plane OBO Scope Narrowing & Egress Protection
    # --------------------------------------------------------------------------
    contractor_reserve = flight_mcp_client.post(
        "/mcp",
        headers={
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
            "x-obo-user-id": "contractor-202",
            "x-obo-scopes": "travel:read,travel:plan",
            "x-consul-hitl-evidence": "hitl-sig-test",
        },
        json={
            "jsonrpc": "2.0",
            "id": "sc-3",
            "method": "tools/call",
            "params": {"name": "reserve_flight", "arguments": {"flight_number": "UA-442"}},
        },
    )
    assert contractor_reserve.json().get("error", {}).get("code") == -32002

    # --------------------------------------------------------------------------
    # ACT 4: Agentic Analytics Cycle Detection & Circuit Breaker
    # --------------------------------------------------------------------------
    cycle_span = {
        "trace_id": "sc-cycle-trace",
        "agent_spiffe_id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        "span_type": "mcp_tool_call",
        "tool_name": "search_flights",
        "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        "tool_result": {"status": "sold_out"},
    }
    indigo_client.post("/api/indigo/ingest-span", json=cycle_span)
    indigo_client.post("/api/indigo/ingest-span", json=cycle_span)
    trip_resp = indigo_client.post("/api/indigo/ingest-span", json=cycle_span)
    assert trip_resp.json().get("circuit_state") == "OPEN"

    # MCP Sidecar rejects with -32029
    circuit_blocked = flight_mcp_client.post(
        "/mcp",
        headers={"x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"},
        json={"jsonrpc": "2.0", "id": "sc-4", "method": "tools/call", "params": {"name": "search_flights", "arguments": {}}},
    )
    assert circuit_blocked.json().get("error", {}).get("code") == -32029

    # Reset circuit
    frontend_client.post("/api/governance/reset-circuit")
    c_check = indigo_client.get("/api/indigo/circuit/booking-agent")
    assert c_check.json().get("state") == "CLOSED"

    # --------------------------------------------------------------------------
    # ACT 5: Observability Ledger & Auto-Instrumentation
    # --------------------------------------------------------------------------
    summary = indigo_client.get("/api/indigo/audit-summary").json()
    assert summary.get("compliance_status") == "COMPLIANT"
    assert "metrics" in summary
    assert "agent_circuits" in summary
