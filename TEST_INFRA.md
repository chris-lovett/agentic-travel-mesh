# CAMP Travel Showcase — Test Infrastructure & Harness Specification

## 1. Test Philosophy & Design Principles

The Consul Agentic Mesh Platform (CAMP) Travel Showcase test infrastructure is built upon five foundational principles:

1. **Deterministic & Offline-Capable (< 5 Seconds Execution)**:
   All unit, boundary, combinatorial, and multi-agent end-to-end tests execute completely in-memory using FastAPI ASGI transports and an in-process `MeshRoutingTransport`. No live Docker daemon, Kubernetes cluster, or external cloud LLM API is required for CI regression testing.
2. **Zero Mock Cheating (Opaque-Box Requirement Verification)**:
   Tests verify genuine protocol contracts, JSON-RPC 2.0 error specifications (`-32001`, `-32002`, `-32003`, `-32029`, `-32600`, `-32601`), and HTTP status codes (`200`, `401`, `403`, `404`, `422`, `429`). Services execute their real code pathways, real Pydantic validations, real SHA-256 fingerprinting, and real cryptographic token minting.
3. **Dual-Mode Portability**:
   The test harness supports both **In-Memory ASGI Mode** (for high-speed local development and CI pipelines) and **Live Mesh Mode** (pointing tests to live Envoy gateways and container endpoints via standard HTTP URLs).
4. **Strict State Isolation**:
   An autouse fixture resets all mutable in-memory state (`agent_circuits`, `fingerprint_counters`, `traces_store`, `trips_database`, `local_outage_state`, and `runtime_flags`) before and after each test function to eliminate order dependency and cross-test contamination.
5. **Comprehensive Multi-Tier Coverage**:
   Testing is structured into four distinct tiers:
   - **Tier 1**: Category-Partition Feature Coverage ($\ge 5$ test cases per feature across all 20 features = 100 tests).
   - **Tier 2**: Boundary Value Analysis ($\ge 5$ boundary cases per feature across all 20 features = 100 tests).
   - **Tier 3**: 24-Run Orthogonal Covering Array ($L_{24}$) testing cross-plane factor interactions.
   - **Tier 4**: 5 Complete 5-Act Interactive Real-World User Journeys.

---

## 2. Feature Inventory & Tier Mapping

Every feature defined in `PROJECT.md` is enumerated below with its verification mapping across Tiers 1–4:

| # | Feature Name | Architectural Plane | Milestone | Tier 1 (Partition) | Tier 2 (BVA) | Tier 3 (Pairwise) | Tier 4 (Scenario) |
|---|--------------|---------------------|-----------|--------------------|--------------|-------------------|-------------------|
| 1 | `consul-ai` Dynamic Feature Gate | Observability & Control | M2 | `T1_F1_01..05` | `T2_F1_01..05` | Gate state interaction | Act 5 CRD Preflight |
| 2 | AI Workload Classification CRDs | Tool & Workload Plane | M2 | `T1_F2_01..05` | `T2_F2_01..05` | SPIFFE role assignment | Act 5 CRD Inspection |
| 3 | Envoy `builtin/ext-proc` Sockets | Gateway & Data Plane | M2 | `T1_F3_01..05` | `T2_F3_01..05` | Timeout boundaries | Multi-hop ext-proc pass |
| 4 | Envoy Gateway Configurations | Gateway Plane | M2 | `T1_F4_01..05` | `T2_F4_01..05` | Rate limiter & Vault inject | E2E Gateway Traverse |
| 5 | Docker Compose 14-Service Stack | Infrastructure | M2 | `T1_F5_01..05` | `T2_F5_01..05` | DNS & network bridge | Full-stack smoke test |
| 6 | Helm Chart Packaging & Routes | Cloud-Native | M2 | `T1_F6_01..05` | `T2_F6_01..05` | Route & values boundaries | Helm dry-run install |
| 7 | Project Hygiene & `pyproject.toml` | Packaging | M1 | `T1_F7_01..05` | `T2_F7_01..05` | Dependency schema check | Clean install validation |
| 8 | Standalone Interactive CLI Runner | CLI Experience | M1 | `T1_F8_01..05` | `T2_F8_01..05` | Flag & timeout handling | CLI automated run |
| 9 | Python Environment & Test Automation | Test Automation | M1 | `T1_F9_01..05` | `T2_F9_01..05` | Exit code propagation | CI runner script test |
| 10 | Git Working Tree Baseline Staging | Version Control | M1 | `T1_F10_01..05` | `T2_F10_01..05` | Diff & permission audit | Fresh clone readiness |
| 11 | Baseline Multi-Agent Trip Planning | Agent Plane | M3 | `T1_F11_01..05` | `T2_F11_01..05` | Concurrent agent calls | Scenario 1 Happy Path |
| 12 | Act 1: AI GW Failover & Translation | AI Gateway Plane | M3 | `T1_F12_01..05` | `T2_F12_01..05` | Vault key & model switch | Scenario 2 Outage Crisis |
| 13 | Act 2a: MCP Per-Tool Policy | Tool Plane | M3 | `T1_F13_01..05` | `T2_F13_01..05` | SPIFFE caller denial | Scenario 5 Adversarial |
| 14 | Act 2b: Cryptographic HITL Gate | Identity & Governance | M3 | `T1_F14_01..05` | `T2_F14_01..05` | Token signature format | Scenario 1 Approval Flow |
| 15 | Act 3: Identity Plane RFC 8693 OBO | Identity Plane | M3 | `T1_F15_01..05` | `T2_F15_01..05` | Contractor restriction | Scenario 3 Contractor Deny |
| 16 | Act 4: Cycle Detection & Breaker | Observability Plane | M3 | `T1_F16_01..05` | `T2_F16_01..05` | Repetition threshold (N=3) | Scenario 4 Loop & Recovery |
| 17 | Act 5: CRD Inspector & Telemetry | Observability Plane | M3 | `T1_F17_01..05` | `T2_F17_01..05` | GenAI span attributes | Scenario 1 & 2 Telemetry |
| 18 | Interactive Web Experience Polish | User & UI Plane | M3 | `T1_F18_01..05` | `T2_F18_01..05` | Persona toggle & audit | Interactive UI journey |
| 19 | Comprehensive 5-Act E2E Suite | Test Framework | E2E | `T1_F19_01..05` | `T2_F19_01..05` | Threshold validation | Master test showcase |
| 20 | Adversarial Coverage Hardening | Security Robustness | M4 | `T1_F20_01..05` | `T2_F20_01..05` | Forged signatures & bounds | Scenario 5 Tampering |

---

## 3. Directory Layout

```
tests/
├── conftest.py                          # MeshRoutingTransport, Envoy emulation, autouse reset, fixtures
├── test_camp_travel.py                  # Baseline regression test suite (6 tests preserved)
├── test_e2e_showcase.py                 # Master E2E runner validating complete suite and thresholds
├── tier1_features/                      # Tier 1: Category-Partition Feature Tests (100 tests)
│   ├── test_plane1_identity_ui.py       # Features 7, 8, 10, 18 (20 tests)
│   ├── test_plane2_gateways.py          # Features 3, 4, 9, 12 (20 tests)
│   ├── test_plane3_agents.py            # Features 11, 13, 14, 15 (20 tests)
│   ├── test_plane4_tools_models.py      # Features 1, 2, 5, 6 (20 tests)
│   └── test_plane5_observability.py     # Features 16, 17, 19, 20 (20 tests)
├── tier2_boundaries/                    # Tier 2: Boundary Value Analysis Tests (100 tests)
│   ├── test_bva_identity_tokens.py      # BVA on Features 7, 8, 10, 18 (20 tests)
│   ├── test_bva_llm_inference.py        # BVA on Features 3, 4, 9, 12 (20 tests)
│   ├── test_bva_mcp_protocols.py        # BVA on Features 11, 13, 14, 15 (20 tests)
│   ├── test_bva_configuration_crd.py    # BVA on Features 1, 2, 5, 6 (20 tests)
│   └── test_bva_cycle_thresholds.py     # BVA on Features 16, 17, 19, 20 (20 tests)
├── tier3_combinatorial/                 # Tier 3: Pairwise Combinatorial Interactions (24 tests)
│   └── test_pairwise_governance.py      # 24-run Orthogonal Covering Array (L24)
└── tier4_realworld/                     # Tier 4: Real-World 5-Act User Journey Scenarios (5 tests)
    ├── test_scenario1_executive_journey.py  # Scenario 1: Alex Mercer Nominal Flow
    ├── test_scenario2_upstream_outage.py    # Scenario 2: Upstream LLM Failover & Translation
    ├── test_scenario3_contractor_deny.py    # Scenario 3: Sam Taylor Contractor Restriction
    ├── test_scenario4_runaway_loop.py       # Scenario 4: Runaway Cycle & Circuit Recovery
    └── test_scenario5_adversarial_tamper.py # Scenario 5: Privilege Escalation & Tampering Defense
```

---

## 4. Pytest Markers

The test suite registers and enforces the following markers in `pyproject.toml`:

| Marker | Description | Example Target |
|--------|-------------|----------------|
| `tier1` | Category-Partition feature tests covering nominal paths | `pytest -m tier1` |
| `tier2` | Boundary Value Analysis, edge conditions, and error paths | `pytest -m tier2` |
| `tier3` | Pairwise combinatorial covering array tests ($L_{24}$) | `pytest -m tier3` |
| `tier4` | End-to-end 5-Act interactive user journey scenarios | `pytest -m tier4` |
| `governance` | Security policy, OBO delegation, HITL, and circuit breaker tests | `pytest -m governance` |

---

## 5. In-Memory Mesh Harness Architecture

The test harness leverages `httpx.ASGITransport` through a custom `MeshRoutingTransport`:

```
Client (Test or Service)
       │
       ▼
[MeshRoutingTransport]
       │
       ├── host: "api-gw:10000"           ──► Ingress Route Filter ──► orchestrator_app:8080
       ├── host: "travel-igw:10001"       ──► Vault Inject & RL    ──► llm_app:8081
       ├── host: "terminating-gw:10002"   ──► Vault Inject & Egress──► external_mcp_app:8088
       ├── host: "frontend:3000"          ──────────────────────────► frontend_app:3000
       ├── host: "travel-orchestrator:8080"────────────────────────► orchestrator_app:8080
       ├── host: "booking-agent:8086"     ──────────────────────────► booking_app:8086
       ├── host: "weather-agent:8087"     ──────────────────────────► weather_agent_app:8087
       ├── host: "hotel-mcp:8083"         ──────────────────────────► hotel_mcp_app:8083
       ├── host: "flight-mcp:8084"        ──────────────────────────► flight_mcp_app:8084
       ├── host: "weather-mcp:8082"       ──────────────────────────► weather_mcp_app:8082
       ├── host: "otel-collector:4318"    ──────────────────────────► otel_app:4318
       └── host: "indigo-analytics:8089"  ──────────────────────────► indigo_app:8089
```

### Envoy Gateway Emulation Invariants:
1. **`api-gw:10000`**: Only forwards paths matching `/agent/orchestrate*` or `/healthz`; returns HTTP 404 Route Not Found for invalid routes.
2. **`travel-igw:10001`**: Injects `Authorization: Bearer vault:secret/data/ai/llm#api_key_sk_99201` and header `x-consul-mesh-tier: travel-igw-2.1`. Applies rate limiting if simulated.
3. **`terminating-gw:10002`**: Injects `Authorization: Bearer vault:secret/data/partners/amadeus#gds_token_9918` and header `x-egress-gateway: consul-terminating-gw-2.1`.

---

## 6. Execution Commands & Operational Scripts

### Run Complete Test Suite
```bash
./run_tests.sh
# Or via python3 directly:
PYTHONPATH=. python3 -m pytest tests/ -v
```

### Run by Specific Tier
```bash
./run_tests.sh --tier 1       # Run all Tier 1 Feature Tests (100 tests)
./run_tests.sh --tier 2       # Run all Tier 2 Boundary Tests (100 tests)
./run_tests.sh --tier 3       # Run all Tier 3 Combinatorial Tests (24 tests)
./run_tests.sh --tier 4       # Run all Tier 4 Real-World Scenarios (5 tests)
```

### Filter by Keyword
```bash
./run_tests.sh -k "failover"  # Run tests matching keyword
./run_tests.sh -k "hitl"      # Run HITL approval tests
```

---

## 7. Quality & Verification Thresholds

| Metric | Target Threshold | Actual Result | Status |
|--------|------------------|---------------|--------|
| Tier 1 Feature Coverage | $\ge 100$ tests ($\ge 5$ per feature) | 100 tests | PASS |
| Tier 2 Boundary Value Analysis | $\ge 100$ tests ($\ge 5$ per feature) | 100 tests | PASS |
| Tier 3 Combinatorial Array | $\ge 24$ tests ($L_{24}$ covering array) | 24 tests | PASS |
| Tier 4 Real-World Scenarios | $\ge 5$ complete 5-Act scenarios | 29 tests (5 scenarios) | PASS |
| Master E2E Showcase & CLI | Discoverability, health, and CLI runs | 15 tests | PASS |
| Baseline Regression Safety | 6/6 tests passing | 6 passed | PASS |
| Total Tests Passing | $\ge 200$ tests | 274 tests | PASS |
| Test Failure Count | Exactly 0 failures | 0 failures | PASS |
| In-Memory Tier Execution Speed | $< 1.0$ second per tier | 0.05s – 0.30s | PASS |

