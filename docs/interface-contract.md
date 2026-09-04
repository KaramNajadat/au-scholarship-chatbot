# The interface contract

This project was built by two developers working in parallel on halves that had to
meet in the middle: a retrieval and generation pipeline, and a web application to
put in front of it. The whole boundary between them is one function.

## The contract

```python
# src/rag.py
def answer_question(question: str, history: list[dict] | None = None) -> dict:
    return {
        "answer": "...",          # str: the text shown to the user
        "sources": [...],         # list: which chunks were used, for citation and logging
        "language": "en",         # str: "ar" or "en", detected from the question
        "retrieval_score": 0.0,   # float 0-1: similarity of the best-matched chunk
        "in_scope": True,         # bool: was this an AU scholarship question at all
    }
```

The application layer never imports anything else from the pipeline. It does not
know that Chroma exists, which embedding model is used, or how chunking works. It
calls one function and reads five fields.

## Why it was stubbed first

The function was written and committed as a **stub with the real shape** before any
retrieval existed: correct field names, correct types, a fixed placeholder answer.

That ordering is the point. It meant the web server, the chat page, session
logging, the escalation rule and the admin console could all be built and tested
against something real-shaped while the retrieval pipeline was still being written.
Neither half was ever blocked waiting for the other.

When the real pipeline replaced the stub, **no application-layer code changed.**
The contract held, which is the only evidence that matters for whether a boundary
was drawn in the right place.

## The rules that made it work

- **Field names and types do not change without both developers agreeing.** A
  missing field is raised as a question, never invented on one side.
- **The application raises loudly if a field is absent**, rather than defaulting it.
  A silent default here would surface later as a wrong answer with no trace back to
  the cause.
- **It is an in-process function call, not a network API.** Both halves run in the
  same process on the same machine. That was a deliberate scope decision: a local
  HTTP hop between them would have bought nothing and added a failure mode.

## `sources`

The application accepts either a list of plain strings or a list of objects, and
renders a source as a clickable chip when the object carries a `url`. The pipeline
returns objects with `title` and `url`, resolved from the three known source
documents, so citations in the interface link back to the AU page or PDF they came
from.

## `history`

The parameter exists in the signature and is never populated. Every turn is
answered independently, with no conversational memory.

This is an honest limitation rather than an oversight: the shape was reserved in
the contract so multi-turn memory could be added later without a breaking change,
but nothing in the current system sends it. Session state is tracked separately by
the application layer for logging and for the escalation rule, which counts
repeated answers within a session.
