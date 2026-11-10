# Project: agentic-travel-mesh (CAMP Showcase)

## Architecture
The Consul Agentic Mesh Platform (CAMP) Travel Showcase consists of 14 microservices and gateways organized across 5 architectural planes:
1. **Identity & User Plane**:
   - `experience-ui`: Port 3000 (FastAPI backend + interactive single-page web UI). Handles Traveler workspace, persona switching (Alex Mercer vs. Sam Taylor), RFC 8693 On-Behalf-Of (OBO) token exchange (`/api/auth/obo-token`), trip planning dispatch (`/api/travel/plan`), cryptographic Human-in-the-Loop (HITL) signing (`/api/travel/review-action` -> `hitl-sig-<sha256>`), and governance control panel.
2. **Gateway Plane**:
   - `api-gw`: Port 10000 (Envoy v1.31 Ingress Gateway). Ingress entrypoint routing `/agent/orchestrate` to `travel-orchestrator:8080`.
   - `travel-igw`: Port 10001 (Envoy v1.31 AI Inference Gateway). Manages access to LLM foundation backends with Envoy token rate limiting (100 tokens/s), HashiCorp Vault Bearer credential injection, and capability-based priority failover (Llama-3-70B -> Claude 3.5 Sonnet with OpenAI-to-Anthropic protocol translation).
   - `terminating-gw`: Port 10002 (Envoy v1.31 Terminating Egress Gateway). Handles external egress to partner GDS systems (`external-mcp:8088`), injecting Vault Bearer tokens and enforcing OBO delegation scopes.
3. **Agent Plane**:
   - `travel-orchestrator`: Port 8080 (`ai-agent`). Master coordinator receiving travel requests, managing OBO delegation chains across hops, coordinating sub-agents concurrently, querying `travel-igw` for synthesis, and assembling itineraries.
   - `booking-agent`: Port 8086 (`ai-agent`). Sub-agent invoking `flight-mcp` and `hotel-mcp` over JSON-RPC 2.0, handling booking logic, policy exceptions, and ground transport egress via `terminating-gw`.
   - `weather-agent`: Port 8087 (`ai-agent`). Sub-agent querying `weather-mcp` over JSON-RPC 2.0, narrowing OBO scopes, and querying `travel-igw` for packing and weather advisories.
4. **Tool & Foundation Model Plane**:
   - `hotel-mcp`: Port 8083 (`mcp-server`). MCP JSON-RPC 2.0 tool provider. Enforces per-tool caller SPIFFE ID policy (`-32001`), destination OBO scope (`-32002`), and HITL approval evidence (`-32003`).
   - `flight-mcp`: Port 8084 (`mcp-server`). MCP JSON-RPC 2.0 tool provider. Enforces agent circuit breaker (`-32029`), per-tool caller SPIFFE ID policy (`-32001`), destination OBO scope (`-32002`), and HITL approval evidence (`-32003`).
   - `weather-mcp`: Port 8082 (`mcp-server`). MCP JSON-RPC 2.0 tool provider for weather forecasts.
   - `llm-backend`: Port 8081 (`inference-model` / `csl-inf-rt`). Foundation model provider simulating Priority 1 (Llama-3-70B) with failover to Priority 2 (Claude 3.5 Sonnet), OpenAI-to-Anthropic protocol translation, and Vault auth validation.
   - `external-mcp`: Port 8088 (External Partner GDS). Requires Vault credential injection and OBO `partner:gds_egress` scope.
5. **Observability & Governance Plane**:
   - `otel-collector`: Port 4318 (`csl-nod-rly`). Zero-code OpenTelemetry span relay. Receives spans, formats OTel GenAI attributes, enqueues to BullMQ, forwards to Tempo.
   - `indigo-analytics`: Port 8089 (`csl-ag-ana`). Agentic Analytics cycle detection engine. Computes SHA-256 fingerprint on tool calls, trips Agent-Scoped Circuit Breaker to `OPEN` on >=3 repetitions, and provides reset API (`/api/indigo/circuit/reset`).
   - `tempo`: Port 3200 / 4317 / 4318 (Distributed tracing backend in Helm).
   - `grafana`: Port 3000 (Tracing visualization in Helm).

## Feature Inventory
Every feature identified during the survey phase is enumerated below and mapped to a milestone.

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | `consul-ai` Dynamic Feature Gate | Dynamic Consul 2.1 Enterprise feature gate enablement via CLI, API, or HCL | M2 | Survey Spec Miner |
| 2 | AI Workload Classification CRDs | `consul.hashicorp.com/ai-role` annotations (`ai-agent`, `mcp-server`, `inference-model`, `inference-gateway`) in `consul-crds.yaml` | M2 | Survey Spec Miner |
| 3 | Envoy `builtin/ext-proc` Unix Sockets | Declarative binding to `unix:///var/run/consul/csl-mcp-sc.sock` and `csl-ig-pro.sock` | M2 | Survey Spec Miner |
| 4 | Envoy Gateway Configurations | Ingress `api-gw`, AI Inference `travel-igw`, and egress `terminating-gw` Envoy configs | M2 | Survey Explorer Codebase |
| 5 | Docker Compose 14-Service Topology | Complete containerized bridge network deployment topology across all 14 services | M2 | Survey Explorer Codebase |
| 6 | Helm Chart Packaging & OpenShift Routes | Production Helm chart (`helm/camp-travel/`) with OpenShift Route resources and Tempo/Grafana | M2 | Survey Explorer Codebase |
| 7 | Project Hygiene & `pyproject.toml` | Python project configuration, explicit dependency specifications, and packaging metadata | M1 | Survey Explorer Codebase |
| 8 | Standalone Interactive CLI Demo Runner | Terminal-based step-by-step runner (`scripts/run_showcase.py`) executing all 5 acts with color-coded proxy diagnostics | M1 | Survey Governance Flow |
| 9 | Python Environment & Test Automation | Convenience test runner script (`run_tests.sh` / `Makefile`) with automatic `PYTHONPATH` resolution | M1 | Survey Governance Flow |
| 10 | Git Working Tree Baseline Staging | Clean review, staging, and documentation of working tree modifications | M1 | Survey Explorer Codebase |
| 11 | Baseline Multi-Agent Trip Planning | Full end-to-end trip planning across `orchestrator`, `booking-agent`, `weather-agent`, and MCP tools | M3 | Survey Governance Flow |
| 12 | Act 1: AI GW Failover & Protocol Translation | `csl-inf-rt` priority-based failover (Llama-3 -> Claude 3.5 Sonnet) and OpenAI-to-Anthropic schema translation | M3 | Survey Governance Flow |
| 13 | Act 2a: MCP Per-Tool Invocation Policy | Decoupling discovery (`tools/list`) from execution (`tools/call`); caller SPIFFE ID policy denial (`-32001`) | M3 | Survey Spec Miner |
| 14 | Act 2b: Cryptographic HITL Approval Gate | Proxy interception of state mutations (`-32003`) until valid `x-consul-hitl-evidence` (`hitl-sig-*`) is provided | M3 | Survey Spec Miner |
| 15 | Act 3: Identity Plane RFC 8693 OBO Delegation | Hop-by-hop OBO scope propagation; Sam Taylor contractor restriction (`-32002` on booking, `403` on GDS egress) | M3 | Survey Spec Miner |
| 16 | Act 4: Cycle Detection & Circuit Breaker | Runaway retry loop detection in `csl-ag-ana` tripping agent circuit breaker to `OPEN` (`-32029`), with operator reset API | M3 | Survey Spec Miner |
| 17 | Act 5: CRD Inspector & Zero-Code Telemetry | Interactive CRD inspection modal and zero-code OpenTelemetry GenAI semantic convention spans | M3 | Survey Governance Flow |
| 18 | Interactive Web Experience Polish | Real-time visual pipeline breadcrumbs, chaos toggle switch, proxy interception alerts, and circuit status pill | M3 | Survey Governance Flow |
| 19 | Comprehensive 5-Act E2E Test Suite | Automated test suite validating all 5 acts, end-to-end multi-agent orchestration, and governance contracts | M4 & E2E Track | Survey Governance Flow |
| 20 | Adversarial Coverage Hardening (Tier 5) | White-box adversarial testing, edge case stress-testing, and security robustness verification | M4 | Project Pattern |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Design comprehensive 4-tier requirement-driven E2E test suite and test runner; publish `TEST_READY.md` | none | IN_PROGRESS |
| M1 | Packaging & Dev Experience | Implement `pyproject.toml`, standalone CLI showcase runner (`scripts/run_showcase.py`), test runner script (`run_tests.sh`), and stage baseline git changes | none | DONE |
| M2 | Consul Fabric Enablement & Gateways | Validate and polish Consul 2.1 CRDs, Envoy gateway configs, Docker Compose 14-service stack, and Helm charts | M1 | IN_PROGRESS |
| M3 | Agents, MCP Tools & 5-Act Flow | Complete and polish 5-Act interactive governance demonstration flow across agents, MCP tools, and Web UI | M1, M2 | PLANNED |
| M4 | Final Milestone (E2E Pass & Hardening) | Phase 1: Pass 100% of E2E test suite (Tiers 1-4). Phase 2: Tier 5 adversarial coverage hardening | M3, E2E | PLANNED |

## Interface Contracts

### 1. `experience-ui` ↔ `travel-orchestrator` / `agents`
- **POST `/api/auth/obo-token`**:
  - Request: `{"user_id": "traveler-101" | "contractor-202"}`
  - Response: `{"token": "obo-tok-...", "user_id": "...", "name": "...", "role": "...", "scopes": ["travel:read", ...]}`
- **POST `/api/travel/plan`**:
  - Request: `{"destination": "San Francisco", "budget": 2500, "days": 4, "scenario_mode": "normal" | "act1_llm_failover" | ...}`
  - Headers: `x-consul-obo-token: ...`, `x-obo-user-id: ...`, `x-obo-scopes: ...`
  - Response: `{"trip_id": "TRIP-...", "status": "NEEDS_APPROVAL" | "CONFIRMED" | "REJECTED", "details": {...}, "telemetry": {...}}`
- **POST `/api/travel/review-action`**:
  - Request: `{"trip_id": "TRIP-...", "action": "approve" | "reject", "user_id": "traveler-101"}`
  - Response: `{"trip_id": "TRIP-...", "status": "CONFIRMED", "signature": "hitl-sig-<sha256>", "booking_confirmation": {...}}`

### 2. `travel-orchestrator` ↔ `booking-agent` & `weather-agent`
- **POST `/agent/book`** & **POST `/agent/forecast`**:
  - Headers propagated: `x-caller-spiffe-id`, `x-obo-user-id`, `x-obo-scopes`, `x-consul-obo-token`, `x-consul-hitl-evidence` (if present)
  - Scopes narrowed per hop: `weather-agent` receives `travel:read,weather:forecast`; `booking-agent` receives `travel:plan,booking:reserve` (if granted to user)

### 3. `booking-agent` / `weather-agent` ↔ MCP Tool Servers (`mcp-server`)
- **Protocol**: MCP JSON-RPC 2.0 over HTTP POST `/mcp`
- **Method `tools/list`**: Returns declared tool catalog.
- **Method `tools/call`**:
  - Body: `{"jsonrpc": "2.0", "id": "...", "method": "tools/call", "params": {"name": "<tool_name>", "arguments": {...}}}`
  - Headers: `x-caller-spiffe-id: spiffe://...`, `x-obo-user-id: ...`, `x-obo-scopes: ...`, optional `x-consul-hitl-evidence: hitl-sig-...`
  - Governance Error Returns:
    - `-32001`: Per-Tool Policy Denied (`PER_TOOL_POLICY_DENIED`)
    - `-32002`: Delegated User Authority Denied (`OBO_SCOPE_DENIED`)
    - `-32003`: Human Approval Evidence Required (`HELD_FOR_HITL_APPROVAL`)
    - `-32029`: Agent Circuit Breaker Tripped (`AGENT_CIRCUIT_OPEN`)

### 4. `travel-orchestrator` / `agents` ↔ `travel-igw` ↔ `llm-backend`
- **POST `/v1/chat/completions`**:
  - Headers: `Authorization: Bearer vault:secret/data/ai/llm#sk_99201`, optional `x-simulate-llm-outage: true`
  - Body: `{"model": "meta-llama/llama-3-70b-instruct", "messages": [...]}`
  - Response on Outage: Failover to `claude-3-5-sonnet`, `gateway_metadata: {"failover_triggered": true, "routed_model": "claude-3-5-sonnet", ...}`

### 5. `csl-nod-rly` (`otel-collector`) ↔ `csl-ag-ana` (`indigo-analytics`)
- **POST `/v1/traces`**: Ingests OTel spans, extracts GenAI attributes, enqueues to BullMQ (`consul-ai-cycle-detection`).
- **POST `/api/indigo/ingest-span`**: Ingests tool execution span into cycle analyzer.
  - Returns: `{"repetition_count": N, "circuit_state": "CLOSED" | "OPEN"}`
- **POST `/api/indigo/circuit/reset`**: Resets circuit breaker to `CLOSED`.

## Code Layout
- `frontend/`: Experience UI web application (`main.py`, `static/index.html`).
- `agents/`:
  - `agents/orchestrator/`: Master orchestrator agent (`main.py`).
  - `agents/booking_agent/`: Booking agent (`main.py`).
  - `agents/weather_agent/`: Weather agent (`main.py`).
- `mcp_tools/`:
  - `mcp_tools/hotel_booking/`: Hotel MCP tool server (`main.py`).
  - `mcp_tools/flight_booking/`: Flight MCP tool server (`main.py`).
  - `mcp_tools/weather_server/`: Weather MCP tool server (`main.py`).
  - `mcp_tools/external_mcp/`: Partner GDS external tool server (`main.py`).
- `llm_backend/`: Foundation model backend & failover runtime (`main.py`).
- `gateways/`: Envoy gateway configurations (`api_gw/`, `travel_igw/`, `terminating_gw/`).
- `observability/`:
  - `observability/otel/`: OpenTelemetry span relay (`main.py`).
  - `observability/indigo/`: Agentic Analytics cycle detection & circuit breaker (`main.py`).
- `helm/camp-travel/`: Kubernetes & OpenShift Helm chart.
- `docker-compose.yml`: 14-service Docker Compose topology.
- `tests/`: Automated test suite (`test_camp_travel.py`, `test_e2e_showcase.py`).
- `scripts/`: Operational scripts (`run_showcase.py`, `run_tests.sh`).
