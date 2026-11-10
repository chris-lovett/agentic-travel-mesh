"""
Foundation Model Backend & AI Inference Gateway External Processor (csl-inf-rt / csl-ig-pro)
Accessed via the travel-igw Envoy AI Gateway with Vault credential injection.
Demonstrates:
1. OpenAI-compatible inference interface (/v1/chat/completions)
2. Capability routing & Priority-based provider failover (Priority 1: meta-llama/llama-3-70b-instruct -> Priority 2: claude-3-5-sonnet)
3. Protocol translation (OpenAI chat.completions -> Anthropic /v1/messages)
4. Zero-code auto-instrumentation (emits OTel GenAI spans directly from the gateway processor to csl-nod-rly)
"""
from fastapi import FastAPI, Request, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import httpx
import os
import time
import math

app = FastAPI(title="CAMP Foundation Model & AI Inference Gateway Processor (csl-inf-rt)", version="2.1.0")

OTEL_COLLECTOR_URL = os.getenv("OTEL_COLLECTOR_URL", "http://otel-collector:4318")
INDIGO_ANALYTICS_URL = os.getenv("INDIGO_ANALYTICS_URL", "http://indigo-analytics:8089")

# Local override toggle for primary model outage simulation
local_outage_state = {"simulate_primary_llm_outage": False}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    capabilities: Optional[List[str]] = ["chat", "reasoning"]


token_usage_stats = {
    "total_calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "total_cost_usd": 0.0,
    "failovers_executed": 0,
}


def count_tokens(text: str) -> int:
    if not text:
        return 0
    words = text.split()
    chars = len(text)
    return max(len(words), math.ceil(chars / 3.7))


async def is_primary_outage_active(request: Request) -> bool:
    if request.headers.get("x-simulate-llm-outage", "").lower() == "true":
        return True
    if local_outage_state["simulate_primary_llm_outage"]:
        return True
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{INDIGO_ANALYTICS_URL}/api/indigo/flags")
            if resp.status_code == 200:
                return bool(resp.json().get("simulate_primary_llm_outage", False))
    except Exception:
        pass
    return False


@app.post("/v1/chat/completions")
@app.post("/openai/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    """OpenAI-compatible endpoint governed by Consul AI Inference Gateway (csl-inf-rt)"""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid injected provider API key from travel-igw",
        )

    user_prompt = "\n".join([m.content for m in req.messages if m.role == "user"])
    prompt_tokens = count_tokens(user_prompt)

    destination = "the destination"
    for line in user_prompt.splitlines():
        if "to " in line.lower() or "destination:" in line.lower() or "route:" in line.lower():
            parts = line.split(":")[-1].strip()
            if parts:
                destination = parts

    outage_active = await is_primary_outage_active(request)
    requested_model = req.model

    if outage_active:
        # Priority 1 upstream (meta-llama/llama-3-70b-instruct) failed -> Failover to Priority 2 (claude-3-5-sonnet)
        routed_model = "claude-3-5-sonnet (Anthropic Priority-2 Failover)"
        protocol_translation = "OpenAI /v1/chat/completions -> Anthropic /v1/messages (csl-inf-rt)"
        vault_secret_ref = "vault:secret/data/ai/anthropic#api_key_ant_8820"
        token_usage_stats["failovers_executed"] += 1
        simulated_reply = (
            f"[csl-inf-rt Priority-2 Failover: claude-3-5-sonnet] Primary upstream '{requested_model}' returned 503/429. "
            f"Consul AI Inference Gateway automatically translated OpenAI request to Anthropic /v1/messages via Terminating Gateway mTLS. "
            f"Synthesized compliant itinerary for {destination}."
        )
    else:
        routed_model = requested_model
        protocol_translation = "OpenAI /v1/chat/completions -> Native Upstream (csl-inf-rt)"
        vault_secret_ref = "vault:secret/data/ai/llm#api_key_sk_99201"
        simulated_reply = (
            f"[travel-igw AI Gateway] Completed multi-agent reasoning using '{routed_model}'. "
            f"Consolidated flight, lodging, and ground logistics for {destination}. "
            f"Full itinerary is compliant with corporate travel policy and ready for executive authorization."
        )

    completion_tokens = count_tokens(simulated_reply)
    total_tokens = prompt_tokens + completion_tokens
    call_cost = round(total_tokens * (0.000008 if outage_active else 0.000005), 6)

    token_usage_stats["total_calls"] += 1
    token_usage_stats["prompt_tokens"] += prompt_tokens
    token_usage_stats["completion_tokens"] += completion_tokens
    token_usage_stats["total_tokens"] += total_tokens
    token_usage_stats["total_cost_usd"] = round(token_usage_stats["total_cost_usd"] + call_cost, 6)

    trace_id = request.headers.get("x-trace-id", f"trace-igw-{int(time.time()*1000)}")
    obo_user = request.headers.get("x-obo-user-id", "anonymous")
    caller_spiffe = request.headers.get(
        "x-caller-spiffe-id",
        "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator",
    )

    # Zero-Code Auto-Instrumentation: csl-inf-rt emits OpenTelemetry GenAI span directly to csl-nod-rly
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            await client.post(
                f"{OTEL_COLLECTOR_URL}/v1/traces",
                json={
                    "trace_id": trace_id,
                    "span_type": "llm_inference",
                    "span_name": "csl-inf-rt.chat.completions",
                    "instrumented_by": "csl-inf-rt (AI Inference Gateway Zero-Code ext-proc)",
                    "service": "travel-igw",
                    "agent_spiffe_id": caller_spiffe,
                    "user_obo": obo_user,
                    "model": requested_model,
                    "response_model": routed_model,
                    "failover_triggered": outage_active,
                    "protocol_translation": protocol_translation,
                    "tokens_used": total_tokens,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
            )
    except Exception:
        pass

    return {
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "model": routed_model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": simulated_reply,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "gateway_metadata": {
            "authenticated_by_vault": True,
            "vault_secret_ref": vault_secret_ref,
            "gateway_tier": request.headers.get("x-consul-mesh-tier", "travel-igw-2.1 (csl-inf-rt)"),
            "tenant_obo_user": obo_user,
            "estimated_cost_usd": call_cost,
            "failover_triggered": outage_active,
            "requested_model": requested_model,
            "routed_model": routed_model,
            "protocol_translation": protocol_translation,
            "zero_code_traced": True,
        },
    }


@app.post("/v1/messages")
@app.post("/anthropic/v1/messages")
async def anthropic_messages(request: Request):
    """Anthropic Claude native endpoint"""
    body = await request.json()
    model = body.get("model", "claude-3-5-sonnet")
    content = body.get("messages", [{}])[0].get("content", "")
    inp_tok = count_tokens(content)
    out_text = f"[Anthropic via travel-igw] Synthesized message response with {model}."
    out_tok = count_tokens(out_text)
    return {
        "id": f"msg-{int(time.time()*1000)}",
        "type": "message",
        "model": model,
        "content": [{"type": "text", "text": out_text}],
        "usage": {"input_tokens": inp_tok, "output_tokens": out_tok},
    }


@app.post("/api/llm/simulate-outage")
async def toggle_outage(body: Dict[str, Any]):
    local_outage_state["simulate_primary_llm_outage"] = bool(body.get("simulate_primary_llm_outage", False))
    return {"status": "updated", **local_outage_state}


@app.get("/metrics/tokens")
async def get_metrics():
    return token_usage_stats


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "llm-backend", "component": "csl-inf-rt"}
