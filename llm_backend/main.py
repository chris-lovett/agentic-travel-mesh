"""
Foundation Model Backend (Ollama / OpenAI / Anthropic Mock)
Accessed exclusively via the travel-igw Envoy AI Gateway with Vault credential injection.
"""
from fastapi import FastAPI, Request, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import time

app = FastAPI(title="CAMP Foundation Model Service (travel-igw Backend)", version="2.1.0")

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7

# Token usage telemetry ledger
token_usage_stats = {"total_calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

@app.post("/v1/chat/completions")
@app.post("/openai/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    """OpenAI / Ollama Chat Completion Endpoint"""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid injected provider API key from travel-igw",
        )

    user_prompt = "\n".join([m.content for m in req.messages if m.role == "user"])
    p_tokens = max(len(user_prompt.split()) * 2, 10)
    c_tokens = 35

    token_usage_stats["total_calls"] += 1
    token_usage_stats["prompt_tokens"] += p_tokens
    token_usage_stats["completion_tokens"] += c_tokens

    # Dynamic intelligent response simulation
    simulated_reply = f"[Ollama/OpenAI via travel-igw] Processed reasoning for model '{req.model}'. Generated synthesized travel plan."

    return {
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "model": req.model,
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
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": p_tokens + c_tokens,
        },
        "gateway_metadata": {
            "authenticated_by_vault": True,
            "gateway_tier": request.headers.get("x-consul-mesh-tier", "travel-igw-2.1"),
            "tenant_obo_user": request.headers.get("x-obo-user-id", "anonymous"),
        },
    }

@app.post("/v1/messages")
@app.post("/anthropic/v1/messages")
async def anthropic_messages(request: Request):
    """Anthropic Claude fallback endpoint"""
    body = await request.json()
    model = body.get("model", "claude-3-5-sonnet")
    return {
        "id": f"msg-{int(time.time()*1000)}",
        "type": "message",
        "model": model,
        "content": [{"type": "text", "text": f"[Anthropic via travel-igw] Synthesized message response with {model}."}],
        "usage": {"input_tokens": 25, "output_tokens": 30},
    }

@app.get("/metrics/tokens")
async def get_metrics():
    return token_usage_stats

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "llm-backend"}
