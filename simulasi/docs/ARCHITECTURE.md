# Arsitektur Simulasi Sidang MK

## Overview

Simulasi JR adalah sistem AI untuk mensimulasikan sidang pengujian undang-undang (PUU) di Mahkamah Konstitusi RI. Sistem ini terdiri dari 3 layer utama:

```
┌─────────────────────────────────────────────┐
│              Frontend (React/TS)            │
│         simulasi/frontend/ atau static/     │
├─────────────────────────────────────────────┤
│            Backend API (FastAPI)            │
│              simulasi/server.py             │
├─────────────────────────────────────────────┤
│        Core Engine (Python + LLM)          │
│  simulasi/core/   simulasi/rag/            │
└─────────────────────────────────────────────┘
```

## Module Structure

```
simulasi/
├── core/                          # Core simulation engine
│   ├── __init__.py
│   ├── llm_client.py              # LLM client config (OpenAI, OpenRouter, Claude)
│   ├── system_prompts.py          # All system prompts for agents
│   ├── agents.py                  # Agent classes (BaseAgent + role-specific agents)
│   ├── orchestrator.py            # Simulation orchestrator (round management)
│   ├── preprocessor.py            # Draft preprocessor
│   ├── draft_reviser.py           # Draft revision agent
│   ├── self_correcting_loop.py    # Auto-correct loop for draft improvement
│   └── utils.py                   # Utility functions
│
├── rag/                           # RAG pipeline
│   ├── extract_and_chunk.py       # PDF → chunks (extract_and_chunk.py)
│   ├── create_vector_db.py        # Chunks → ChromaDB vector store
│   ├── retriever.py               # RAG retriever (semantic + keyword + reranking)
│   ├── pipeline_utils.py          # Shared pipeline utilities
│   ├── ratio_pipeline.py          # Agent 2: Ratio extraction
│   ├── attack_bank_pipeline.py    # Agent 3: Government attack patterns
│   ├── judge_concern_pipeline.py  # Agent 4: Judge concern patterns
│   ├── survive_pipeline.py        # Agent 5: Survive extraction
│   ├── pasal_api.py               # Pasal/article API
│   ├── prompts/                   # Prompt templates for all 7 agents
│   │   ├── agent1_classifier.txt
│   │   ├── agent2_ratio_extractor.txt
│   │   ├── agent3_attack_bank.txt
│   │   ├── agent4_judge_concern.txt
│   │   ├── agent5_survive_extractor.txt
│   │   ├── agent6_petition_blueprint.txt
│   │   ├── agent7_hearing_playbook.txt
│   │   └── draft_reviser.txt
│   └── scratch/                   # Analysis scripts
│
├── tests/                         # Unit tests (pytest)
│   ├── __init__.py
│   ├── conftest.py                # Test fixtures
│   └── test_agents.py             # Agent unit tests
│
├── frontend/                      # React/TypeScript frontend
│   ├── src/
│   │   ├── App.tsx                # Main application component
│   │   ├── types.ts               # TypeScript type definitions
│   │   ├── hooks/useApi.ts        # API hooks (SSE streaming)
│   │   └── components/            # UI components
│   ├── index.html
│   └── vite.config.ts
│
├── static/                        # Legacy vanilla HTML/CSS/JS fallback
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── server.py                      # FastAPI backend (SSE streaming)
├── main.py                        # CLI entry point
├── config.yaml                    # Central configuration
├── .env.example                   # Environment variables template
└── requirements.txt               # Python dependencies
```

## Core Module: `core/`

### `llm_client.py` — LLM Client Configuration
- **LLM_BASE_URL, LLM_API_KEY, MODEL_NAME**: Environment-based config
- **client**: Shared AsyncOpenAI singleton for local provider
- **_openrouter_provider_route()**: Provider-specific routing for OpenRouter

### `system_prompts.py` — System Prompts
Semua system prompt untuk 10+ agent roles dipisahkan di sini agar mudah diedit tanpa menyentuh logika:
- SYSTEM_PROMPT_PEMOHON, SYSTEM_PROMPT_PEMERINTAH, SYSTEM_PROMPT_HAKIM
- SYSTEM_PROMPT_PIHAK_TERKAIT, SYSTEM_PROMPT_AMICUS_CURIAE
- SYSTEM_PROMPT_AHLI_PEMOHON, SYSTEM_PROMPT_AHLI_PEMERINTAH
- SYSTEM_PROMPT_VALIDATOR, SYSTEM_PROMPT_JUDICIAL_REVIEW_DRAFT

### `agents.py` — Agent Classes
- **BaseAgent**: Base class dengan sliding window memory, thinking filter, word limiter, usage tracking
- **PemohonAgent, PemerintahAgent, HakimAgent**: Agen utama sidang
- **PihakTerkaitAgent, AmicusCuriaeAgent, AhliPemohonAgent, AhliPemerintahAgent**: Agen pendukung
- **ValidatorAgent**: Anti-hallucination citation checker (regex + LLM)
- **JudicialReviewDraftAgent**: Legal drafter untuk revisi naskah permohonan

### `orchestrator.py` — Simulation Orchestrator
Mengelola jalannya simulasi:
- Fase 1: Pendahuluan (Pemohon, Pemerintah, Hakim)
- Fase 2: Jawab-Menjawab
- Fase 2B: Nota Keberatan
- Fase 3: Pembuktian (Ahli, Pihak Terkait, Amicus Curiae)
- Fase 4: Kesimpulan & Amar Putusan

## RAG Pipeline: `rag/`

### Data Flow
```
PDF files → extract_and_chunk.py → rag_chunks.jsonl → create_vector_db.py → ChromaDB
                                                                              ↓
                              7-agent pipeline (ratio, attack, judge, survive, etc.)
                                                                              ↓
                                                         Intelligence Banks (JSON)
```

### Pipeline Stages
1. **Agent 1 (Classifier)**: Klasifikasi dokumen (norma_diuji, batu_uji, amar, klaster)
2. **Agent 2 (Ratio Extractor)**: Ekstraksi ratio decidendi dari putusan
3. **Agent 3 (Attack Bank)**: Pola serangan Pemerintah yang konsisten
4. **Agent 4 (Judge Concern)**: Concern/pertanyaan kritis Hakim
5. **Agent 5 (Survive Extractor)**: Formulasi Pemohon yang survive
6. **Agent 6 (Petition Blueprint)**: Template naskah permohonan
7. **Agent 7 (Hearing Playbook)**: Strategi sidang

## Import Dependencies

```
preprocessor.py ──→ agents.py ──→ llm_client.py
                      ↑               ↑
orchestrator.py ──────┘               │
server.py ────────────┘               │
                                      │
draft_reviser.py ──→ agents.py ──→ system_prompts.py
```

Backward compatibility: `agents.py` re-exports `client`, `MODEL_NAME`, `LLM_BASE_URL` dari `llm_client.py` sehingga import lama dari `preprocessor.py` tetap bekerja.

## Testing

```bash
# Run all tests
python -m pytest simulasi/tests/ -v

# Run specific test file
python -m pytest simulasi/tests/test_agents.py -v

# Run with coverage
python -m pytest simulasi/tests/ -v --tb=short
```

49 unit tests mencakup:
- Agent initialization (14 tests)
- Memory management / sliding window (5 tests)
- Thinking filter (11 tests)
- Streaming filter (7 tests)
- Validator regex (7 tests)
- Backward compatibility imports (5 tests)

## Running the Application

### Backend
```bash
cd simulasi
python server.py              # FastAPI on port 8000
# or
python main.py                # CLI mode
```

### Frontend (React)
```bash
cd simulasi/frontend
npm install
npm run dev                   # Vite dev server
```

### Static Fallback
Access `simulasi/static/index.html` directly for vanilla HTML/CSS/JS version.

## Configuration

All config in `simulasi/config.yaml` and `simulasi/.env`:
- LLM provider selection (local / openrouter / claude)
- Model name and API keys
- Scoring weights
- RAG parameters