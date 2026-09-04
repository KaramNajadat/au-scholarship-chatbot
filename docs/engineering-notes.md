# Engineering notes

Decisions in this project that are not obvious from reading the code, and the two
changes made when the repository was opened up.

---

## 1. The Chroma collection is opened once, not per query

### What the code used to do

`retrieve()` in `src/rag.py` built a fresh client on every single question:

```python
def retrieve(question: str, n_results: int = 4) -> dict:
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(COLLECTION_NAME)
    ...
```

### Why that is waste

`PersistentClient` is not a lightweight handle. Constructing it opens the on-disk
store, and `get_collection` then reads that collection's metadata back. Neither of
those depends on the question being asked, so both were repeated work: the same
files reopened and the same metadata reread for every turn, discarded, and done
again on the next turn.

It matters more here than it would elsewhere. This pipeline already takes roughly
80 to 100 seconds per answer on CPU-only hardware, and the one thing that is
genuinely fast is the sub-second refusal path for out-of-scope questions. Setup
work repeated per query eats into exactly the case that was supposed to be quick.

### What it does now

```python
_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = client.get_collection(COLLECTION_NAME)
    return _collection
```

The client and collection are built on the first query and reused for the life of
the process.

### Why the cache is lazy rather than eager

The obvious version is a module-level `collection = client.get_collection(...)` at
the top of the file. That would be wrong here.

`src/app.py` imports `src.rag` at startup. Building the client at import time
means that in any clone where `python src/index.py` has not been run yet, there is
no vector store on disk, so importing the app crashes before the server starts. The
failure would also be confusing: an import error, not a message saying the index is
missing.

Deferring to first use keeps module import free of side effects, which is also what
makes the CI import check in section 2 possible.

### The trade-off, stated

A long-lived handle means the collection is read once. Rebuilding the index while
the server is running is not picked up until the server restarts.

That is the right default for this project, because the index is built once and
offline by a separate script, and rebuilding it is a deliberate maintenance action
rather than something that happens under a live server. It is worth naming rather
than leaving implicit, because it is a genuine behaviour change from the old code:
previously every query would have seen a rebuilt index immediately.

---

## 2. Continuous integration

`.github/workflows/ci.yml` runs on every push to `main` and every pull request.

### What it checks

1. **Dependencies install.** `pip install -r requirements.txt` against the pinned
   versions. This alone catches a pin that has gone missing or become
   uninstallable.
2. **Lint.** `ruff check .` with the configuration in `ruff.toml`: `E`
   (pycodestyle), `F` (pyflakes) and `I` (import ordering). `F` is the one that
   earns its place, catching undefined names and unused imports.
3. **Import smoke test.** `python -c "import src.app"`. This transitively imports
   every module in the project in dependency order (`app` to `rag` to `index` and
   `db`), so it catches syntax errors, undefined names at module scope, circular
   imports and a broken package layout.

The smoke test is only possible because of the change in section 1. If the Chroma
client were built at import time, this step would fail in CI, where no vector index
exists. The two changes support each other.

### What it deliberately does not check

Being clear about this matters more than the green badge:

- **There are no unit tests.** None. Testing is manual and lives in `TESTING.md`,
  which is a book of roughly 30 hand-run cases with expected answers and failure
  conditions, including adversarial ones. That is a documented process, not an
  automated one, and CI does not pretend otherwise.
- **The model never runs in CI.** Answer generation needs Ollama plus `qwen2.5:7b`
  and `bge-m3`, which are multi-gigabyte downloads. Nothing in CI exercises
  retrieval, generation, the 0.45 scope gate or the refusal path.
- **Nothing checks answer quality.** The open defects in `ISSUES.md`, including the
  wrong tuition-discount percentage, would not be caught by this pipeline. Catching
  them needs a labelled evaluation set scored automatically, which does not exist
  yet and is the most valuable next thing to build.

So a green tick here means the project installs, lints and imports. It does not
mean the bot is correct.

---

## 3. Why `qwen2.5:7b` and not something smaller

Four models were tried for answer generation. The decision came down to accuracy
and licence pointing at the same place.

| Model | Outcome |
| --- | --- |
| `qwen2.5:3b` | Faster, but could not keep two student cohorts apart even with the exact policy text in the context. Also Qwen-Research-licensed, so non-commercial only. |
| `gemma3:4b` | Faster, wrong. |
| `qwen3:4b` | Faster, wrong. |
| `qwen2.5:7b` | The smallest model tested that answers correctly in **both** Arabic and English. Apache 2.0. |

The cohort failure is the one that decided it. Scholarship rules attach to specific
groups of students, so a model that blurs two cohorts does not give a slightly
worse answer, it gives a confidently wrong one to a real person about money.

The cost is speed: 7b is roughly 80 to 100 seconds per answer on the CPU-only
laptop this was developed on. It is a larger instruction-tuned model, not a
reasoning model, so the extra time is parameter count rather than any additional
deliberation step.

The licence was not a tiebreaker after the fact. `qwen2.5:3b` being research-only
would have ruled it out of any real university deployment regardless of accuracy,
and the same constraint appeared elsewhere in the same internship. A licence
constrains engineering as firmly as a technical limit does.
