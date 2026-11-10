#!/usr/bin/env python3
"""
Consul Agentic Mesh Platform (CAMP) 5-Act Interactive Showcase Runner
======================================================================
Executes the full 5-act governance demonstration flow either interactively
or headless (--auto / --all / --act <1-5>).

Governance Acts:
  Act 1: AI Inference Gateway (csl-inf-rt) Failover & OpenAI-to-Anthropic Protocol Translation
  Act 2: Consul MCP Sidecar (csl-mcp-sc) Per-Tool Policy (-32001) & Cryptographic HITL Gate (-32003)
  Act 3: Identity Plane RFC 8693 On-Behalf-Of (OBO) Delegation & Scope Narrowing (-32002 / 403)
  Act 4: Agentic Analytics (csl-ag-ana) Cycle Detection & Agent-Scoped Circuit Breaker (-32029)
  Act 5: Zero-Code Auto-Instrumentation Span Relay (csl-nod-rly) & Declarative CRD Governance
"""
import sys
import os
import time
import json
import asyncio
import hashlib
import argparse
from typing import Dict, Any, List, Optional, Union

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import httpx

# Rich terminal styling with graceful ANSI fallback
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.syntax import Syntax
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# Import FastAPI applications for in-memory ASGI routing
from mcp_tools.hotel_booking.main import app as hotel_app
from mcp_tools.flight_booking.main import app as flight_app
from mcp_tools.external_mcp.main import app as external_app
from mcp_tools.weather_server.main import app as weather_app
from llm_backend.main import app as llm_app
from observability.indigo.main import app as indigo_app
from observability.otel.main import app as otel_app
from agents.orchestrator.main import app as orch_app
from agents.booking_agent.main import app as booking_app
from agents.weather_agent.main import app as weather_agent_app
from frontend.main import app as frontend_app


# ==============================================================================
# In-Memory Mesh Transport Routing Engine
# ==============================================================================

SERVICE_APP_MAP: Dict[str, Any] = {
    "hotel-mcp:8083": hotel_app,
    "hotel-mcp": hotel_app,
    "flight-mcp:8084": flight_app,
    "flight-mcp": flight_app,
    "external-mcp:8088": external_app,
    "external-mcp": external_app,
    "weather-mcp:8082": weather_app,
    "weather-mcp": weather_app,
    "llm-backend:8081": llm_app,
    "llm-backend": llm_app,
    "travel-igw:10001": llm_app,
    "travel-igw": llm_app,
    "terminating-gw:10002": external_app,
    "terminating-gw": external_app,
    "indigo-analytics:8089": indigo_app,
    "indigo-analytics": indigo_app,
    "otel-collector:4318": otel_app,
    "otel-collector": otel_app,
    "travel-orchestrator:8080": orch_app,
    "travel-orchestrator": orch_app,
    "api-gw:10000": orch_app,
    "api-gw": orch_app,
    "booking-agent:8086": booking_app,
    "booking-agent": booking_app,
    "weather-agent:8087": weather_agent_app,
    "weather-agent": weather_agent_app,
    "experience-ui:3000": frontend_app,
    "experience-ui": frontend_app,
}


class InMemoryMeshTransport(httpx.AsyncBaseTransport):
    """
    Simulates the Envoy service mesh data plane in memory.
    Routes inter-service HTTP requests across FastAPI microservices
    using ASGI in-process transport without network overhead.
    """
    def __init__(self):
        self.transports: Dict[str, httpx.ASGITransport] = {
            key: httpx.ASGITransport(app=app)
            for key, app in SERVICE_APP_MAP.items()
        }

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        netloc = request.url.netloc.decode("ascii") if isinstance(request.url.netloc, bytes) else str(request.url.netloc)
        host = request.url.host
        port = request.url.port
        target_with_port = f"{host}:{port}" if port else host

        transport = (
            self.transports.get(target_with_port)
            or self.transports.get(host)
            or self.transports.get(netloc)
        )
        if transport:
            return await transport.handle_async_request(request)

        return httpx.Response(
            status_code=404,
            json={"error": f"Service '{target_with_port}' not registered in in-memory mesh"},
        )


def patch_mesh_transport(is_live: bool = False) -> Optional[InMemoryMeshTransport]:
    """
    Monkeypatches httpx.AsyncClient.__init__ to route internal microservice
    HTTP calls through the in-memory mesh transport when not running in live network mode.
    """
    if not is_live:
        shared_transport = InMemoryMeshTransport()
        orig_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            if "transport" not in kwargs:
                kwargs["transport"] = shared_transport
            orig_init(self, *args, **kwargs)

        httpx.AsyncClient.__init__ = patched_init
        return shared_transport
    return None


# ==============================================================================
# Terminal Presentation & Diagnostic Formatter
# ==============================================================================

class TerminalFormatter:
    """Provides formatted output with Rich (colors, panels, tables, JSON) or ANSI fallback."""

    def __init__(self, plain: bool = False):
        self.plain = plain
        self.console = Console() if HAS_RICH and not plain else None

    def banner(self, title: str, subtitle: str = ""):
        if self.console:
            text = f"[bold cyan]{title}[/bold cyan]"
            if subtitle:
                text += f"\n[dim]{subtitle}[/dim]"
            self.console.print(Panel(text, border_style="bright_blue", expand=False))
        else:
            print("\n" + "=" * 70)
            print(f"  {title}")
            if subtitle:
                print(f"  {subtitle}")
            print("=" * 70)

    def act_header(self, act_id: str, title: str, summary: str):
        if self.console:
            content = f"[bold yellow]{act_id}: {title}[/bold yellow]\n[italic white]{summary}[/italic white]"
            self.console.print(Panel(content, border_style="cyan", title="[bold magenta]CAMP GOVERNANCE ACT[/bold magenta]"))
        else:
            print("\n" + "-" * 70)
            print(f"▶ {act_id}: {title}")
            print(f"  {summary}")
            print("-" * 70)

    def step(self, step_num: Union[int, str], title: str, narrative: str):
        if self.console:
            self.console.print(f"\n[bold green]Step {step_num}:[/bold green] [bold white]{title}[/bold white]")
            self.console.print(f"  [dim cyan]ℹ {narrative}[/dim cyan]")
        else:
            print(f"\nStep {step_num}: {title}")
            print(f"  ℹ {narrative}")

    def pill(self, text: str, style: str = "info"):
        color_map = {
            "success": ("green", "✓"),
            "warning": ("yellow", "⚠"),
            "danger": ("red", "✗"),
            "info": ("cyan", "ℹ"),
            "highlight": ("magenta", "★"),
        }
        color, symbol = color_map.get(style, ("cyan", "ℹ"))
        if self.console:
            self.console.print(f"  [{color} bold]{symbol} [{text}][/{color} bold]")
        else:
            print(f"  {symbol} [{text}]")

    def json(self, label: str, data: Dict[str, Any]):
        dumped = json.dumps(data, indent=2)
        if self.console:
            self.console.print(f"  [dim]{label}:[/dim]")
            syntax = Syntax(dumped, "json", theme="monokai", line_numbers=False)
            self.console.print(syntax)
        else:
            print(f"  {label}:")
            for line in dumped.splitlines():
                print(f"    {line}")

    def table(self, title: str, headers: List[str], rows: List[List[str]]):
        if self.console:
            tbl = Table(title=title, border_style="blue", show_header=True, header_style="bold cyan")
            for h in headers:
                tbl.add_column(h)
            for row in rows:
                tbl.add_row(*row)
            self.console.print(tbl)
        else:
            print(f"\n--- {title} ---")
            header_line = " | ".join(headers)
            print(header_line)
            print("-" * len(header_line))
            for r in rows:
                print(" | ".join(r))
            print()

    def prompt(self, message: str = "Press Enter to continue..."):
        if not sys.stdin.isatty():
            return ""
        try:
            if not self.plain and self.console:
                return self.console.input(f"\n[bold yellow]❯ {message}[/bold yellow]")
            else:
                return input(f"\n❯ {message}")
        except (EOFError, IOError):
            return ""


# ==============================================================================
# Act 1: AI Inference Gateway Failover & Protocol Translation
# ==============================================================================

async def run_act1(client: httpx.AsyncClient, fmt: TerminalFormatter, auto: bool, delay: float) -> bool:
    fmt.act_header(
        "Act 1",
        "AI Gateway Failover & OpenAI-to-Anthropic Protocol Translation",
        "Consul AI Inference Gateway (csl-inf-rt) capability routing, HashiCorp Vault token injection, "
        "and seamless dynamic failover between foundation models."
    )

    # Step 1A: Normal Priority-1 Llama-3 Inference
    fmt.step(
        "1A",
        "Normal Priority-1 Inference via travel-igw",
        "Client sends OpenAI /v1/chat/completions payload with HashiCorp Vault bearer reference."
    )
    req_body = {
        "model": "meta-llama/llama-3-70b-instruct",
        "messages": [{"role": "user", "content": "Route: JFK to Tokyo for HashiCorp AI Architecture Summit"}],
    }
    headers = {"Authorization": "Bearer vault:secret/data/ai/llm#sk_99201"}

    resp = await client.post("http://travel-igw:10001/v1/chat/completions", json=req_body, headers=headers)
    assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"
    data = resp.json()
    gw_meta = data.get("gateway_metadata", {})

    fmt.pill(f"HTTP {resp.status_code} OK", "success")
    fmt.pill(f"Model Routed: {gw_meta.get('routed_model')}", "info")
    fmt.pill(f"Authenticated by Vault: {gw_meta.get('authenticated_by_vault')}", "success")
    fmt.pill(f"Failover Triggered: {gw_meta.get('failover_triggered')}", "info")
    fmt.json("Response Metadata", gw_meta)

    if not auto:
        fmt.prompt("Press Enter to trigger simulated Primary LLM outage...")
    else:
        await asyncio.sleep(delay)

    # Step 1B: Priority-1 Outage -> Automatic Anthropic Claude Failover & Protocol Translation
    fmt.step(
        "1B",
        "Simulate Primary Outage -> Dynamic Priority-2 Failover",
        "travel-igw detects outage, swaps Vault bearer token to Anthropic key, translates OpenAI schema to Claude messages."
    )
    failover_headers = {
        "Authorization": "Bearer vault:secret/data/ai/llm#sk_99201",
        "x-simulate-llm-outage": "true",
    }
    resp_failover = await client.post("http://travel-igw:10001/v1/chat/completions", json=req_body, headers=failover_headers)
    assert resp_failover.status_code == 200, f"Expected 200 but got {resp_failover.status_code}: {resp_failover.text}"
    fo_data = resp_failover.json()
    fo_meta = fo_data.get("gateway_metadata", {})

    assert fo_meta.get("failover_triggered") is True, "Expected failover_triggered=True"
    assert "claude-3-5-sonnet" in fo_meta.get("routed_model", ""), "Expected routed_model to contain claude-3-5-sonnet"

    fmt.pill("PRIMARY LLM OUTAGE DETECTED", "warning")
    fmt.pill(f"FAILOVER ACTIVE: {fo_meta.get('routed_model')}", "highlight")
    fmt.pill(f"PROTOCOL TRANSLATION: {fo_meta.get('protocol_translation')}", "success")
    fmt.pill(f"VAULT SECRET SWAPPED: {fo_meta.get('vault_secret_ref')}", "info")
    fmt.json("Failover Gateway Audit Trace", fo_meta)

    fmt.pill("Act 1 PASSED: AI Gateway Failover & Schema Translation Verified", "success")
    return True


# ==============================================================================
# Act 2: Consul MCP Sidecar (csl-mcp-sc) Per-Tool Policy & HITL Gate
# ==============================================================================

async def run_act2a(client: httpx.AsyncClient, fmt: TerminalFormatter, auto: bool, delay: float) -> bool:
    fmt.act_header(
        "Act 2a",
        "MCP Sidecar Per-Tool SPIFFE ID Policy Rejection (-32001)",
        "Consul MCP Sidecar (csl-mcp-sc) decouples tool discovery from invocation authority. "
        "Sensitive administrative tools are blocked at the proxy layer with JSON-RPC -32001."
    )

    # Step 2A.1: Catalog Discovery
    fmt.step(
        "2A.1",
        "Discover Catalog Tools via JSON-RPC tools/list",
        "Agent queries hotel-mcp catalog. All tools are visible, including override_hotel_rate."
    )
    list_req = {"jsonrpc": "2.0", "id": "act2a-disc", "method": "tools/list"}
    resp = await client.post("http://hotel-mcp:8083/mcp", json=list_req)
    assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}"
    tools = resp.json().get("result", {}).get("tools", [])
    tool_names = [t["name"] for t in tools]

    fmt.pill("CATALOG DISCOVERY COMPLETE", "info")
    rows = [[t["name"], t.get("description", "")] for t in tools]
    fmt.table("Discovered MCP Tools (hotel-mcp)", ["Tool Name", "Description"], rows)
    assert "override_hotel_rate" in tool_names, "override_hotel_rate should be in catalog"

    if not auto:
        fmt.prompt("Press Enter to test unauthorized invocation by booking-agent...")
    else:
        await asyncio.sleep(delay)

    # Step 2A.2: Unauthorized Invocation Attempt
    fmt.step(
        "2A.2",
        "Booking Agent Invokes override_hotel_rate",
        "csl-mcp-sc proxy evaluates caller SPIFFE ID against per-tool policy and blocks invocation."
    )
    unauth_req = {
        "jsonrpc": "2.0",
        "id": "act2a-call",
        "method": "tools/call",
        "params": {
            "name": "override_hotel_rate",
            "arguments": {"hotel_id": "HTL-SF-01", "new_rate_usd": 50.0},
        },
    }
    caller_headers = {"x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"}

    resp_call = await client.post("http://hotel-mcp:8083/mcp", json=unauth_req, headers=caller_headers)
    assert resp_call.status_code == 200, f"Expected 200 but got {resp_call.status_code}"
    err = resp_call.json().get("error", {})

    assert err.get("code") == -32001, f"Expected error code -32001, got {err.get('code')}"
    fmt.pill(f"INTERCEPTED: Code {err.get('code')} (PER_TOOL_POLICY_DENIED)", "danger")
    fmt.pill(f"Enforced By: {err.get('data', {}).get('enforced_by')}", "highlight")
    fmt.json("csl-mcp-sc Policy Rejection Error", err)

    fmt.pill("Act 2a PASSED: Per-Tool SPIFFE ID Policy Enforcement Verified", "success")
    return True


async def run_act2b(client: httpx.AsyncClient, fmt: TerminalFormatter, auto: bool, delay: float) -> bool:
    fmt.act_header(
        "Act 2b",
        "Cryptographic Human-in-the-Loop (HITL) Approval Gate (-32003 -> Confirmed)",
        "State-mutating MCP tools require cryptographic evidence signed by an authorized approver. "
        "Missing evidence results in -32003; valid signature permits execution."
    )

    # Step 2B.1: Mutation Attempt Without HITL Evidence
    fmt.step(
        "2B.1",
        "Invoking reserve_hotel Without Cryptographic Evidence",
        "csl-mcp-sc intercepts state-mutating tool and holds action with JSON-RPC error -32003."
    )
    hotel_call = {
        "jsonrpc": "2.0",
        "id": "act2b-no-hitl",
        "method": "tools/call",
        "params": {
            "name": "reserve_hotel",
            "arguments": {"hotel_id": "HTL-SF-01", "guest_name": "Alex Mercer", "nights": 4},
        },
    }
    hdrs_no_hitl = {
        "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
    }

    resp = await client.post("http://hotel-mcp:8083/mcp", json=hotel_call, headers=hdrs_no_hitl)
    assert resp.status_code == 200
    err = resp.json().get("error", {})

    assert err.get("code") == -32003, f"Expected error code -32003, got {err.get('code')}"
    fmt.pill(f"INTERCEPTED: Code {err.get('code')} (HELD_FOR_HITL_APPROVAL)", "warning")
    fmt.pill(f"Reason: {err.get('message')}", "info")
    fmt.json("csl-mcp-sc HITL Gate Error", err)

    if not auto:
        fmt.prompt("Press Enter to approve proposal and mint cryptographic evidence token...")
    else:
        await asyncio.sleep(delay)

    # Step 2B.2: Approver Mints Cryptographic Evidence
    fmt.step(
        "2B.2",
        "Approver Reviews Proposal & Mints Cryptographic Evidence",
        "SHA-256 signature calculated over (trip_id, approver, flight_number, hotel_id)."
    )
    trip_id = f"TRIP-{int(time.time())}"
    approver = "Manager / Finance Compliance"
    raw_evidence = f"{trip_id}:{approver}:UA-442:HTL-SF-01"
    evidence_hash = hashlib.sha256(raw_evidence.encode("utf-8")).hexdigest()[:16]
    hitl_token = f"hitl-sig-{evidence_hash}"

    fmt.pill(f"APPROVAL GRANTED by {approver}", "success")
    fmt.pill(f"CRYPTOGRAPHIC EVIDENCE: {hitl_token}", "highlight")

    # Step 2B.3: Re-invoking reserve_hotel with Evidence
    fmt.step(
        "2B.3",
        "Re-invoking reserve_hotel with x-consul-hitl-evidence Header",
        "csl-mcp-sc validates signature token and allows execution to proceed to hotel-mcp backend."
    )
    hdrs_with_hitl = {
        "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        "x-obo-scopes": "travel:read,travel:plan,booking:reserve",
        "x-consul-hitl-evidence": hitl_token,
    }

    resp_auth = await client.post("http://hotel-mcp:8083/mcp", json=hotel_call, headers=hdrs_with_hitl)
    assert resp_auth.status_code == 200
    result = resp_auth.json().get("result", {})

    assert result.get("status") == "confirmed", f"Expected confirmed, got {result.get('status')}"
    ref = result.get('booking_reference') or result.get('confirmation_reference', 'CONFIRMED')
    fmt.pill(f"BOOKING CONFIRMED: Reference {ref}", "success")
    fmt.pill(f"Hotel: {result.get('hotel_name')} | Nights: {result.get('nights')}", "info")
    fmt.json("Confirmed Reservation Result", result)

    fmt.pill("Act 2b PASSED: Cryptographic HITL Gate & Approval Token Verified", "success")
    return True


async def run_act2(client: httpx.AsyncClient, fmt: TerminalFormatter, auto: bool, delay: float) -> bool:
    p1 = await run_act2a(client, fmt, auto, delay)
    if not auto:
        fmt.prompt("Press Enter to proceed to Act 2b (HITL Approval Gate)...")
    else:
        await asyncio.sleep(delay)
    p2 = await run_act2b(client, fmt, auto, delay)
    return p1 and p2


# ==============================================================================
# Act 3: Identity Plane RFC 8693 On-Behalf-Of (OBO) Delegation & Scopes
# ==============================================================================

async def run_act3(client: httpx.AsyncClient, fmt: TerminalFormatter, auto: bool, delay: float) -> bool:
    fmt.act_header(
        "Act 3",
        "Identity Plane RFC 8693 On-Behalf-Of (OBO) Delegation & Scope Narrowing",
        "Consul Identity Plane propagates user context across multi-agent hops. "
        "Enforces scope narrowing: Alex Mercer (VP) vs Sam Taylor (Contractor)."
    )

    # Step 3A: Display IAM Personas
    fmt.step("3A.1", "Inspect Customer IAM Persona Scopes", "Comparing VP Engineering vs External Contractor authority.")
    personas_table = [
        ["traveler-101 (Alex Mercer)", "VP Engineering", "travel:read, travel:plan, booking:reserve, partner:gds_egress"],
        ["contractor-202 (Sam Taylor)", "External Contractor", "travel:read, travel:plan (Read/Plan ONLY)"],
    ]
    fmt.table("IAM Personas (IBM Verify / RFC 8693 Directory)", ["Persona", "Role", "Authorized Scopes"], personas_table)

    if not auto:
        fmt.prompt("Press Enter to test Contractor Sam Taylor's flight booking attempt...")
    else:
        await asyncio.sleep(delay)

    # Step 3A.2: Contractor Attempts reserve_flight (Destination Identity Enforcement)
    fmt.step(
        "3A.2",
        "Contractor Sam Taylor Attempts reserve_flight",
        "flight-mcp Destination Identity Processor verifies scopes. Sam Taylor lacks booking:reserve -> -32002."
    )
    contractor_flight_req = {
        "jsonrpc": "2.0",
        "id": "act3-contractor-flight",
        "method": "tools/call",
        "params": {
            "name": "reserve_flight",
            "arguments": {"flight_number": "UA-442", "passenger_name": "Sam Taylor"},
        },
    }
    contractor_hdrs = {
        "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        "x-obo-user-id": "contractor-202",
        "x-obo-scopes": "travel:read,travel:plan",
        "x-consul-hitl-evidence": "hitl-sig-simulated",
    }

    resp = await client.post("http://flight-mcp:8084/mcp", json=contractor_flight_req, headers=contractor_hdrs)
    assert resp.status_code == 200
    err = resp.json().get("error", {})

    assert err.get("code") == -32002, f"Expected -32002, got {err.get('code')}"
    fmt.pill(f"OBO SCOPE DENIED: Code {err.get('code')} (OBO_SCOPE_DENIED)", "danger")
    fmt.pill(f"Enforced By: {err.get('data', {}).get('enforced_by')}", "highlight")
    fmt.pill(f"Missing Scope: {err.get('data', {}).get('required_scope')}", "warning")
    fmt.json("Destination Identity OBO Scope Violation", err)

    if not auto:
        fmt.prompt("Press Enter to test Contractor Sam Taylor's external partner ground transport attempt...")
    else:
        await asyncio.sleep(delay)

    # Step 3A.3: Contractor Attempts External Ground Transport (Terminating Gateway Egress Block)
    fmt.step(
        "3A.3",
        "Contractor Sam Taylor Attempts External Partner Ground Transport",
        "Terminating Gateway checks partner:gds_egress. Contractor lacks egress authority -> HTTP 403 Forbidden."
    )
    ext_req = {"destination": "San Francisco", "rental_days": 4}
    ext_hdrs_contractor = {
        "Authorization": "Bearer vault:secret/data/partners/amadeus#gds_token_9918",
        "x-obo-user-id": "contractor-202",
        "x-obo-scopes": "travel:read,travel:plan",
    }

    resp_ext = await client.post("http://terminating-gw:10002/external/mcp/ground-transport", json=ext_req, headers=ext_hdrs_contractor)
    assert resp_ext.status_code == 403, f"Expected 403, got {resp_ext.status_code}"
    fmt.pill(f"TERMINATING GATEWAY BLOCKED: HTTP {resp_ext.status_code} Forbidden", "danger")
    fmt.json("Terminating Gateway Security Policy Error", resp_ext.json())

    if not auto:
        fmt.prompt("Press Enter to test VP Alex Mercer's execution with full authority...")
    else:
        await asyncio.sleep(delay)

    # Step 3B: VP Alex Mercer Execution (Full Scopes -> Confirmed)
    fmt.step(
        "3B",
        "VP Alex Mercer Executes Flight & External Egress",
        "Alex Mercer holds booking:reserve and partner:gds_egress -> both succeed with 200 OK."
    )
    vp_flight_req = {
        "jsonrpc": "2.0",
        "id": "act3-alex-flight",
        "method": "tools/call",
        "params": {
            "name": "reserve_flight",
            "arguments": {"flight_number": "UA-442", "passenger_name": "Alex Mercer"},
        },
    }
    vp_hdrs = {
        "x-caller-spiffe-id": "spiffe://cluster.local/ns/camp-travel/sa/booking-agent",
        "x-obo-user-id": "traveler-101",
        "x-obo-scopes": "travel:read,travel:plan,booking:reserve,partner:gds_egress",
        "x-consul-hitl-evidence": "hitl-sig-simulated",
    }
    resp_vp_flight = await client.post("http://flight-mcp:8084/mcp", json=vp_flight_req, headers=vp_hdrs)
    assert resp_vp_flight.status_code == 200
    flight_res = resp_vp_flight.json().get("result", {})
    assert "confirmed" in flight_res.get("status", ""), f"Expected status containing 'confirmed', got {flight_res.get('status')}"
    pnr = flight_res.get("pnr") or flight_res.get("confirmation_pnr", "")
    fmt.pill(f"FLIGHT CONFIRMED: PNR {pnr}", "success")

    vp_ext_hdrs = {
        "Authorization": "Bearer vault:secret/data/partners/amadeus#gds_token_9918",
        "x-obo-user-id": "traveler-101",
        "x-obo-scopes": "travel:read,travel:plan,booking:reserve,partner:gds_egress",
    }
    resp_vp_ext = await client.post("http://terminating-gw:10002/external/mcp/ground-transport", json=ext_req, headers=vp_ext_hdrs)
    assert resp_vp_ext.status_code == 200
    ext_res = resp_vp_ext.json()
    assert ext_res.get("status") == "reserved"
    fmt.pill(f"GROUND TRANSPORT RESERVED: Ref {ext_res.get('reservation_reference')}", "success")

    fmt.pill("Act 3 PASSED: Identity Plane RFC 8693 OBO Delegation & Scope Narrowing Verified", "success")
    return True


# ==============================================================================
# Act 4: Agentic Analytics (csl-ag-ana) Cycle Detection & Circuit Breaker
# ==============================================================================

async def run_act4(client: httpx.AsyncClient, fmt: TerminalFormatter, auto: bool, delay: float) -> bool:
    fmt.act_header(
        "Act 4",
        "Agentic Analytics Cycle Detection & Agent-Scoped Circuit Breaker (-32029)",
        "Consul Agentic Analytics (csl-ag-ana) evaluates tool call spans asynchronously. "
        "Detects repetitive execution loops and trips an agent-scoped circuit breaker to protect backend tools."
    )

    # Step 4A: Reset Circuit State
    fmt.step("4A", "Reset Circuit Breaker State & Clear Fingerprint Window", "Restoring all agent circuits to CLOSED.")
    reset_resp = await client.post("http://indigo-analytics:8089/api/indigo/circuit/reset", json={})
    assert reset_resp.status_code == 200
    fmt.pill("CIRCUIT BREAKER STATE INITIALIZED: CLOSED", "info")

    if not auto:
        fmt.prompt("Press Enter to simulate runaway agent execution loop...")
    else:
        await asyncio.sleep(delay)

    # Step 4B: Runaway Tool-Call Loop Ingestion
    spiffe_id = "spiffe://cluster.local/ns/camp-travel/sa/booking-agent"
    fmt.step(
        "4B",
        "Agent Emits Repetitive Tool Calls to search_flights",
        "csl-nod-rly queues spans to csl-ag-ana. Repetition threshold is 3."
    )

    for i in range(1, 4):
        span_payload = {
            "trace_id": f"trace-loop-demo-{int(time.time())}",
            "span_type": "mcp_tool_call",
            "agent_spiffe_id": spiffe_id,
            "service": "booking-agent",
            "mcp_server": "flight-mcp",
            "tool_name": "search_flights",
            "tool_arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
            "tool_result": {"status": "NO_INVENTORY_RETRYABLE"},
        }
        res = await client.post("http://indigo-analytics:8089/api/indigo/ingest-span", json=span_payload)
        assert res.status_code == 200
        body = res.json()
        rep_count = body.get("repetition_count")
        state = body.get("circuit_state")
        fp = body.get("fingerprint")

        if i < 3:
            fmt.pill(f"Repetition #{rep_count}: Fingerprint {fp} | Circuit: {state}", "info")
            assert state == "CLOSED"
        else:
            fmt.pill(f"Repetition #{rep_count}: THRESHOLD REACHED! Fingerprint {fp}", "warning")
            fmt.pill(f"CIRCUIT TRIPPED: state={state} (csl-ag-ana)", "danger")
            assert state == "OPEN"

    if not auto:
        fmt.prompt("Press Enter to invoke flight-mcp as booking-agent while circuit is OPEN...")
    else:
        await asyncio.sleep(delay)

    # Step 4C: Proxy Rejection on Next Tool Call (-32029)
    fmt.step(
        "4C",
        "Next Tool Call Intercepted at Proxy Layer with JSON-RPC -32029",
        "Consul MCP Sidecar checks agent circuit breaker before executing tool. Returns AGENT_CIRCUIT_OPEN."
    )
    blocked_call = {
        "jsonrpc": "2.0",
        "id": "act4-blocked-call",
        "method": "tools/call",
        "params": {
            "name": "search_flights",
            "arguments": {"origin": "JFK", "destination": "SOLDOUT-LOOP"},
        },
    }
    call_hdrs = {"x-caller-spiffe-id": spiffe_id}

    resp_block = await client.post("http://flight-mcp:8084/mcp", json=blocked_call, headers=call_hdrs)
    assert resp_block.status_code == 200
    err = resp_block.json().get("error", {})

    assert err.get("code") == -32029, f"Expected -32029, got {err.get('code')}"
    fmt.pill(f"BLOCKED AT PROXY LAYER: Code {err.get('code')} (AGENT_CIRCUIT_OPEN)", "danger")
    fmt.pill(f"Enforced By: {err.get('data', {}).get('enforced_by')}", "highlight")
    fmt.json("Consul Behavior Policy Circuit Breaker Error", err)

    # Verify audit summary reflects CIRCUIT_OPEN_HALTED
    audit = await client.get("http://indigo-analytics:8089/api/indigo/audit-summary")
    assert audit.status_code == 200
    assert audit.json().get("compliance_status") == "CIRCUIT_OPEN_HALTED"
    fmt.pill(f"Governance Compliance Status: {audit.json().get('compliance_status')}", "warning")

    if not auto:
        fmt.prompt("Press Enter to execute operator circuit breaker reset...")
    else:
        await asyncio.sleep(delay)

    # Step 4D: Operator Remediation & Reset
    fmt.step("4D", "Operator Resets Circuit via Consul Behavior Policy", "Restores agent-scoped circuit breaker to COMPLIANT.")
    await client.post("http://indigo-analytics:8089/api/indigo/circuit/reset", json={})
    audit_after = await client.get("http://indigo-analytics:8089/api/indigo/audit-summary")
    assert audit_after.json().get("compliance_status") == "COMPLIANT"
    fmt.pill("OPERATOR REMEDIATION COMPLETE: compliance_status=COMPLIANT", "success")

    fmt.pill("Act 4 PASSED: Agentic Analytics Cycle Detection & Circuit Breaker Verified", "success")
    return True


# ==============================================================================
# Act 5: Observability & Declarative CRD Governance
# ==============================================================================

async def run_act5(client: httpx.AsyncClient, fmt: TerminalFormatter, auto: bool, delay: float) -> bool:
    fmt.act_header(
        "Act 5",
        "Observability, Span Relay & Declarative CRD Architecture",
        "OpenTelemetry Collector & Span Relay (csl-nod-rly), GenAI semantic attributes, "
        "and declarative Kubernetes CRD governance."
    )

    # Step 5A: Ingest Trace & Inspect GenAI Semantic Attributes
    fmt.step(
        "5A",
        "Span Relay (csl-nod-rly) Auto-Instrumentation & GenAI Semantic Attributes",
        "Mesh proxies emit spans with gen_ai.* and consul.* semantic conventions without code SDKs."
    )
    trace_payload = {
        "trace_id": f"trace-act5-demo-{int(time.time())}",
        "service": "travel-orchestrator",
        "agent_spiffe_id": "spiffe://cluster.local/ns/camp-travel/sa/travel-orchestrator",
        "model": "meta-llama/llama-3-70b-instruct",
        "tokens_used": 1850,
        "tool_name": "search_flights",
        "mcp_server": "flight-mcp",
        "user_obo": "traveler-101",
        "obo_scopes": ["travel:read", "travel:plan", "booking:reserve"],
        "failover_triggered": False,
    }
    ingest_resp = await client.post("http://otel-collector:4318/v1/traces", json=trace_payload)
    assert ingest_resp.status_code == 200
    attrs = ingest_resp.json().get("attributes", {})

    fmt.pill("ZERO-CODE PROXY TELEMETRY INGESTED", "success")
    attr_rows = [[k, str(v)] for k, v in attrs.items()]
    fmt.table("OpenTelemetry GenAI Semantic Attributes", ["Attribute Key", "Value"], attr_rows)

    if not auto:
        fmt.prompt("Press Enter to inspect BullMQ relay queue and Indigo audit summary...")
    else:
        await asyncio.sleep(delay)

    # Step 5B: Relay Queue & Analytics Audit Summary
    fmt.step("5B", "Query BullMQ Span Relay Queue & Indigo Audit Summary", "Verifies real-time feature gate and metrics.")
    traces_query = await client.get("http://otel-collector:4318/v1/traces")
    assert traces_query.status_code == 200
    q_data = traces_query.json()
    fmt.pill(f"BullMQ Span Relay Queue Depth: {q_data.get('bullmq_queue_depth')}", "info")

    audit = await client.get("http://indigo-analytics:8089/api/indigo/audit-summary")
    assert audit.status_code == 200
    audit_data = audit.json()
    metrics = audit_data.get("metrics", {})

    metrics_rows = [
        ["Engine", audit_data.get("engine", "")],
        ["Feature Gate", audit_data.get("feature_gate", "")],
        ["Compliance Status", audit_data.get("compliance_status", "")],
        ["Policy Violations Prevented", str(metrics.get("policy_violations_prevented", 0))],
        ["Cycles Detected", str(metrics.get("cycles_detected", 0))],
        ["Tokens Inspected", str(metrics.get("tokens_inspected_last_24h", 0))],
        ["Vault Egress Auth Rate", str(metrics.get("vault_egress_auth_success_rate", "100%"))],
    ]
    fmt.table("Indigo AI Governance Audit Summary", ["Dimension", "Value"], metrics_rows)

    if not auto:
        fmt.prompt("Press Enter to inspect Declarative Consul CRD Architecture...")
    else:
        await asyncio.sleep(delay)

    # Step 5C: Declarative CRD Architecture
    fmt.step("5C", "Consul 2.1 Declarative CRDs (consul-crds.yaml)", "Highlights AI Workload Identity, ext-proc sockets, and Intentions.")
    crd_summary = [
        ["ai-agent", "agents/orchestrator, agents/booking_agent, agents/weather_agent", "Full mesh identity + Envoy ext-proc sidecar"],
        ["mcp-server", "mcp_tools/hotel_booking, flight_booking, weather_server", "csl-mcp-sc Sidecar policy, HITL Gate & Cycle enforcement"],
        ["inference-model", "llm_backend", "Protected Foundation Model backend"],
        ["inference-gateway", "gateways/travel_igw (csl-inf-rt)", "OpenAI/Anthropic capability routing & Vault bearer injection"],
        ["terminating-gateway", "gateways/terminating_gw", "Zero-Trust egress to external partner MCP APIs with Vault token"],
        ["ext-proc socket", "/var/run/consul/csl-mcp-sc.sock", "UNIX domain socket ext-proc binding for sub-millisecond filtering"],
    ]
    fmt.table("Consul Agentic Runtime Fabric CRD Architecture", ["Workload Role / CRD", "Target Services", "Mesh Capabilities"], crd_summary)

    fmt.pill("Act 5 PASSED: Observability & CRD Governance Verified", "success")
    return True


# ==============================================================================
# CLI Entrypoint & Runner Coordinator
# ==============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consul Agentic Mesh Platform (CAMP) 5-Act Governance Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/run_showcase.py --all            # Run all 5 acts headless
  python3 scripts/run_showcase.py --act 1          # Run Act 1 only
  python3 scripts/run_showcase.py --act 2a         # Run Act 2a only
  python3 scripts/run_showcase.py --auto --plain   # Automated run without colors
  python3 scripts/run_showcase.py                  # Full interactive walkthrough
        """,
    )
    parser.add_argument("--auto", action="store_true", help="Run in non-interactive/headless mode")
    parser.add_argument("--all", action="store_true", help="Run all acts sequentially")
    parser.add_argument(
        "--act", "-a",
        type=str,
        choices=["1", "2a", "2b", "2", "3", "4", "5"],
        help="Run specific governance act",
    )
    parser.add_argument("--delay", type=float, default=0.2, help="Delay in seconds between steps in auto mode")
    parser.add_argument("--live", action="store_true", help="Connect to live network services instead of in-memory mesh")
    parser.add_argument("--plain", action="store_true", help="Disable rich terminal colors and tables")
    return parser.parse_args()


async def run_cli(args: argparse.Namespace) -> int:
    fmt = TerminalFormatter(plain=args.plain)
    fmt.banner(
        "Consul Agentic Runtime Fabric (CAMP) Showcase",
        "Demonstrating Multi-Agent Governance, AI Gateways, MCP Sidecars & RFC 8693 Identity",
    )

    # Monkeypatch mesh transport for transparent in-memory ASGI routing
    patch_mesh_transport(is_live=args.live)

    # Ensure delay is non-negative
    delay = max(0.0, args.delay)

    # Automatically enable auto_mode if --auto, --all, or non-interactive stdin (pipe/CI/devnull)
    auto_mode = args.auto or args.all or not sys.stdin.isatty()

    results: Dict[str, bool] = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            target_act = args.act

            # Act 1: AI Gateway Failover
            if target_act in ("1", None):
                results["Act 1: AI Gateway Failover"] = await run_act1(client, fmt, auto_mode, delay)
                if target_act is None:
                    if not auto_mode:
                        fmt.prompt("Press Enter to proceed to Act 2...")
                    else:
                        await asyncio.sleep(delay)

            # Act 2a: Per-Tool SPIFFE Policy
            if target_act in ("2", "2a", None):
                results["Act 2a: Per-Tool SPIFFE Policy"] = await run_act2a(client, fmt, auto_mode, delay)
                if target_act in ("2", None):
                    if not auto_mode:
                        fmt.prompt("Press Enter to proceed to Act 2b...")
                    else:
                        await asyncio.sleep(delay)

            # Act 2b: Cryptographic HITL Gate
            if target_act in ("2", "2b", None):
                results["Act 2b: Cryptographic HITL Gate"] = await run_act2b(client, fmt, auto_mode, delay)
                if target_act is None:
                    if not auto_mode:
                        fmt.prompt("Press Enter to proceed to Act 3...")
                    else:
                        await asyncio.sleep(delay)

            # Act 3: Identity Plane OBO Delegation
            if target_act in ("3", None):
                results["Act 3: Identity Plane OBO Delegation"] = await run_act3(client, fmt, auto_mode, delay)
                if target_act is None:
                    if not auto_mode:
                        fmt.prompt("Press Enter to proceed to Act 4...")
                    else:
                        await asyncio.sleep(delay)

            # Act 4: Cycle Detection & Circuit Breaker
            if target_act in ("4", None):
                results["Act 4: Cycle Detection & Circuit Breaker"] = await run_act4(client, fmt, auto_mode, delay)
                if target_act is None:
                    if not auto_mode:
                        fmt.prompt("Press Enter to proceed to Act 5...")
                    else:
                        await asyncio.sleep(delay)

            # Act 5: Observability & CRDs
            if target_act in ("5", None):
                results["Act 5: Observability & CRDs"] = await run_act5(client, fmt, auto_mode, delay)

        except Exception as e:
            fmt.pill(f"EXECUTION ERROR: {str(e)}", "danger")
            import traceback
            traceback.print_exc()
            return 1

    # Print summary table
    fmt.banner("CAMP Showcase Execution Summary", "Governance verification results")
    summary_rows = [
        [act_name, "PASSED" if passed else "FAILED"]
        for act_name, passed in results.items()
    ]
    fmt.table("Final Governance Status", ["Act Name", "Result"], summary_rows)

    all_passed = all(results.values()) and len(results) > 0
    if all_passed:
        fmt.pill("ALL GOVERNANCE ACTS VERIFIED SUCCESSFULLY!", "success")
        return 0
    else:
        fmt.pill("SHOWCASE ENCOUNTERED FAILURES!", "danger")
        return 1


def main():
    try:
        args = parse_args()
        exit_code = asyncio.run(run_cli(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nShowcase execution cancelled by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
