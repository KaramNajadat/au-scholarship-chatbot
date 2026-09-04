"""App layer: FastAPI server for the AU scholarship chat website. Karam owns this file."""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.db import (
    check_and_flag_escalation,
    get_session_turns,
    init_db,
    list_sessions,
    log_turn,
)
from src.rag import answer_question

logging.basicConfig(level=logging.INFO) #Logging setup
logger = logging.getLogger("chatbot")

app = FastAPI(title="AU Scholarship Chatbot")

# Create the SQLite tables on startup if they don't exist yet.
init_db()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

class ChatRequest(BaseModel): #The request shape
    question: str
    session_id: str

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# --- Admin view (read-only log browser). No auth: intended for localhost/demo only. ---

@app.get("/admin")
def admin() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/admin/api/sessions")
def admin_sessions() -> list:
    return list_sessions()


@app.get("/admin/api/sessions/{session_id}")
def admin_session(session_id: str) -> dict:
    return {"session_id": session_id, "turns": get_session_turns(session_id)}

@app.post("/chat") #handler
def chat(req: ChatRequest) -> dict:
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty.")
    try:
        result = answer_question(question)
    except Exception:
        logger.exception("answer_question failed for question: %r", question)
        raise HTTPException(status_code=500, 
                            detail="The answer engine failed. The error has been logged; please try again.",
                            )
    response = {
        "answer": result["answer"],
        "sources": result["sources"],
        "language": result["language"],
        "retrieval_score": result["retrieval_score"],
        "in_scope": result["in_scope"],
    }

    # Log the turn and check the escalation rule. A logging failure must never
    # swallow the user's answer, but must never be silent either — record it
    # loudly and still respond.
    escalated = False
    try:
        log_turn(
            session_id=req.session_id,
            question=question,
            answer=response["answer"],
            sources=response["sources"],
            language=response["language"],
            retrieval_score=response["retrieval_score"],
        )
        escalated = check_and_flag_escalation(req.session_id)
    except Exception:
        logger.exception("Failed to log/check turn for session %r", req.session_id)

    if escalated:
        # The demo's "notify a human". A real email/webhook is a documented next step.
        logger.warning(
            "ESCALATION: session %s returned the same answer 3 times in a row",
            req.session_id,
        )

    response["escalated"] = escalated
    return response