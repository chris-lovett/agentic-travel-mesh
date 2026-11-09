"""
External MCP Travel Server (External Partner Tools)
Accessed outside the mesh via the Consul Terminating Gateway with Vault API key injection.
"""
from fastapi import FastAPI, Request, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any
import uuid

app = FastAPI(title="External Partner Travel MCP Server", version="1.0.0")

class CarRentalRequest(BaseModel):
    destination: str
    vehicle_class: str = "Executive Sedan"
    rental_days: int = 4

@app.post("/external/mcp/ground-transport")
async def ground_transport(req: CarRentalRequest, request: Request):
    """External Travel Partner Endpoint requiring Vault injected credential"""
    auth_header = request.headers.get("authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing Vault-injected external partner credential from Terminating Gateway",
        )

    rental_id = f"RENT-{uuid.uuid4().hex[:6].upper()}"
    rate_per_day = 85.0
    total = rate_per_day * req.rental_days

    return {
        "external_mcp": "hertz-amadeus-partner-gds",
        "status": "reserved",
        "rental_id": rental_id,
        "destination": req.destination,
        "vehicle": req.vehicle_class,
        "days": req.rental_days,
        "total_amount_usd": total,
        "vault_egress_security": {
            "credential_injected_by": "consul-terminating-gateway",
            "authenticated": True,
        },
    }

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "external-mcp-server"}
