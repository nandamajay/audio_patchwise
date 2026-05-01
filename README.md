<div align="center">

# 🏛️ PatchWise
### *Ancient Wisdom Meets Modern AI*

[![CI Status](https://github.com/nandamajay/patchwise/actions/workflows/dev-ci.yml/badge.svg)](https://github.com/nandamajay/patchwise/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![React 18](https://img.shields.io/badge/react-18-61DAFB.svg)](https://reactjs.org/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](https://www.docker.com/)

```
 ██████╗██╗  ██╗ █████╗ ███╗   ██╗ █████╗ ██╗  ██╗██╗   ██╗ █████╗
██╔════╝██║  ██║██╔══██╗████╗  ██║██╔══██╗██║ ██╔╝╚██╗ ██╔╝██╔══██╗
██║     ███████║███████║██╔██╗ ██║███████║█████╔╝  ╚████╔╝ ███████║
██║     ██╔══██║██╔══██║██║╚██╗██║██╔══██║██╔═██╗   ╚██╔╝  ██╔══██║
╚██████╗██║  ██║██║  ██║██║ ╚████║██║  ██║██║  ██╗   ██║   ██║  ██║
 ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝
```

**An autonomous A2A (Agent-to-Agent) patch review system powered by CHANAKYA (Reviewer) and ARYABHATA (Developer)**

[Quick Start](#quick-start) • [Architecture](#architecture) • [Usage](#usage) • [Configuration](#configuration) • [Contributing](#contributing)

</div>

---

## 🎯 What is PatchWise?

PatchWise is a **standalone autonomous A2A patch review system** focused on the **Linux Audio (ALSA/ASoC) subsystem**. It uses two AI agents that work together in a closed loop:

| Agent | Role | Personality |
|---|---|---|
| 🔍 **CHANAKYA** (Reviewer) | Analyses patches, flags issues, searches LKML for similar patches | Master strategist — questions everything |
| 🛠️ **ARYABHATA** (Developer) | Applies fixes, justifies changes, iterates until LGTM | Precision solver — computes the exact fix |

### Key Features
- 🔁 **Autonomous loop** — agents iterate up to 5 rounds or until CHANAKYA says LGTM
- 🌊 **Token-by-token streaming** — watch agents think in real time
- 🧠 **Learning knowledge base** — pre-seeded with ALSA/ASoC LKML history + continuous learning
- 💬 **Soft interrupt** — inject hints mid-loop without breaking the flow
- 📊 **Monaco diff view** — side-by-side original vs fixed patch
- 🚀 **Submit to Gerrit / GitHub / Upstream** with manual approval gate

---

## ⚡ Quick Start

### Prerequisites
- Docker & Docker Compose
- Git
- 4GB RAM minimum

### 1. Clone the repository
```bash
git clone https://github.com/nandamajay/patchwise.git
cd patchwise
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your API keys and config
nano .env
```

### 3. Start PatchWise
```bash
chmod +x run.sh
./run.sh start
```

### 4. Pre-seed knowledge base (first time only)
```bash
./run.sh seed
# This crawls ALSA/ASoC patches from lore.kernel.org (~5000 patches, takes ~10 mins)
```

### 5. Open in browser
```
http://localhost:3000
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    PatchWise UI (React)                  │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────┐ │
│  │ Input Page  │  │  Agent Chat UI   │  │ Diff + Out │ │
│  └─────────────┘  └──────────────────┘  └────────────┘ │
└───────────────────────────┬─────────────────────────────┘
                            │ WebSocket + REST
┌───────────────────────────▼─────────────────────────────┐
│                   FastAPI Backend                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │              LangGraph Orchestrator               │   │
│  │  ┌─────────────────┐    ┌─────────────────────┐  │   │
│  │  │ CHANAKYA Node   │◄──►│  ARYABHATA Node     │  │   │
│  │  │  (Reviewer)     │    │  (Developer)        │  │   │
│  │  └────────┬────────┘    └──────────┬──────────┘  │   │
│  │           │   PatchWise Skill      │             │   │
│  └───────────┼────────────────────────┼─────────────┘   │
└──────────────┼────────────────────────┼─────────────────┘
               │                        │
    ┌──────────▼──────┐      ┌──────────▼──────────┐
    │  ChromaDB       │      │  SQLite DB           │
    │  (Vector KB)    │      │  (Sessions/History)  │
    └─────────────────┘      └─────────────────────┘
               │
    ┌──────────▼──────────────────────┐
    │  External Sources               │
    │  lore.kernel.org | Gerrit | Git │
    └─────────────────────────────────┘
```

---

## 🔧 Configuration

### .env Reference
```env
# LLM runtime
# Use openai/anthropic for highest-accuracy agent reasoning.
# Use mock for offline/local deterministic mode.
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_API_KEY=
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
QUALCOMM_API_KEY=

# Unified app port (run.sh auto-increments if busy)
APP_PORT=7000

# Agent Settings
CHANAKYA_MAX_ROUNDS=5
SUBSYSTEM=audio

# Knowledge Base
CHROMADB_PATH=/app/data/chromadb
SQLITE_PATH=/app/data/sqlite/patchwise.db
LKML_PRESEEDED=false

# Submission
GITHUB_TOKEN=your_token_here
GERRIT_URL=https://your-gerrit-instance
GERRIT_USERNAME=your_username
GERRIT_PASSWORD=your_password

# Email
SMTP_HOST=smtp.qualcomm.com
SMTP_PORT=587
SMTP_USER=nandam@qti.qualcomm.com
NOTIFICATION_EMAIL=nandam@qti.qualcomm.com
```

---

## 📖 Usage

### Input Methods
| Method | How |
|---|---|
| Raw patch text | Paste directly into text area |
| Upload .patch file | Drag & drop or file picker |
| Gerrit link | Paste Gerrit review URL |
| lore.kernel.org link | Paste LKML thread URL |

### run.sh Commands
```bash
./run.sh start       # Start all services
./run.sh stop        # Stop all services
./run.sh restart     # Restart all services
./run.sh rebuild     # Force rebuild (after .env changes)
./run.sh logs        # Tail all logs
./run.sh status      # Show container status
./run.sh seed        # Pre-seed LKML knowledge base
./run.sh clean       # Remove containers + volumes
```

### API Key Setup (Safer Flow)
- `./run.sh start` now prompts for API key if provider is `openai`/`anthropic`/`qualcomm` and no key is found.
- You can keep keys out of `.env` by declining save at the prompt.
- You can also set/update runtime keys in UI at `/settings` (stored in runtime secrets, not git).

---

## 📁 Project Structure

```text
patchwise/
├── backend/
│   ├── agents/
│   │   ├── chanakya.py          # Reviewer agent
│   │   └── aryabhata.py         # Developer agent
│   ├── skills/
│   │   └── patchwise_skill.py   # Core patch analysis skill
│   ├── graph/
│   │   └── orchestrator.py      # LangGraph state machine
│   ├── knowledge/
│   │   ├── chromadb_store.py    # Vector KB
│   │   ├── sqlite_store.py      # Structured history
│   │   └── lkml_seeder.py       # LKML pre-seeder
│   ├── api/
│   │   ├── routes.py            # REST endpoints
│   │   └── websocket.py         # Streaming WebSocket
│   └── notifications/
│       └── email_service.py     # Email notifications
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── InputPage/       # Patch input UI
│   │   │   ├── ChatThread/      # Agent conversation
│   │   │   ├── DiffView/        # Monaco diff viewer
│   │   │   └── Agents/          # CHANAKYA & ARYABHATA doodles
│   │   ├── hooks/
│   │   │   └── useAgentStream.js # WebSocket streaming hook
│   │   └── store/
│   │       └── sessionStore.js  # Zustand state management
├── .github/
│   └── workflows/
│       ├── dev-ci.yml           # CI on push to dev
│       └── release.yml          # Release on merge to main
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.frontend
├── run.sh
├── .env.example
└── README.md
```

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
