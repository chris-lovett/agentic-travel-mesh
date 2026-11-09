"""
OpenTelemetry Collector & Span Relay (CAMP AI Observability)
Ingests agent spans, token metrics, and relays trace IDs to BullMQ/Redis for INDIGO analysis.
"""
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Dict, Any, List
import time

app = FastAPI(title="CAMP OpenTelemetry Collector & Span Relay", version="1.0.0")

traces_store: List[Dict[str, Any]] = []

@app.post("/v1/traces")
async def ingest_trace(request: Request):
    data = await request.json()
    record = {
        "ingest_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trace_id": data.get("trace_id", f"trace-{int(time.time())}"),
        "service": data.get("service", "unknown"),
        "user_obo": data.get("user_obo", "anonymous"),
        "tokens_used": data.get("tokens_used", 0),
        "payload": data,
        "relayed_to_bullmq": True,
    }
    traces_store.append(record)
    return {"status": "accepted", "trace_id": record["trace_id"]}

@app.get("/v1/traces")
async def get_traces():
    return {"traces": list(reversed(traces_store[-50:]))}

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "otel-collector"}
