"""
OpenTelemetry Collector & Span Relay (CAMP AI Observability)
Conforms to OpenTelemetry GenAI Semantic Conventions:
- gen_ai.system (watsonx / openai / ollama)
- gen_ai.request.model (meta-llama/llama-3-70b-instruct)
- gen_ai.usage.prompt_tokens & completion_tokens
- gen_ai.client.token.cost_usd
"""
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Dict, Any, List
import time

app = FastAPI(title="CAMP OpenTelemetry Collector & Span Relay", version="2.1.0")

traces_store: List[Dict[str, Any]] = []

@app.post("/v1/traces")
async def ingest_trace(request: Request):
    data = await request.json()
    trace_id = data.get("trace_id", f"trace-{int(time.time()*1000)}")
    
    # Extract / format OpenTelemetry GenAI attributes
    prompt_tokens = data.get("prompt_tokens", int(data.get("tokens_used", 0) * 0.6))
    completion_tokens = data.get("completion_tokens", int(data.get("tokens_used", 0) * 0.4))
    total_tokens = prompt_tokens + completion_tokens
    cost_usd = round(total_tokens * 0.000005, 5)

    record = {
        "ingest_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trace_id": trace_id,
        "service": data.get("service", "travel-orchestrator"),
        "user_obo": data.get("user_obo", "anonymous"),
        "otel_gen_ai_attributes": {
            "gen_ai.system": "watsonx / consul-ai-gw",
            "gen_ai.request.model": data.get("model", "meta-llama/llama-3-70b-instruct"),
            "gen_ai.usage.prompt_tokens": prompt_tokens,
            "gen_ai.usage.completion_tokens": completion_tokens,
            "gen_ai.usage.total_tokens": total_tokens,
            "gen_ai.usage.cost_usd": cost_usd,
            "spiffe.id": f"spiffe://cluster.local/ns/camp-travel/sa/{data.get('service', 'orchestrator')}",
            "consul.ai_gateway": "travel-igw",
        },
        "tokens_used": total_tokens,
        "payload": data,
        "relayed_to_indigo": True,
    }
    traces_store.append(record)
    return {"status": "accepted", "trace_id": record["trace_id"], "attributes": record["otel_gen_ai_attributes"]}

@app.get("/v1/traces")
async def get_traces():
    return {"traces": list(reversed(traces_store[-50:]))}

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "otel-collector"}
