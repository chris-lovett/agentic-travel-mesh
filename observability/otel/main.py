"""
OpenTelemetry Collector & Span Relay (csl-nod-rly / CAMP AI Observability)
Receives zero-code auto-instrumented spans emitted by protocol-aware mesh proxies:
- AI Inference Gateway external processor (csl-inf-rt / csl-ig-pro)
- Model Context Protocol sidecar external processor (csl-mcp-sc)
- Identity Plane OBO processors
Queues trace evidence via BullMQ/Redis semantics to Agentic Analytics (csl-ag-ana) for cycle detection,
and forwards OTLP spans to Grafana Tempo.
"""
from fastapi import FastAPI, Request
from typing import Dict, Any, List
import httpx
import os
import time
import uuid

app = FastAPI(title="CAMP OpenTelemetry Collector & Span Relay (csl-nod-rly)", version="2.1.0")

INDIGO_ANALYTICS_URL = os.getenv("INDIGO_ANALYTICS_URL", "http://indigo-analytics:8089")
TEMPO_OTLP_URL = os.getenv("TEMPO_OTLP_URL", "http://tempo:4318/v1/traces")

traces_store: List[Dict[str, Any]] = []
bullmq_relay_queue: List[Dict[str, Any]] = []


@app.post("/v1/traces")
async def ingest_trace(request: Request):
    data = await request.json()
    trace_id = data.get("trace_id", f"trace-{int(time.time()*1000)}")
    span_type = data.get("span_type", "llm_inference")

    prompt_tokens = data.get("prompt_tokens", int(data.get("tokens_used", 0) * 0.6))
    completion_tokens = data.get("completion_tokens", int(data.get("tokens_used", 0) * 0.4))
    total_tokens = prompt_tokens + completion_tokens
    cost_usd = round(total_tokens * 0.000005, 5)

    service_name = data.get("service", "travel-orchestrator")
    agent_spiffe = data.get(
        "agent_spiffe_id",
        f"spiffe://cluster.local/ns/camp-travel/sa/{service_name}",
    )

    record = {
        "ingest_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trace_id": trace_id,
        "span_type": span_type,
        "service": service_name,
        "instrumented_by": data.get("instrumented_by", "consul-envoy-ext-proc (zero-code)"),
        "user_obo": data.get("user_obo", "anonymous"),
        "obo_scopes": data.get("obo_scopes", []),
        "otel_gen_ai_attributes": {
            "gen_ai.system": data.get("gen_ai_system", "consul-ai-gw (csl-inf-rt)"),
            "gen_ai.request.model": data.get("model", "meta-llama/llama-3-70b-instruct"),
            "gen_ai.response.model": data.get("response_model", data.get("model", "meta-llama/llama-3-70b-instruct")),
            "gen_ai.usage.prompt_tokens": prompt_tokens,
            "gen_ai.usage.completion_tokens": completion_tokens,
            "gen_ai.usage.total_tokens": total_tokens,
            "gen_ai.usage.cost_usd": cost_usd,
            "mcp.tool.name": data.get("tool_name"),
            "mcp.tool.server": data.get("mcp_server"),
            "spiffe.id": agent_spiffe,
            "consul.ai_gateway": "travel-igw",
            "consul.failover_triggered": data.get("failover_triggered", False),
        },
        "tokens_used": total_tokens,
        "payload": data,
        "relayed_to_indigo": True,
    }
    traces_store.append(record)

    # Queue trace trigger in Span Relay (csl-nod-rly -> BullMQ -> csl-ag-ana)
    queue_job = {
        "job_id": f"bullmq-{uuid.uuid4().hex[:8]}",
        "queue": "consul-ai-cycle-detection",
        "trace_id": trace_id,
        "span_type": span_type,
        "agent_spiffe_id": agent_spiffe,
        "tool_name": data.get("tool_name"),
        "timestamp": record["ingest_timestamp"],
    }
    bullmq_relay_queue.append(queue_job)

    # Asynchronously forward evidence to Agentic Analytics (csl-ag-ana)
    analytics_result = None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            ana_resp = await client.post(
                f"{INDIGO_ANALYTICS_URL}/api/indigo/ingest-span",
                json={
                    "trace_id": trace_id,
                    "span_type": span_type,
                    "agent_spiffe_id": agent_spiffe,
                    "service": service_name,
                    "mcp_server": data.get("mcp_server"),
                    "tool_name": data.get("tool_name"),
                    "tool_arguments": data.get("tool_arguments"),
                    "tool_result": data.get("tool_result"),
                    "tokens_used": total_tokens,
                    "status": data.get("status", "OK"),
                    "detail": data.get("detail"),
                },
            )
            analytics_result = ana_resp.json()
    except Exception:
        pass

    # Forward standard OTLP span hierarchy into Grafana Tempo
    try:
        now_ns = int(time.time() * 1e9)
        raw_tid = str(trace_id).replace("trace-camp-", "").replace("trace-", "")
        raw_tid = (raw_tid + uuid.uuid4().hex)[:32]
        span_id = uuid.uuid4().hex[:16]
        otlp_spans = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": service_name}},
                            {"key": "consul.mesh.version", "value": {"stringValue": "2.1.0-enterprise"}},
                            {"key": "consul.ai.instrumented_by", "value": {"stringValue": record["instrumented_by"]}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "consul.agentic.auto_instrumentation"},
                            "spans": [
                                {
                                    "traceId": raw_tid,
                                    "spanId": span_id,
                                    "name": data.get("span_name", f"{service_name}.{span_type}"),
                                    "kind": 3,
                                    "startTimeUnixNano": str(now_ns - 250000000),
                                    "endTimeUnixNano": str(now_ns),
                                    "attributes": [
                                        {"key": "spiffe.id", "value": {"stringValue": agent_spiffe}},
                                        {"key": "user.obo", "value": {"stringValue": str(record["user_obo"])}},
                                        {"key": "gen_ai.request.model", "value": {"stringValue": str(record["otel_gen_ai_attributes"]["gen_ai.request.model"])}},
                                        {"key": "gen_ai.response.model", "value": {"stringValue": str(record["otel_gen_ai_attributes"]["gen_ai.response.model"])}},
                                        {"key": "gen_ai.usage.total_tokens", "value": {"intValue": total_tokens}},
                                        {"key": "mcp.tool.name", "value": {"stringValue": str(data.get("tool_name") or "none")}},
                                    ],
                                    "status": {"code": 1},
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        async with httpx.AsyncClient(timeout=1.5) as client:
            await client.post(TEMPO_OTLP_URL, json=otlp_spans)
    except Exception:
        pass

    return {
        "status": "accepted",
        "trace_id": record["trace_id"],
        "attributes": record["otel_gen_ai_attributes"],
        "analytics": analytics_result,
    }


@app.get("/v1/traces")
async def get_traces():
    return {
        "traces": list(reversed(traces_store[-50:])),
        "bullmq_queue_depth": len(bullmq_relay_queue),
        "recent_jobs": list(reversed(bullmq_relay_queue[-15:])),
    }


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "otel-collector", "component": "csl-nod-rly"}
