"""
Tier 4 Real-World Interactive User Journey — Scenario 2: Upstream Outage & Failover (5 Acts)
Scenario: Upstream Crisis & Dynamic Failover across Consul AI Inference Gateway (travel-igw)
- Act I: Nominal Traveler Request Pre-Check
- Act II: Primary Model Provider Outage Simulation
- Act III: Automatic Priority-Based Failover to Anthropic Claude 3.5 Sonnet
- Act IV: Protocol Translation & HashiCorp Vault Secret Swapping
- Act V: Post-Crisis Recovery & Trace Audit Verification
"""
import pytest
import time


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario2_full_5act_upstream_outage(frontend_client, travel_igw_client):
    """
    Complete 5-Act user journey simulating upstream provider crisis and zero-downtime failover.
    Validates Consul AI Inference Gateway dynamic routing, protocol adaptation, and Vault integration.
    """
    # --------------------------------------------------------------------------
    # ACT I: Nominal Traveler Request Pre-Check
    # --------------------------------------------------------------------------
    nominal_resp = frontend_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "user_name": "Alex Mercer",
            "origin": "JFK",
            "destination": "London",
            "duration_days": 5,
            "budget_usd": 4000.0,
            "trip_purpose": "Executive Briefing",
            "scenario_mode": "normal",
        },
    )
    assert nominal_resp.status_code == 200
    nominal_data = nominal_resp.json()
    assert nominal_data.get("ai_telemetry", {}).get("failover_triggered") is False

    # --------------------------------------------------------------------------
    # ACT II: Primary Model Provider Outage Simulation
    # --------------------------------------------------------------------------
    toggle_on = frontend_client.post(
        "/api/governance/toggle-llm-outage",
        json={"simulate_primary_llm_outage": True},
    )
    assert toggle_on.status_code == 200
    assert toggle_on.json().get("runtime_flags", {}).get("simulate_primary_llm_outage") is True

    # --------------------------------------------------------------------------
    # ACT III: Automatic Priority-Based Failover to Claude 3.5 Sonnet
    # --------------------------------------------------------------------------
    failover_resp = frontend_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "user_name": "Alex Mercer",
            "origin": "JFK",
            "destination": "London",
            "duration_days": 5,
            "budget_usd": 4000.0,
            "trip_purpose": "Executive Briefing",
            "scenario_mode": "act1_llm_failover",
        },
    )
    assert failover_resp.status_code == 200
    failover_data = failover_resp.json()

    ai_meta = failover_data.get("ai_telemetry", {})
    assert ai_meta.get("failover_triggered") is True, "AI Gateway failover must be triggered"
    assert "claude-3-5-sonnet" in ai_meta.get("model", "") or "anthropic" in ai_meta.get("model", "")

    # --------------------------------------------------------------------------
    # ACT IV: Protocol Translation & HashiCorp Vault Secret Swapping
    # --------------------------------------------------------------------------
    assert "OpenAI /v1/chat/completions -> Anthropic /v1/messages" in ai_meta.get("protocol_translation", "")
    assert "auth_provider" in ai_meta
    assert "HashiCorp Vault" in ai_meta["auth_provider"]
    assert failover_data.get("executive_summary") is not None
    assert len(failover_data["executive_summary"]) > 10

    # --------------------------------------------------------------------------
    # ACT V: Post-Crisis Recovery & Trace Audit Verification
    # --------------------------------------------------------------------------
    toggle_off = frontend_client.post(
        "/api/governance/toggle-llm-outage",
        json={"simulate_primary_llm_outage": False},
    )
    assert toggle_off.status_code == 200
    assert toggle_off.json().get("runtime_flags", {}).get("simulate_primary_llm_outage") is False

    audit_resp = frontend_client.get("/api/travel/audit-stream")
    assert audit_resp.status_code == 200
    events = audit_resp.json().get("audit_events", [])
    event_names = [e.get("event") for e in events]
    assert "AI_GW_FAILOVER_CLAUDE_SONNET" in event_names
    assert "LLM_OUTAGE_SIM_OFF" in event_names


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario2_act2_outage_flag_toggle(frontend_client):
    """Act II In-depth: Verifies runtime outage flag toggle modifies state across services."""
    resp = frontend_client.post(
        "/api/governance/toggle-llm-outage",
        json={"simulate_primary_llm_outage": True},
    )
    assert resp.status_code == 200
    assert resp.json()["runtime_flags"]["simulate_primary_llm_outage"] is True

    # Restore
    resp2 = frontend_client.post(
        "/api/governance/toggle-llm-outage",
        json={"simulate_primary_llm_outage": False},
    )
    assert resp2.status_code == 200
    assert resp2.json()["runtime_flags"]["simulate_primary_llm_outage"] is False


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario2_act3_direct_inference_failover(travel_igw_client):
    """Act III In-depth: travel-igw directly intercepts simulated outage and fails over."""
    resp = travel_igw_client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer api_key_sk_99201",
            "x-simulate-llm-outage": "true",
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator",
        },
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Please synthesize itinerary."}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    gw = data.get("gateway_metadata", {})
    assert gw.get("failover_triggered") is True
    assert "claude-3-5-sonnet" in gw.get("routed_model", "")


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario2_act4_anthropic_vault_token_injection(travel_igw_client):
    """Act IV In-depth: Failover injects Anthropic bearer token from Vault."""
    resp = travel_igw_client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer api_key_sk_99201",
            "x-simulate-llm-outage": "true",
            "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator",
        },
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "Summarize policy."}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    gw = data.get("gateway_metadata", {})
    assert "vault_secret_ref" in gw
    assert "vault:secret/data/ai/anthropic#api_key" in gw["vault_secret_ref"]


@pytest.mark.tier4
@pytest.mark.governance
def test_scenario2_act5_audit_stream_records_failover_event(frontend_client):
    """Act V In-depth: Frontend audit stream records failover event with timestamp."""
    frontend_client.post(
        "/api/travel/plan",
        json={
            "user_id": "traveler-101",
            "user_name": "Alex Mercer",
            "scenario_mode": "act1_llm_failover",
        },
    )
    audit_resp = frontend_client.get("/api/travel/audit-stream")
    assert audit_resp.status_code == 200
    events = audit_resp.json().get("audit_events", [])
    found = any(e.get("event") == "AI_GW_FAILOVER_CLAUDE_SONNET" for e in events)
    assert found is True
