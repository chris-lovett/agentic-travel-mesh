"""
Consul Agentic Analytics Engine (csl-ag-ana / INDIGO Governance)
Asynchronously analyzes zero-code proxy trace spans relayed by csl-nod-rly (BullMQ/Redis pipeline)
for Cycle Detection (repetitive tool calls with identical arguments and unchanged results),
manages agent-scoped circuit breakers, and tracks MCP Sidecar & Identity Plane policy decisions.
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import hashlib
import json
import time

app = FastAPI(title="Consul Agentic Analytics (csl-ag-ana / INDIGO)", version="2.1.0")

# Agent-scoped circuit breaker state managed by Consul Behavior Policy
# Key: SPIFFE ID (e.g. "spiffe://cluster.local/ns/camp-travel/sa/booking-agent")
agent_circuits: Dict[str, Dict[str, Any]] = {
    "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator": {
        "state": "CLOSED",
        "reason": "Normal operation",
        "repetition_count": 0,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    },
    "spiffe://cluster.local/ns/camp-travel/sa/booking-agent": {
        "state": "CLOSED",
        "reason": "Normal operation",
        "repetition_count": 0,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    },
    "spiffe://cluster.local/ns/camp-travel/sa/weather-agent": {
        "state": "CLOSED",
        "reason": "Normal operation",
        "repetition_count": 0,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    },
}

# Sliding window of tool call fingerprints per (trace_id / agent_spiffe_id)
# Fingerprint = sha256(agent_spiffe_id + tool_name + canonical_args + canonical_result)
fingerprint_counters: Dict[str, int] = {}
cycle_events: List[Dict[str, Any]] = []
governance_events: List[Dict[str, Any]] = []

# Runtime governance & fault-injection state for interactive demo acts
runtime_flags: Dict[str, Any] = {
    "simulate_primary_llm_outage": False,
    "cycle_threshold": 3,
    "policy_violations_prevented": 0,
    "cycles_detected": 0,
    "obo_exchanges_verified": 0,
    "hitl_gates_enforced": 0,
    "tokens_inspected_last_24h": 14200,
}


class SpanEvidence(BaseModel):
    trace_id: str
    span_type: str = "mcp_tool_call"  # "mcp_tool_call" | "llm_inference" | "obo_exchange" | "policy_violation"
    agent_spiffe_id: str = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"
    service: str = "booking-agent"
    mcp_server: Optional[str] = None
    tool_name: Optional[str] = None
    tool_arguments: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    tokens_used: int = 0
    status: str = "OK"
    detail: Optional[str] = None


class CircuitResetRequest(BaseModel):
    agent_spiffe_id: Optional[str] = None


class ChaosFlagRequest(BaseModel):
    simulate_primary_llm_outage: bool


def compute_cycle_fingerprint(agent_spiffe: str, tool_name: str, args: Any, result: Any) -> str:
    canonical = json.dumps(
        {
            "agent": agent_spiffe,
            "tool": tool_name,
            "args": args or {},
            "result": result or {},
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@app.post("/api/indigo/ingest-span")
async def ingest_span_evidence(evidence: SpanEvidence):
    """
    Consumes trace evidence queued by csl-nod-rly (Span Relay).
    Evaluates repetitive (tool_name, arguments, result) tuples for Cycle Detection.
    """
    runtime_flags["tokens_inspected_last_24h"] += evidence.tokens_used

    if evidence.span_type == "policy_violation":
        runtime_flags["policy_violations_prevented"] += 1
        governance_events.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "trace_id": evidence.trace_id,
            "type": "POLICY_VIOLATION_BLOCKED",
            "agent": evidence.agent_spiffe_id,
            "tool": evidence.tool_name,
            "detail": evidence.detail or "Blocked by Consul Agentic Runtime Fabric proxy policy",
        })
        return {"status": "recorded", "circuit_state": "CLOSED"}

    if evidence.span_type == "mcp_tool_call" and evidence.tool_name:
        fp = compute_cycle_fingerprint(
            evidence.agent_spiffe_id,
            evidence.tool_name,
            evidence.tool_arguments,
            evidence.tool_result,
        )
        key = f"{evidence.agent_spiffe_id}:{fp}"
        fingerprint_counters[key] = fingerprint_counters.get(key, 0) + 1
        count = fingerprint_counters[key]

        circuit_entry = agent_circuits.setdefault(
            evidence.agent_spiffe_id,
            {"state": "CLOSED", "reason": "Normal operation", "repetition_count": 0, "updated_at": ""},
        )
        circuit_entry["repetition_count"] = count
        circuit_entry["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        if count >= runtime_flags["cycle_threshold"] and circuit_entry["state"] != "OPEN":
            circuit_entry["state"] = "OPEN"
            circuit_entry["reason"] = (
                f"Cycle detected by csl-ag-ana: {count} identical calls to "
                f"'{evidence.tool_name}' with unchanged arguments & result (fingerprint={fp})"
            )
            runtime_flags["cycles_detected"] += 1
            runtime_flags["policy_violations_prevented"] += 1
            cycle_event = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "trace_id": evidence.trace_id,
                "agent_spiffe_id": evidence.agent_spiffe_id,
                "tool_name": evidence.tool_name,
                "arguments": evidence.tool_arguments,
                "repetitions": count,
                "fingerprint": fp,
                "action_taken": "AGENT_CIRCUIT_OPENED",
            }
            cycle_events.append(cycle_event)
            governance_events.append({
                "timestamp": cycle_event["timestamp"],
                "trace_id": evidence.trace_id,
                "type": "CYCLE_DETECTED_CIRCUIT_OPEN",
                "agent": evidence.agent_spiffe_id,
                "tool": evidence.tool_name,
                "detail": circuit_entry["reason"],
            })

        return {
            "status": "analyzed",
            "fingerprint": fp,
            "repetition_count": count,
            "circuit_state": circuit_entry["state"],
            "reason": circuit_entry["reason"],
        }

    return {"status": "analyzed", "circuit_state": "CLOSED"}


@app.get("/api/indigo/circuit/{service_name}")
async def get_circuit_state(service_name: str):
    spiffe_id = (
        service_name
        if service_name.startswith("spiffe://")
        else f"spiffe://cluster.local/ns/camp-travel/sa/{service_name}"
    )
    entry = agent_circuits.get(
        spiffe_id,
        {"state": "CLOSED", "reason": "Normal operation", "repetition_count": 0},
    )
    return {"agent_spiffe_id": spiffe_id, **entry}


@app.post("/api/indigo/circuit/reset")
async def reset_circuits(req: Optional[CircuitResetRequest] = None):
    """Resets agent-scoped circuit breakers back to CLOSED."""
    fingerprint_counters.clear()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    for spiffe_id in list(agent_circuits.keys()):
        if not req or not req.agent_spiffe_id or req.agent_spiffe_id in spiffe_id:
            agent_circuits[spiffe_id] = {
                "state": "CLOSED",
                "reason": "Circuit reset by operator via Consul Behavior Policy",
                "repetition_count": 0,
                "updated_at": now_str,
            }
    governance_events.append({
        "timestamp": now_str,
        "trace_id": f"op-reset-{int(time.time())}",
        "type": "CIRCUIT_BREAKER_RESET",
        "agent": req.agent_spiffe_id if (req and req.agent_spiffe_id) else "all-agents",
        "tool": "consul-behavior-policy",
        "detail": "Operator reset agent-scoped circuit breaker to CLOSED",
    })
    return {"status": "reset", "circuits": agent_circuits}


@app.post("/api/indigo/flags")
async def set_chaos_flags(req: ChaosFlagRequest):
    runtime_flags["simulate_primary_llm_outage"] = req.simulate_primary_llm_outage
    governance_events.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trace_id": f"flag-{int(time.time())}",
        "type": "PRIMARY_LLM_OUTAGE_SIMULATION",
        "agent": "spiffe://cluster.local/ns/camp-travel/sa/travel-igw",
        "tool": "inference-gateway",
        "detail": f"Primary LLM outage simulation set to {req.simulate_primary_llm_outage}",
    })
    return {"status": "updated", "runtime_flags": runtime_flags}


@app.get("/api/indigo/flags")
async def get_chaos_flags():
    return runtime_flags


@app.get("/api/analytics/summary")
@app.get("/api/indigo/audit-summary")
async def audit_summary():
    any_open = any(c["state"] == "OPEN" for c in agent_circuits.values())
    return {
        "engine": "INDIGO-AI-Governance (Consul csl-ag-ana 2.1)",
        "feature_gate": "consul-ai=enabled",
        "compliance_status": "CIRCUIT_OPEN_HALTED" if any_open else "COMPLIANT",
        "metrics": {
            "policy_violations_prevented": runtime_flags["policy_violations_prevented"],
            "cycles_detected": runtime_flags["cycles_detected"],
            "tokens_inspected_last_24h": runtime_flags["tokens_inspected_last_24h"],
            "average_agent_mesh_latency_ms": 38.5,
            "vault_egress_auth_success_rate": "100%",
            "simulate_primary_llm_outage": runtime_flags["simulate_primary_llm_outage"],
        },
        "agent_circuits": agent_circuits,
        "recent_cycles": list(reversed(cycle_events[-10:])),
        "governance_events": list(reversed(governance_events[-20:])),
        "governance_rules_active": [
            "Consul 2.1 AI Workload Identity (ai-agent, mcp-server, inference-model)",
            "MCP Sidecar (csl-mcp-sc) Per-Tool JSON-RPC Policy & Cryptographic HITL Gate",
            "Identity Plane Hop-by-Hop OBO Token Exchange & Scope Narrowing",
            "AI Inference Gateway (csl-inf-rt) Capability Routing & Multi-Provider Failover",
            "Agentic Analytics (csl-ag-ana) Asynchronous Cycle Detection & Circuit Breaker",
        ],
    }


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "indigo-analytics", "component": "csl-ag-ana"}
