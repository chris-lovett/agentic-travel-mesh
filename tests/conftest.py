"""
CAMP Travel Mesh — Global Pytest Configuration & In-Memory Mesh Harness
Provides:
- In-memory MeshRoutingTransport dispatching HTTP calls across all 11 FastAPI applications
- Gateway emulation for Envoy Ingress (api-gw), AI Gateway (travel-igw), and Terminating Gateway (terminating-gw)
- Automatic state isolation resetting module-level state between tests
- Preconfigured async and synchronous test clients for all services
"""
import pytest
import httpx
from fastapi.testclient import TestClient
from typing import Dict, Any, Optional

from frontend.main import app as frontend_app, trips_database, audit_events
from agents.orchestrator.main import app as orchestrator_app
from agents.booking_agent.main import app as booking_app
from agents.weather_agent.main import app as weather_agent_app
from mcp_tools.weather_server.main import app as weather_mcp_app
from mcp_tools.hotel_booking.main import app as hotel_mcp_app
from mcp_tools.flight_booking.main import app as flight_mcp_app
from mcp_tools.external_mcp.main import app as external_mcp_app
from llm_backend.main import app as llm_app, local_outage_state, token_usage_stats
from observability.otel.main import app as otel_app, traces_store, bullmq_relay_queue
from observability.indigo.main import (
    app as indigo_app,
    agent_circuits,
    fingerprint_counters,
    cycle_events,
    governance_events,
    runtime_flags,
)

SERVICE_APPS = {
    "frontend:3000": frontend_app,
    "api-gw:10000": orchestrator_app,
    "travel-orchestrator:8080": orchestrator_app,
    "booking-agent:8086": booking_app,
    "weather-agent:8087": weather_agent_app,
    "weather-mcp:8082": weather_mcp_app,
    "hotel-mcp:8083": hotel_mcp_app,
    "flight-mcp:8084": flight_mcp_app,
    "external-mcp:8088": external_mcp_app,
    "llm-backend:8081": llm_app,
    "travel-igw:10001": llm_app,
    "terminating-gw:10002": external_mcp_app,
    "otel-collector:4318": otel_app,
    "indigo-analytics:8089": indigo_app,
}

_asgi_transports = {k: httpx.ASGITransport(app=v) for k, v in SERVICE_APPS.items()}

# State for gateway rate limiting simulation
rate_limit_state = {"tokens_remaining": 100, "force_rate_limit": False}


class MeshRoutingTransport(httpx.AsyncBaseTransport):
    """
    Intercepts mesh HTTP calls and dispatches to the in-memory ASGI application
    with Envoy gateway emulation (api-gw, travel-igw, terminating-gw).
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        port = request.url.port
        path = request.url.path

        # Handle Tempo dummy response if intercepted
        if host == "tempo":
            return httpx.Response(200, json={"status": "ok", "service": "tempo"})

        # Normalize key
        key = f"{host}:{port}" if port else host

        # 1. Gateway Plane Emulation: api-gw:10000
        if host == "api-gw" or port == 10000:
            if not path.startswith("/agent/orchestrate") and path not in ["/healthz", "/"]:
                return httpx.Response(404, json={"detail": "Route not found on api-gw"})
            target_transport = _asgi_transports["api-gw:10000"]
            return await target_transport.handle_async_request(request)

        # 2. Gateway Plane Emulation: travel-igw:10001
        if host == "travel-igw" or port == 10001:
            if rate_limit_state["force_rate_limit"]:
                return httpx.Response(429, json={"detail": "Too Many Requests - Local Rate Limit Exceeded"})
            # Inject Vault Bearer token and tier header per Envoy configuration
            if path.startswith("/v1/messages"):
                request.headers.setdefault("Authorization", "Bearer vault:secret/data/ai/anthropic#api_key_ant_8820")
            else:
                request.headers.setdefault("Authorization", "Bearer vault:secret/data/ai/llm#api_key_sk_99201")
            request.headers.setdefault("x-consul-mesh-tier", "travel-igw-2.1")
            target_transport = _asgi_transports["travel-igw:10001"]
            return await target_transport.handle_async_request(request)

        # 3. Gateway Plane Emulation: terminating-gw:10002
        if host == "terminating-gw" or port == 10002:
            request.headers.setdefault(
                "Authorization",
                "Bearer vault:secret/data/partners/amadeus#gds_token_9918",
            )
            request.headers.setdefault("x-egress-gateway", "consul-terminating-gw-2.1")
            target_transport = _asgi_transports["terminating-gw:10002"]
            return await target_transport.handle_async_request(request)

        # Direct service mapping
        transport = _asgi_transports.get(key)
        if not transport:
            # Try port matching
            for registered_key, trans in _asgi_transports.items():
                if f":{port}" in registered_key:
                    transport = trans
                    break
        if not transport:
            raise RuntimeError(
                f"Unmapped mesh host: {key} (path: {path}). Available: {list(_asgi_transports.keys())}"
            )

        return await transport.handle_async_request(request)


# Singleton transport instance
_global_mesh_transport = MeshRoutingTransport()


@pytest.fixture(autouse=True)
def patch_mesh_transport(monkeypatch):
    """
    Ensures all httpx.AsyncClient instances automatically use the in-memory
    mesh routing transport unless an explicit custom transport is provided.
    """
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        if "transport" not in kwargs:
            kwargs["transport"] = _global_mesh_transport
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


def reset_all_mesh_state():
    """Resets all in-memory state stores for complete test isolation."""
    trips_database.clear()
    audit_events.clear()
    traces_store.clear()
    bullmq_relay_queue.clear()
    local_outage_state["simulate_primary_llm_outage"] = False
    token_usage_stats.update({
        "total_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "failovers_executed": 0,
    })
    fingerprint_counters.clear()
    cycle_events.clear()
    governance_events.clear()
    runtime_flags.update({
        "simulate_primary_llm_outage": False,
        "policy_violations_prevented": 0,
        "cycles_detected": 0,
        "obo_exchanges_verified": 0,
        "hitl_gates_enforced": 0,
    })
    rate_limit_state["tokens_remaining"] = 100
    rate_limit_state["force_rate_limit"] = False

    for spiffe in list(agent_circuits.keys()):
        agent_circuits[spiffe] = {
            "state": "CLOSED",
            "reason": "Normal operation",
            "repetition_count": 0,
            "updated_at": "baseline",
        }


@pytest.fixture(autouse=True)
def reset_mesh_state():
    """Auto-use fixture that resets mesh state before and after every test."""
    reset_all_mesh_state()
    yield
    reset_all_mesh_state()


@pytest.fixture
def mesh_transport():
    return _global_mesh_transport


@pytest.fixture
def mesh_client():
    """Async client connected to experience-ui (frontend:3000) with mesh transport."""
    client = httpx.AsyncClient(base_url="http://frontend:3000", transport=_global_mesh_transport)
    yield client


@pytest.fixture
def orchestrator_client():
    """Async client connected to api-gw:10000 with mesh transport."""
    client = httpx.AsyncClient(base_url="http://api-gw:10000", transport=_global_mesh_transport)
    yield client


@pytest.fixture
def weather_mcp_client():
    return TestClient(weather_mcp_app)


@pytest.fixture
def hotel_mcp_client():
    return TestClient(hotel_mcp_app)


@pytest.fixture
def flight_mcp_client():
    return TestClient(flight_mcp_app)


@pytest.fixture
def external_mcp_client():
    return TestClient(external_mcp_app)


@pytest.fixture
def llm_backend_client():
    return TestClient(llm_app)


@pytest.fixture
def otel_client():
    return TestClient(otel_app)


@pytest.fixture
def indigo_client():
    return TestClient(indigo_app)


@pytest.fixture
def frontend_client():
    return TestClient(frontend_app)


@pytest.fixture
def orchestrator_test_client():
    return TestClient(orchestrator_app)


@pytest.fixture
def booking_agent_test_client():
    return TestClient(booking_app)


@pytest.fixture
def weather_agent_test_client():
    return TestClient(weather_agent_app)


@pytest.fixture
def indigo_analytics_client():
    return TestClient(indigo_app)


@pytest.fixture
def booking_agent_client():
    return TestClient(booking_app)


@pytest.fixture
def terminating_gw_client():
    return TestClient(external_mcp_app)


@pytest.fixture
def weather_server_client():
    return TestClient(weather_mcp_app)


@pytest.fixture
def travel_igw_client():
    return TestClient(llm_app)

