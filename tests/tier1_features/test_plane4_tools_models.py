"""
Tier 1 Feature Tests — Architectural Plane 4: Tool & Foundation Model Plane + Infrastructure
Covers:
- Feature 1: consul-ai Dynamic Feature Gate (5 tests)
- Feature 2: AI Workload Classification CRDs (5 tests)
- Feature 5: Docker Compose 14-Service Stack (5 tests)
- Feature 6: Helm Chart Packaging & Routes (5 tests)
Total: 20 tests
"""
import pytest
import re
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


# ==============================================================================
# Feature 1: consul-ai Dynamic Feature Gate
# ==============================================================================
@pytest.mark.tier1
def test_f1_01_feature_gate_enabled_audit(indigo_client):
    """Verify /api/indigo/audit-summary reports feature_gate consul-ai=enabled."""
    resp = indigo_client.get("/api/indigo/audit-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("feature_gate") == "consul-ai=enabled"


@pytest.mark.tier1
def test_f1_02_compliance_status_reported(indigo_client):
    """Verify compliance_status is either COMPLIANT or CIRCUIT_OPEN_HALTED."""
    resp = indigo_client.get("/api/indigo/audit-summary")
    assert resp.status_code == 200
    status = resp.json().get("compliance_status")
    assert status in ["COMPLIANT", "CIRCUIT_OPEN_HALTED"]


@pytest.mark.tier1
def test_f1_03_active_governance_rules(indigo_client):
    """Verify audit summary enumerates active Consul 2.1 governance rules."""
    resp = indigo_client.get("/api/indigo/audit-summary")
    assert resp.status_code == 200
    rules = resp.json().get("governance_rules_active", [])
    assert len(rules) >= 5
    assert any("Consul 2.1 AI Workload Identity" in r for r in rules)
    assert any("MCP Sidecar" in r for r in rules)


@pytest.mark.tier1
def test_f1_04_crds_feature_directive():
    """Verify consul-crds.yaml references consul-ai feature gate requirement."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    assert crd_path.exists()
    content = crd_path.read_text()
    assert "consul-ai" in content


@pytest.mark.tier1
def test_f1_05_indigo_health(indigo_client):
    """Verify /healthz on indigo-analytics reports healthy status and csl-ag-ana component."""
    resp = indigo_client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "healthy"
    assert data.get("component") == "csl-ag-ana"


# ==============================================================================
# Feature 2: AI Workload Classification CRDs
# ==============================================================================
@pytest.mark.tier1
def test_f2_01_ai_agent_role_annotation():
    """Verify consul-crds.yaml assigns ai-agent role to orchestrator and bookingAgent."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert 'consul.hashicorp.com/ai-role: "ai-agent"' in content
    assert ".Values.orchestrator.name" in content
    assert ".Values.bookingAgent.name" in content


@pytest.mark.tier1
def test_f2_02_mcp_server_role_annotation():
    """Verify consul-crds.yaml assigns mcp-server role to hotel-mcp and flight-mcp."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert 'consul.hashicorp.com/ai-role: "mcp-server"' in content
    assert ".Values.hotelMcp.name" in content
    assert ".Values.flightMcp.name" in content


@pytest.mark.tier1
def test_f2_03_inference_model_role_annotation():
    """Verify consul-crds.yaml assigns inference-model role to llm-backend with capabilities."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert 'consul.hashicorp.com/ai-role: "inference-model"' in content
    assert ".Values.llmBackend.name" in content
    assert "chat,reasoning,tool-use" in content


@pytest.mark.tier1
def test_f2_04_inference_gateway_service_kind():
    """Verify consul-crds.yaml designates travel-igw as service-kind inference-gateway."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert 'service-kind: "inference-gateway"' in content
    assert ".Values.travelIgw.name" in content


@pytest.mark.tier1
def test_f2_05_oauth_client_annotation():
    """Verify consul-crds.yaml configures oauth-client-enabled on agent ServiceDefaults."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert 'consul.hashicorp.com/oauth-client-enabled: "true"' in content


# ==============================================================================
# Feature 5: Docker Compose 14-Service Stack
# ==============================================================================
@pytest.mark.tier1
def test_f5_01_service_count_14():
    """Verify docker-compose.yml defines exactly 14 service containers."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"
    content = compose_path.read_text()
    containers = re.findall(r"container_name:\s*(camp-[a-zA-Z0-9_\-]+)", content)
    assert len(containers) == 14, f"Expected 14 containers in docker-compose.yml, found {len(containers)}: {containers}"


@pytest.mark.tier1
def test_f5_02_bridge_network():
    """Verify docker-compose.yml configures default bridge network camp-travel-mesh-net."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    content = compose_path.read_text()
    assert "camp-travel-mesh-net" in content


@pytest.mark.tier1
def test_f5_03_orchestrator_environment():
    """Verify orchestrator container in docker-compose.yml receives sub-agent and IGW URLs."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    content = compose_path.read_text()
    assert "BOOKING_AGENT_URL=http://booking-agent:8086" in content
    assert "WEATHER_AGENT_URL=http://weather-agent:8087" in content
    assert "TRAVEL_IGW_URL=http://travel-igw:10001" in content


@pytest.mark.tier1
def test_f5_04_gateway_port_mappings():
    """Verify gateway ports 3000, 10000, 10001, 10002 are published in compose."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    content = compose_path.read_text()
    for port in ['"3000:3000"', '"10000:10000"', '"10001:10001"', '"10002:10002"']:
        assert port in content, f"Port mapping {port} must exist in docker-compose.yml"


@pytest.mark.tier1
def test_f5_05_health_endpoints_available(
    weather_mcp_client,
    hotel_mcp_client,
    flight_mcp_client,
    external_mcp_client,
    llm_backend_client,
    otel_client,
    indigo_client,
    frontend_client,
):
    """Verify all application containers implement /healthz with HTTP 200 OK."""
    clients = [
        weather_mcp_client,
        hotel_mcp_client,
        flight_mcp_client,
        external_mcp_client,
        llm_backend_client,
        otel_client,
        indigo_client,
        frontend_client,
    ]
    for c in clients:
        resp = c.get("/healthz")
        assert resp.status_code == 200
        assert resp.json().get("status") == "healthy"


# ==============================================================================
# Feature 6: Helm Chart Packaging & Routes
# ==============================================================================
@pytest.mark.tier1
def test_f6_01_chart_metadata():
    """Verify Chart.yaml defines apiVersion v2, name camp-travel, and appVersion 2.1.0."""
    chart_file = ROOT_DIR / "helm" / "camp-travel" / "Chart.yaml"
    assert chart_file.exists()
    content = chart_file.read_text()
    assert "apiVersion: v2" in content
    assert "name: camp-travel" in content
    assert 'appVersion: "2.1.0"' in content or 'appVersion: 2.1.0' in content


@pytest.mark.tier1
def test_f6_02_openshift_route_template():
    """Verify helm/camp-travel/templates/routes.yaml defines Route resource."""
    route_file = ROOT_DIR / "helm" / "camp-travel" / "templates" / "routes.yaml"
    assert route_file.exists()
    content = route_file.read_text()
    assert "kind: Route" in content
    assert "route.openshift.io/v1" in content


@pytest.mark.tier1
def test_f6_03_service_accounts_defined():
    """Verify templates define dedicated ServiceAccounts matching SPIFFE caller identities."""
    sa_file = ROOT_DIR / "helm" / "camp-travel" / "templates" / "deployments.yaml"
    assert sa_file.exists()
    content = sa_file.read_text()
    assert "serviceAccountName:" in content


@pytest.mark.tier1
def test_f6_04_values_structure():
    """Verify values.yaml configures settings for all mesh services."""
    values_file = ROOT_DIR / "helm" / "camp-travel" / "values.yaml"
    assert values_file.exists()
    content = values_file.read_text()
    assert "experienceUI:" in content
    assert "apiGw:" in content
    assert "orchestrator:" in content
    assert "travelIgw:" in content


@pytest.mark.tier1
def test_f6_05_connect_inject_annotations():
    """Verify Helm templates include consul connect-inject annotations."""
    crd_file = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_file.read_text()
    assert "consul.hashicorp.com" in content
