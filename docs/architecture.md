# AssistGen Architecture

## Project Positioning

AssistGen is a small but polished multi-agent ecommerce shopping assistant.

Draw.io architecture diagram:

```text
docs/assistgen_architecture.drawio
```

It is not a pure FAQ chatbot. The system is designed around:

- understanding shopping intent and constraints
- retrieving relevant products
- recommending related products through product relations
- explaining recommendations in buyer-friendly language
- using a Critic gate to prevent bad, robotic, or constraint-breaking answers
- exposing Agent execution progress for learning and portfolio demonstration

## Current Status

V2 is complete.

V3 Memory & Context Management is complete, including:
- Redis/InMemory session store
- frontend `session_id` via `localStorage`
- `shopping_state`, `effective_query`, per-agent memory views
- LLM structured compression (>6 messages)
- SSE `compressing` / `compressed` events
- frontend `正在整理上下文...` status display
- new-chat button wired to `newChatSession()`

V3 remaining (optional / future):
- developer memory debug panel (not for normal users)

## Main Runtime Flow

```text
User
  -> Memory Layer
  -> Query Understanding Layer
  -> Supervisor Agent
  -> Retrieval Agent
  -> Recommendation Agent
  -> Explanation Agent
  -> Critic Agent
  -> Final Answer
```

## Agent Responsibilities

### Memory Layer

Memory is a layer, not an Agent.

Responsibilities:

- load short-term session memory
- merge current query with previous shopping context
- maintain `shopping_state`
- build `effective_query`
- build per-agent memory views
- save updated memory after the response

Current implementation:

- Redis-first `SessionMemoryStore`
- automatic `InMemorySessionStore` fallback
- frontend-generated `session_id`
- per-agent memory views in `views.py`

Deferred:

- LLM structured compression after long sessions
- frontend compression status display

### Query Understanding Layer

Query Understanding is a deterministic perception layer before Supervisor.

Responsibilities:

- detect purchase intent
- extract budget
- extract ranking objective, such as `lowest_price`, `best_value`, `premium`
- detect product categories
- detect support / complaint intent

It prevents simple ecommerce queries from being misrouted to casual chat.

### Supervisor Agent

Supervisor owns orchestration and routing.

Responsibilities:

- decide whether the request is chat, support, retrieval, recommendation, or clarification
- use Query Understanding and Memory context instead of relying only on LLM intuition
- suppress selling behavior in complaint/refund scenarios

### Retrieval Agent

Retrieval is a complete RAG-style product retrieval pipeline.

Responsibilities:

- dense retrieval from Qdrant
- sparse retrieval with BM25
- metadata filtering
- score fusion
- DashScope `gte-rerank-v2` reranking when configured
- safe fallback when Qdrant or reranker is unavailable

Current embedding provider:

- DashScope `text-embedding-v4`
- dimension: 512

Current Qdrant collections:

- `assistgen_products`
- `assistgen_explanation_evidence`

### Recommendation Agent

Recommendation uses product-graph relations, not GraphRAG, to decide related products.

Responsibilities:

- use selected main products as anchors
- find one-hop product relations from the product graph
- rank by relation type, graph weight, business weight, stock, budget fit, and user preferences
- avoid repeated or rejected products where memory provides that signal

Current relation examples:

- `COMPLEMENTS`
- `BOUGHT_WITH`
- `CONSUMABLE`
- `UPGRADE`
- `SAME_SCENE`
- `BUNDLE`
- `SUBSTITUTE`

### Explanation Agent

Explanation explains selected products and selected relations.

Responsibilities:

- explain why the recommendation fits the user's needs
- use lightweight GraphRAG-style evidence from Qdrant when available
- use structured relation tags when Qdrant is unavailable
- never invent products outside the selected candidates/recommendations

Important boundary:

GraphRAG-style explanation is not the recommender. Recommendation Agent owns product selection.

### Critic Agent

Critic is the final quality gate.

Responsibilities:

- check factual grounding
- check budget and hard constraints
- check primary recommendation vs explanation consistency
- check recommendation strategy fit
- check formatting readability
- check human tone
- block or rewrite when needed

Critic should not rely only on prompt-based LLM judgment. Deterministic checks are the foundation.

## Infrastructure

### Qdrant

Current local setup:

```text
Binary: L:\AssistGen\.tools\qdrant\bin\qdrant.exe
Config: L:\AssistGen\.tools\qdrant\config.yaml
Data:   L:\AssistGen\.data\qdrant
URL:    http://localhost:6333
```

Local development uses standalone Qdrant on L drive.

Future CI / standard deployment should use Docker Qdrant.

### Redis

Redis is preferred for short-term session memory but is not a hard local dependency.

Fallback:

```text
Redis unavailable -> InMemorySessionStore
```

This keeps local development unblocked while Docker/Redis setup is unstable.

### Neo4j

Neo4j is retained for graph database capability and future complex graph queries.

Text2Cypher is not part of the default main path. It remains a hidden fallback for:

- explicit graph query intent
- complex multi-hop relationship queries
- normal retrieval failure

### LLM / Embedding / Reranker

Current model-related integrations:

- DeepSeek-compatible chat model for Agent reasoning and answer generation
- DashScope `text-embedding-v4` for product/evidence vectors
- DashScope `gte-rerank-v2` for reranking

No API keys should be printed or committed.

## Observability

AssistGen has two observability layers:

- backend Agent Trace Console controlled by `AGENT_TRACE=true`
- frontend SSE stage streaming for user/developer-visible progress

Trace should show summaries only, never full prompts, API keys, or large raw memory dumps.

## Key Design Boundaries

- Do not add Agents just to make the architecture look richer.
- Memory is a layer, not a Memory Agent.
- Ranking belongs inside Retrieval/Recommendation, not a separate Ranking Agent.
- Product recommendation is decided by product retrieval and product graph logic.
- GraphRAG-style logic explains recommendations; it does not choose products.
- Critic is a quality gate, not a decorative reviewer.
- Prefer structural fixes and tests over one-off prompt patches.

## V3 Memory Architecture

See `docs/v3_memory_architecture.md` for the dedicated memory-layer design.
