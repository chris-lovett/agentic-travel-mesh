"""
External MCP Travel Server (External Partner Tools via Terminating Gateway)
Accessed outside the mesh via the Consul Terminating Gateway with:
1. Vault-backed credential injection (Bearer vault:secret/data/partners/amadeus#key_99)
2. Identity Plane OBO scope verification (requires 'partner:gds_egress' or 'booking:reserve')
"""
from fastapi import FastAPI, Request, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any
import uuid

app = FastAPI(title="External Partner Travel MCP Server", version="2.1.0")


class CarRentalRequest(BaseModel):
    destination: str
    vehicle_class: str = "Executive Sedan"
    rental_days: int = 4


@app.post("/external/mcp/ground-transport")
async def ground_transport(req: CarRentalRequest, request: Request):
    """External Travel Partner Endpoint requiring Vault injected credential + valid OBO scope"""
    auth_header = request.headers.get("authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing Vault-injected external partner credential from Terminating Gateway",
        )

    # Check if OBO scopes explicitly restrict external partner egress (e.g. contractor persona in Act 3)
    obo_scopes_raw = request.headers.get("x-obo-scopes", "")
    if obo_scopes_raw:
        scopes = [s.strip() for s in obo_scopes_raw.split(",") if s.strip()]
        if "partner:gds_egress" not in scopes and "booking:reserve" not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Identity Plane OBO Denied at Terminating Gateway: user '{request.headers.get('x-obo-user-id', 'contractor')}' "
                    f"(scopes={scopes}) is not authorized for external partner GDS egress ('partner:gds_egress')"
                ),
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
            "per_model_mtls": True,
        },
    }


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "external-mcp-server"}
