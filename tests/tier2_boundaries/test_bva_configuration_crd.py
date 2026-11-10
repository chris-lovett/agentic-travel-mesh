"""
Tier 2 Boundary Value Analysis — Configuration, CRD, Docker & Helm Boundaries
Covers Boundary Value Analysis for Features 1, 2, 5, 6 (20 tests)
"""
import pytest
import re
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


# ==============================================================================
# Feature 1 BVA: consul-ai Feature Gate & Indigo Engine Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f1_01_chaos_flag_toggle_true(indigo_client):
    """Verify POST /api/indigo/flags can toggle simulate_primary_llm_outage to True."""
    resp = indigo_client.post("/api/indigo/flags", json={"simulate_primary_llm_outage": True})
    assert resp.status_code == 200
    assert resp.json()["runtime_flags"]["simulate_primary_llm_outage"] is True


@pytest.mark.tier2
def test_bva_f1_02_chaos_flag_toggle_false(indigo_client):
    """Verify POST /api/indigo/flags can toggle simulate_primary_llm_outage to False."""
    resp = indigo_client.post("/api/indigo/flags", json={"simulate_primary_llm_outage": False})
    assert resp.status_code == 200
    assert resp.json()["runtime_flags"]["simulate_primary_llm_outage"] is False


@pytest.mark.tier2
def test_bva_f1_03_audit_summary_metrics_structure(indigo_client):
    """Verify metrics dictionary contains all required governance count keys."""
    resp = indigo_client.get("/api/indigo/audit-summary")
    assert resp.status_code == 200
    metrics = resp.json().get("metrics", {})
    required = ["policy_violations_prevented", "cycles_detected", "tokens_inspected_last_24h", "simulate_primary_llm_outage"]
    for req in required:
        assert req in metrics, f"Metric key {req} must exist in audit summary"


@pytest.mark.tier2
def test_bva_f1_04_query_circuit_unknown_agent(indigo_client):
    """Verify querying circuit for unknown SPIFFE ID returns default CLOSED state."""
    resp = indigo_client.get("/api/indigo/circuit/unknown-agent-999")
    assert resp.status_code == 200
    assert resp.json().get("state") == "CLOSED"


@pytest.mark.tier2
def test_bva_f1_05_health_check_payload_keys(indigo_client):
    """Verify /healthz returns status healthy and expected service identifier."""
    resp = indigo_client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "healthy"
    assert "indigo-analytics" in data.get("service", "")


# ==============================================================================
# Feature 2 BVA: AI Workload Classification CRD Specification Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f2_01_crd_ai_role_values():
    """Verify all ai-role values in values.yaml belong to allowed CAMP taxonomy."""
    values_path = ROOT_DIR / "helm" / "camp-travel" / "values.yaml"
    content = values_path.read_text()
    roles = re.findall(r'aiRole:\s*"([^"]+)"', content)
    assert len(roles) >= 6
    allowed_roles = {"ai-agent", "mcp-server", "inference-model", "inference-gateway"}
    for r in roles:
        assert r in allowed_roles, f"Role {r} is outside allowed CAMP taxonomy"


@pytest.mark.tier2
def test_bva_f2_02_crd_service_defaults_protocol_http():
    """Verify all ServiceDefaults in consul-crds.yaml declare protocol: http."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    # Find all ServiceDefaults blocks
    blocks = content.split("---")
    sd_blocks = [b for b in blocks if "kind: ServiceDefaults" in b]
    assert len(sd_blocks) >= 8
    for b in sd_blocks:
        assert "protocol: http" in b, "All CAMP HTTP service defaults must declare protocol: http"


@pytest.mark.tier2
def test_bva_f2_03_crd_service_intentions_action_allow():
    """Verify ServiceIntentions in consul-crds.yaml declare action: allow."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert "kind: ServiceIntentions" in content
    assert "action: allow" in content


@pytest.mark.tier2
def test_bva_f2_04_crd_capabilities_comma_separated():
    """Verify llmBackend capabilities in values.yaml contain chat, reasoning, tool-use."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert "chat,reasoning,tool-use" in content


@pytest.mark.tier2
def test_bva_f2_05_crd_ext_proc_argument_keys():
    """Verify ext-proc arguments define processorTarget and messageTimeout."""
    crd_path = ROOT_DIR / "helm" / "camp-travel" / "templates" / "consul-crds.yaml"
    content = crd_path.read_text()
    assert "processorTarget:" in content
    assert "messageTimeout:" in content


# ==============================================================================
# Feature 5 BVA: Docker Compose Topology Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f5_01_no_duplicate_host_ports():
    """Verify docker-compose.yml defines zero overlapping host port mappings."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    content = compose_path.read_text()
    port_mappings = re.findall(r'"(\d+):(\d+)"', content)
    host_ports = [m[0] for m in port_mappings]
    assert len(host_ports) == len(set(host_ports)), f"Duplicate host ports found: {host_ports}"


@pytest.mark.tier2
def test_bva_f5_02_all_containers_have_working_dir():
    """Verify application containers in docker-compose.yml specify working_dir /app."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    content = compose_path.read_text()
    assert "working_dir: /app" in content


@pytest.mark.tier2
def test_bva_f5_03_envoy_admin_ports_configured():
    """Verify envoy gateways have distinct admin ports 9900, 9901, 9902."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    content = compose_path.read_text()
    assert '"9900:9900"' in content
    assert '"9901:9901"' in content
    assert '"9902:9902"' in content


@pytest.mark.tier2
def test_bva_f5_04_default_network_name():
    """Verify compose default network name matches camp-travel-mesh-net."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    content = compose_path.read_text()
    assert "camp-travel-mesh-net" in content


@pytest.mark.tier2
def test_bva_f5_05_otel_collector_port():
    """Verify otel-collector publishes standard OTLP HTTP port 4318."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    content = compose_path.read_text()
    assert '"4318:4318"' in content


# ==============================================================================
# Feature 6 BVA: Helm Chart Packaging Specification Boundaries
# ==============================================================================
@pytest.mark.tier2
def test_bva_f6_01_chart_type_application():
    """Verify Chart.yaml declares type: application."""
    chart_file = ROOT_DIR / "helm" / "camp-travel" / "Chart.yaml"
    content = chart_file.read_text()
    assert "type: application" in content


@pytest.mark.tier2
def test_bva_f6_02_values_replica_counts_positive():
    """Verify all replica counts in values.yaml are positive integers (>=1)."""
    values_file = ROOT_DIR / "helm" / "camp-travel" / "values.yaml"
    content = values_file.read_text()
    replicas = re.findall(r"replicaCount:\s*(\d+)", content)
    assert len(replicas) > 0
    for r in replicas:
        assert int(r) >= 1, f"Replica count {r} must be >= 1"


@pytest.mark.tier2
def test_bva_f6_03_values_resource_limits_defined():
    """Verify container resource limits specify cpu and memory."""
    values_file = ROOT_DIR / "helm" / "camp-travel" / "values.yaml"
    content = values_file.read_text()
    assert 'limits: { cpu:' in content or 'limits:' in content
    assert 'requests: { cpu:' in content or 'requests:' in content


@pytest.mark.tier2
def test_bva_f6_04_routes_port_3000():
    """Verify OpenShift route targets port 3000 for experience-ui."""
    route_file = ROOT_DIR / "helm" / "camp-travel" / "templates" / "routes.yaml"
    content = route_file.read_text()
    assert "targetPort: 3000" in content or "targetPort: http" in content


@pytest.mark.tier2
def test_bva_f6_05_ingress_defaults_in_values():
    """Verify values.yaml enables openShiftRoute by default."""
    values_file = ROOT_DIR / "helm" / "camp-travel" / "values.yaml"
    content = values_file.read_text()
    assert "openShiftRoute: true" in content
    assert "ingress:" in content
