# Tech News RAG

A modular Retrieval-Augmented Generation (RAG) system that extracts weekly technology news via RSS, stores embeddings in ChromaDB, and exposes a chatbot interface and admin panel through a Flask API consumed by a React frontend.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React/Vite)                    │
│   ┌─────────────────────┐      ┌──────────────────────────────┐ │
│   │   Chatbot UI /chat  │      │   Admin Panel /admin         │ │
│   └────────┬────────────┘      └──────────────┬───────────────┘ │
└────────────┼───────────────────────────────────┼────────────────┘
             │  REST (JSON)                       │  REST (JSON)
             ▼                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                        BACKEND (Flask)                          │
│   POST /api/chat              GET|PUT /api/admin/config/*       │
│   ┌──────────────┐            ┌──────────────────────────────┐  │
│   │  RAGService  │            │  AdminService                │  │
│   │  (LCEL chain)│            │  (reads/writes SQLite config)│  │
│   └──────┬───────┘            └──────────────────────────────┘  │
│          │                                                       │
│   ┌──────▼───────┐  ┌─────────────┐  ┌──────────────────────┐  │
│   │ LLMFactory   │  │ VectorStore │  │  IngestionPipeline   │  │
│   │ (reads DB on │  │ (ChromaDB)  │  │  RSS→chunk→embed     │  │
│   │  each request│  └─────────────┘  │  (weekly APScheduler)│  │
│   └──────────────┘                   └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### LLM Abstraction

The Flask backend uses a **Factory pattern** (`LLMFactory`, `EmbeddingsFactory`) that reads the current provider/model from the SQLite config table on every request. Changing the model via the Admin Panel takes effect on the next chat message — no restart required.

Raw article text is persisted in the `RawArticle` table. When the embedding model changes, re-ingestion from stored text is possible without re-fetching from RSS.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Flask + Flask-SQLAlchemy + Flask-Migrate |
| Config store | SQLite |
| LLM orchestration | LangChain (LCEL) |
| Vector database | ChromaDB |
| Ingestion scheduler | APScheduler |
| News source | RSS via `feedparser` |
| Frontend | React + Vite + TypeScript |
| HTTP client | Axios |
| State management | Zustand |

---

## Directory Structure

```
data-master-vms/
├── backend/
│   ├── app/
│   │   ├── __init__.py              # Flask app factory (create_app)
│   │   ├── config.py                # Env-based config classes
│   │   ├── extensions.py            # db, cors, migrate, scheduler singletons
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── settings.py          # LLMConfig, EmbeddingConfig, ChunkConfig,
│   │   │                            # SourceConfig, RawArticle
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py              # POST /api/chat
│   │   │   ├── admin.py             # GET|PUT /api/admin/config/*
│   │   │   └── ingestion.py         # POST /api/ingest/trigger
│   │   ├── services/
│   │   │   ├── llm_factory.py       # Provider factory (Ollama/OpenAI/Anthropic)
│   │   │   ├── embeddings_factory.py
│   │   │   ├── vector_store.py      # ChromaDB singleton + retriever builder
│   │   │   └── rag_service.py       # Assembles LCEL chain per request
│   │   └── ingestion/
│   │       ├── pipeline.py          # Orchestrates fetch → chunk → embed → store
│   │       ├── fetchers/
│   │       │   ├── base.py          # Abstract BaseFetcher
│   │       │   └── rss_fetcher.py   # feedparser implementation
│   │       └── processors/
│   │           └── chunker.py       # RecursiveCharacterTextSplitter wrapper
│   ├── db/
│   │   ├── app.db                   # SQLite (gitignored)
│   │   └── chroma/                  # ChromaDB persistence (gitignored)
│   ├── migrations/
│   ├── tests/
│   ├── .env.example
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/                # ChatWindow, MessageBubble, InputBar
│   │   │   └── admin/               # LLMConfigForm, ChunkConfigForm,
│   │   │                            # SourcesManager, IngestionPanel
│   │   ├── pages/
│   │   │   ├── ChatPage.tsx
│   │   │   └── AdminPage.tsx
│   │   ├── services/api.ts          # Axios typed wrappers
│   │   ├── store/adminStore.ts      # Zustand config state
│   │   └── App.tsx
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── .gitignore
└── README.md
```

---

## Implementation Roadmap

### Phase 1 — Backend Core ✅
*Goal: a working RAG API callable via `curl`.*

- [x] Flask app factory + extensions
- [x] SQLAlchemy models with seed defaults (`LLMConfig`, `EmbeddingConfig`, `ChunkConfig`, `SourceConfig`, `RawArticle`)
- [x] `VectorStoreService` (ChromaDB singleton)
- [x] `LLMFactory` — Ollama + OpenAI + Anthropic providers
- [x] `EmbeddingsFactory` — Ollama + OpenAI providers
- [x] `RAGService.ask()` using LCEL
- [x] `POST /api/chat` blueprint
- [x] Unit tests for factory and RAG service

**Deliverable:** `curl -X POST /api/chat -d '{"question":"..."}'` returns a grounded answer.

---

### Phase 2 — Ingestion Pipeline ✅
*Goal: tech news flows into ChromaDB automatically.*

- [x] `BaseFetcher` abstract class
- [x] `RSSFetcher` using `feedparser`, seeded with default tech RSS URLs
- [x] `Chunker` wrapping `RecursiveCharacterTextSplitter`
- [x] `IngestionPipeline.run()` — fetch → chunk → embed → persist (`RawArticle` + ChromaDB)
- [x] APScheduler wired into app factory for weekly runs (every Sunday 00:00 UTC)
- [x] `POST /api/ingest/trigger` — non-blocking, returns job status (202) or 409 if already running
- [x] `GET /api/ingest/status` — last run details + total article count + next scheduled run

**Deliverable:** Vector store populates automatically every week; admin can also trigger manually.

---

### Phase 3 — Admin Config API ✅
*Goal: every system parameter is configurable via REST.*

- [x] `GET /api/admin/config` — returns full current config (LLM, embedding, chunk); API keys never exposed
- [x] `PUT /api/admin/config/llm` — updates `LLMConfig`; validates provider, temperature range, required fields
- [x] `PUT /api/admin/config/embedding` — updates `EmbeddingConfig`; if model changed and articles exist, triggers async re-embedding job (202) from `RawArticle`
- [x] `PUT /api/admin/config/chunk` — updates `ChunkConfig`; validates overlap < size
- [x] `GET|POST|PATCH|DELETE /api/admin/sources` — full CRUD on `SourceConfig`; delete nullifies FK on articles
- [x] Request validation with `marshmallow` schemas (422 on invalid input)
- [x] All admin endpoints protected by `X-Admin-Key` header (401 without it)

**Deliverable:** Full system configurable without touching files or restarting.

---

### Phase 4 — React Chatbot UI ✅
*Goal: users interact through a browser.*

- [x] Scaffold Vite + React + TypeScript (Node 20 LTS, Vite 6)
- [x] Axios typed wrapper (`ApiError` class), `/api` proxy in dev via `vite.config.ts`
- [x] `ChatWindow` (auto-scroll, ARIA live region), `MessageBubble` (user/assistant styles, sources), `InputBar` (auto-grow textarea, Enter to send)
- [x] Source citations with clickable links and publication dates below each answer
- [x] Loading animation (three-dot bounce) while awaiting LLM response
- [x] React Router scaffold ready for Phase 5 admin route

**Deliverable:** Functional browser chat backed by Phase 1 API.

---

### Phase 5 — React Admin Panel
*Goal: non-technical admins manage the whole system.*

- [ ] Tabbed `AdminPage` (LLM / Embedding / Chunking / Sources / Ingestion)
- [ ] `LLMConfigForm` — provider dropdown, model name, temperature slider
- [ ] `ChunkConfigForm` — chunk size, overlap, k-retrievals
- [ ] `SourcesManager` — RSS URL table with add/delete
- [ ] `IngestionPanel` — "Run Now" + last-run status

**Deliverable:** Full admin panel managing all system parameters.

---

### Phase 6 — Hardening
*Non-negotiable before any real deployment.*

- [ ] Admin endpoints protected by API key middleware
- [ ] Rate limiting on `/api/chat` via `Flask-Limiter`
- [ ] Structured logging with `structlog`
- [ ] CORS restricted to frontend origin
- [ ] `docker-compose.yml` for single-command local orchestration

---

## Getting Started

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
flask db upgrade
python run.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```
