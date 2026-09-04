<div align="center">

# AU Scholarship Chatbot

**A bilingual Arabic/English RAG assistant that answers Ajman University scholarship
questions strictly from AU's own published documents, cites its sources, refuses anything
out of scope, and escalates to a human when it starts repeating itself.**

[![CI](https://github.com/KaramNajadat/au-scholarship-chatbot/actions/workflows/ci.yml/badge.svg)](https://github.com/KaramNajadat/au-scholarship-chatbot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-vector%20store-FF6B6B)](https://www.trychroma.com/)
[![Ollama](https://img.shields.io/badge/Ollama-self--hosted-000000?logo=ollama&logoColor=white)](https://ollama.com/)
[![Qwen 2.5 7B](https://img.shields.io/badge/Qwen%202.5-7B-6F4CFF)](https://ollama.com/library/qwen2.5)
[![bge-m3](https://img.shields.io/badge/embeddings-bge--m3-4C8BF5)](https://ollama.com/library/bge-m3)
[![Languages](https://img.shields.io/badge/languages-%D8%A7%D9%84%D8%B9%D8%B1%D8%A8%D9%8A%D8%A9%20%7C%20English-1B9AAA)](#)

</div>

---

The deliverable is a **website** served by FastAPI. It opens in a browser at a local URL
and is designed so it could later be embedded into AU's real site. Everything runs on the
machine it is installed on: the web server, the database and the model. Nothing leaves the
box.

> **Status.** Built during a 2026 internship with Ajman University's Office of Information
> Technology, delivered and demonstrated to the supervising engineer in July 2026. It was
> never deployed to students and has not run in production. Developed over 38 commits and
> 5 merged pull requests in a private repository; published here as a single snapshot with
> the supervisor's permission.

**Built by** [Karam Najadat](https://github.com/KaramNajadat) and
[Ayham Smadi](https://github.com/ayham15s). Karam built the FastAPI application layer, the
bilingual chat front end, SQLite session logging, the escalation rule and the admin
console, and contributed to the retrieval and prompt work including the structure-aware
chunker, the language-drift fix and the hallucination guards. Ayham built the initial
knowledge base and retrieval core.

---

## Contents

- [How it works](#how-it-works)
- [How it answers, and when it refuses](#how-it-answers-and-when-it-refuses)
- [Model choice](#model-choice)
- [Quick start](#quick-start)
- [URLs](#urls)
- [Features](#features)
- [Data sources](#data-sources)
- [Known limitations](#known-limitations)
- [Docs](#docs)

## How it works

```
AU web pages + policy PDF          ← src/collect.py
          │
          ▼  structure-aware chunking (articles, clauses, whole lines)
   101 indexed chunks               ← src/index.py
          │
          ▼  bge-m3 embeddings → ChromaDB
     top-4 retrieval                ← src/rag.py
          │
    score ≥ 0.45 ?
      │        │
     no        yes
      │         │
   refuse    qwen2.5:7b generates a grounded, cited answer
   (< 1s)                │
                         ▼
        FastAPI + chat UI + SQLite logging + escalation
                                    ← src/app.py, src/db.py, static/
```

Two halves meeting at a single function. The application layer only ever calls
`answer_question()`, so the real pipeline was built and swapped in behind that boundary
with **no application-layer code changed**. See
[docs/interface-contract.md](docs/interface-contract.md).

## How it answers, and when it refuses

Retrieval returns the four closest chunks and scores the best one as
`1 - cosine_distance`. Below **0.45** the question is treated as out of scope and refused
in the language it was asked, **without invoking the model at all**, so refusals come back
in under a second while a real answer takes 80 to 100 seconds on CPU-only hardware.

The system prompt carries five hallucination guards, each written in response to an
observed failure:

| Guard | What it prevents |
| --- | --- |
| Answer only from the retrieved context | Invented policy |
| Every rule must name the group it applies to | A rule floating free of its cohort |
| Never infer which group the student is in | Confidently answering the wrong student |
| An unmet requirement stays a condition | "Since you completed 15 credit hours" when they did not |
| State thresholds exactly as written | Widening, narrowing or rounding a GPA range |

## Model choice

Four models were tried for generation. Accuracy and licence pointed at the same one.

| Model | Outcome |
| --- | --- |
| `qwen2.5:3b` | Faster, but could not keep two student cohorts apart even with the exact policy text in context. Qwen-Research-licensed, non-commercial only. |
| `gemma3:4b` | Faster, wrong. |
| `qwen3:4b` | Faster, wrong. |
| **`qwen2.5:7b`** | **Smallest model tested that answers correctly in both Arabic and English. Apache 2.0. In use.** |

The cost is speed: roughly 80 to 100 seconds per answer on the CPU-only laptop this was
developed on. `qwen2.5:7b` is a larger instruction-tuned model, not a reasoning model, so
the extra time is parameter count rather than any additional deliberation step. Full
reasoning in [docs/engineering-notes.md](docs/engineering-notes.md).

## Quick start

**Requirements:** Python 3.10+ (developed on 3.14, CI runs 3.12), git, and
[Ollama](https://ollama.com/download) running locally. Both models run on CPU, no GPU
required.

```powershell
# 1. Clone and enter the project
git clone https://github.com/KaramNajadat/au-scholarship-chatbot
cd au-scholarship-chatbot

# 2. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1
# If activation is blocked ("running scripts is disabled on this system"), run once:
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# then re-run the activate line above.

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Pull the two models
ollama pull qwen2.5:7b   # answer generation (qwen2.5:3b is faster but less accurate)
ollama pull bge-m3       # embeddings

# 5. Build the vector store from the bundled knowledge base (data/raw/collected.json).
#    Run once; re-run to rebuild from scratch. Prints "Indexed <N> chunks" on success.
python src/index.py

# 6. Run it
uvicorn src.app:app
```

Then open **http://127.0.0.1:8000/**. Steps 4 and 5 must be done first, or the bot cannot
answer.

## URLs

| URL | What it is |
| --- | --- |
| `/` | The chat website |
| `/health` | Health check, returns `{"status": "ok"}` |
| `/chat` | POST endpoint the page calls to get answers (JSON) |
| `/admin` | Read-only page to browse logged sessions and their turns |
| `/docs` | Auto-generated interactive API documentation |

## Features

- **Bilingual.** Arabic messages lay out right-to-left automatically, the UI greets in both
  languages, and answers come back in the language the question was asked in.
- **Structure-aware chunking.** Splitting on character count tore scholarship rules away
  from the cohort conditions they attach to, leaving the model to guess which went with
  which. Chunks follow the document's own boundaries instead: articles and numbered clauses
  in the policy manual, whole lines elsewhere, with article headings re-prepended so a
  clause never loses its parent.
- **Scope gate.** Out-of-scope questions are refused without calling the model.
- **Cited answers.** Each answer carries source chips linking back to the AU page or PDF the
  content came from.
- **Session logging.** Every answered turn is written to a local SQLite database at
  `data/chatbot.db` (tables `sessions` and `turns`). That file is **gitignored**, so no
  logged conversation is ever committed.
- **Escalation.** If the bot returns the same answer **three times in a row** in a session,
  the session is flagged (`sessions.escalated = 1`), a warning is logged, and the page tells
  the user they have been handed to a human advisor.
- **Admin view.** `/admin` browses every logged session with its turn count and escalation
  badge, and inspects each turn's question, answer, sources, language and retrieval score.

## Data sources

Everything the bot knows comes from these public Ajman University sources, collected by
`src/collect.py`:

| Source | Languages |
| --- | --- |
| [Office of Scholarship & Financial Aid](https://www.ajman.ac.ae/en/outreach/office-of-scholarship-financial-aid.html) ([AR](https://www.ajman.ac.ae/ar/admissions/office-of-scholarship-financial-aid.html)) | English, Arabic |
| [Thamer Fund](https://www.ajman.ac.ae/en/thamer-fund-1) ([AR](https://www.ajman.ac.ae/ar/thamer-fund-1)) | English, Arabic |
| [Policies and Procedures Manual 2025-2026](https://www.ajman.ac.ae/upload/docs/Policies_and_Procedures_Manual_2025-2026.pdf), pages 617-626 | English |

59 records, 98,753 characters, indexed into 101 chunks. See [NOTICE](NOTICE) for the
ownership of this content.

## Known limitations

Tracked openly in [ISSUES.md](ISSUES.md) and [TESTING.md](TESTING.md). The ones worth
knowing before reading the code:

- **`/admin` has no authentication.** Intended for localhost and demo use. Any real
  deployment must put it behind a login.
- **Open correctness defect.** The bot understates one employee tuition-discount case.
  Diagnosed in `ISSUES.md`, not fixed.
- **No automated tests.** `TESTING.md` is a book of roughly 30 manual cases, including
  adversarial ones. CI lints and imports; it does not test behaviour.
- **No conversation memory.** The `history` parameter exists in the contract and is never
  populated, so each turn is answered independently.
- **Escalation notifies by log line only.** A real email or webhook is a documented next
  step, not built.

## Docs

| Document | What is in it |
| --- | --- |
| [docs/engineering-notes.md](docs/engineering-notes.md) | The per-query Chroma client fix, what CI does and does not check, and the model choice |
| [docs/interface-contract.md](docs/interface-contract.md) | The single-function boundary between the two halves, and why it was stubbed first |
| [ISSUES.md](ISSUES.md) | Running issue tracker with observed symptom, code location, root cause and proposed fix |
| [TESTING.md](TESTING.md) | Manual test book, both languages, with expected answers and failure conditions |

## Data privacy

Everything runs locally: the web server, the database and the model. No student data is
sent to any external service, and there are no outbound API calls.

## Licence

Code is MIT, see [LICENSE](LICENSE). The AU scholarship content in
`data/raw/collected.json` and the AU logo in `static/logo3.png` are Ajman University's and
are not covered by that grant, see [NOTICE](NOTICE).
