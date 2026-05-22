# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI-driven high-agency RPG engine prototype. Creative reasoning is done by a supervised
multi-agent layer; the runtime substrate stays deterministic, auditable, and validatable.
The full design lives in `docs/superpowers/specs/2026-05-22-multi-agent-rpg-framework-design.md`
(in Chinese) — read it before large changes.

Python 3.11+, `src/` layout. The package directory `src/` must be on `PYTHONPATH` for
imports like `from core...` / `from game...` / `from main import ...` to resolve.

## Commands

```bash
pip install -e ".[dev]"          # base + pytest/pytest-asyncio
pip install -e ".[dev,rag]"      # add chromadb (optional, for ChromaRAGRepository)

python -m pytest                                   # full suite (pytest.ini_options sets pythonpath + asyncio)
python -m pytest tests/test_world_init_workflow.py  # one file
python -m pytest tests/test_llm_gateway.py::test_name -q   # one test

# Scripts and the MVP entrypoint need src/ on the path:
PYTHONPATH=src python -m main --answer "..."          # offline-safe? no — calls live LLM
PYTHONPATH=src python scripts/live_world_init.py --live   # full world-init pass against the LLM
PYTHONPATH=src python scripts/smoke_mimo_gateway.py       # provider connectivity check
PYTHONPATH=src python scripts/check_chroma_repository.py  # Chroma persistence check (needs [rag])
```

Tests run fully offline — `LLMGateway` is exercised via an injected `httpx` transport, never
the real provider. Scripts and `main` hit the live MIMO provider and need credentials.

## Configuration

`AppSettings` (`src/core/config.py`) reads `.env` then `.env.local` (both gitignored).
`MIMO_API_KEY` is required for any live call; `MIMO_BASE_URL`/`MIMO_MODEL` have defaults.
Copy `.env.example` to `.env.local`. Live entrypoints raise `SystemExit` if the key is missing.

## Architecture

The system is a validate-then-commit pipeline. Agents only propose; `core/` decides.

**Iron rules (enforce these in every change):**
1. `core/` is fully decoupled from game content — only generic concepts (node, event,
   memory, task, agent, schema, state, change). Domain entities (world law, character,
   faction, combat) live only in `game/`.
2. Agents never mutate world state directly — they emit proposals; only accepted
   proposals reach storage or RAG.
3. Every LLM output is Pydantic-validated. On failure the gateway re-prompts with the
   error; after retries it raises a controlled error rather than letting hallucination through.
4. RAG is the world blackboard — long-term memory, world laws, history, causal packets
   all persist as structured `MemoryFragment`s.

**Core layer (`src/core/`)**
- `llm_gateway.py` — `LLMGateway` over an OpenAI-compatible API. `complete()` retries and
  auto-doubles `max_tokens` when reasoning-only `length` truncation is detected.
  `complete_and_parse()` validates against a Pydantic schema and, on failure, re-prompts with
  the validation error + JSON schema (`_with_validation_feedback`) before giving up with
  `GatewaySchemaError`. `extract_json` strips code fences / locates the JSON span.
- `schemas.py` — generic primitives: `Message`, `LLMRequest/Response`, `ThinkingPolicy`
  (`disabled|auto|enabled`), `MemoryFragment`, `RAGQueryResult`, `TickEvent`, `SimulationNode`.
- `rag_repository.py` — `UniversalRAGRepository` Protocol with two implementations:
  `InMemoryRAGRepository` (cosine over term counts) and `ChromaRAGRepository` (persistent,
  uses a deterministic hashed-text embedding, not a learned model).
- `agents/runtime.py` — `AgentRuntime.run_agent(profile, task, schema)` builds the
  system/user messages from an `AgentProfile` + `AgentTask` and delegates to the gateway.
- `agents/debate.py` — `DebateSession` runs each profile once and collects `DebateTurn`s.

**Game layer (`src/game/world_init/`)** — the MVP "world initialization" closed loop:
`workflow.py` `WorldInitWorkflow.run()` chains: Debate agents (Expander / Critic /
Drama Designer) → Synthesizer → `WorldSeedCandidate` → Canon Guard (`accept`/`revise`/
`reject` — non-accept currently raises) → `WorldSeed` → Causality Analyzer →
`CausalImpactPacket`. `agents.py` defines profiles, `prompts.py` builds tasks,
`schemas.py` holds domain schemas, `memory.py` converts seeds/packets to `MemoryFragment`s.

**Entrypoint** — `src/main.py` `run_world_init_mvp()` runs the workflow then upserts the
resulting fragments into a RAG repository.

When adding new `core/` Protocols, prefer the existing pattern: a `Protocol` interface plus
concrete impls, dependency-injected (see `StructuredGateway`, `UniversalRAGRepository`).
