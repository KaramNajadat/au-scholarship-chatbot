"""RAG core: the single function the app layer calls.

answer_question() runs the full pipeline: detect language -> retrieve the
closest scholarship chunks from Chroma -> score them -> refuse if off-topic,
otherwise generate a grounded answer with the local model. Returns the five
contract fields the app layer depends on.
"""

import chromadb
import ollama

from src.index import CHROMA_PATH, COLLECTION_NAME, embed

REFUSAL_EN = (
    "I can only answer questions about Ajman University scholarships. "
    "Please contact the scholarship office for anything else."
)
REFUSAL_AR = "أستطيع الإجابة فقط عن أسئلة المنح الدراسية في جامعة عجمان. يرجى التواصل مع مكتب المنح لأي استفسار آخر."

IN_SCOPE_THRESHOLD = 0.45
# qwen2.5:3b could not keep two student cohorts apart even with the exact policy
# text in front of it, and is Qwen-Research-licensed (non-commercial). gemma3:4b
# and qwen3:4b were faster but wrong. 7b is the smallest model tested that
# answers correctly in both languages, and is Apache 2.0.
GEN_MODEL = "qwen2.5:7b"

SOURCE_URLS = {
    "osfa_scholarships": "https://www.ajman.ac.ae/en/outreach/office-of-scholarship-financial-aid.html",
    "thamer_fund": "https://www.ajman.ac.ae/en/thamer-fund-1",
    "policy_manual": "https://www.ajman.ac.ae/upload/docs/Policies_and_Procedures_Manual_2025-2026.pdf",
}

def answer_question(question: str, history: list[dict] | None = None) -> dict:

    language = detect_language(question)
    results = retrieve(question)
    documents = results["documents"][0]
    distances = results["distances"][0]
    metadata = results["metadatas"][0]

    if not distances:
        return {
            "answer": REFUSAL_AR if language == "ar" else REFUSAL_EN,
            "sources": [],
            "language": language,
            "retrieval_score": 0.0,
            "in_scope": False,
        }

    retrieval_score = 1 - distances[0]
    in_scope = retrieval_score >= IN_SCOPE_THRESHOLD

    if in_scope:
        answer = generate_answer(question, documents, language)
        sources = []
        seen = set()
        for meta in metadata:
            if meta["title"] in seen:
                continue
            seen.add(meta["title"])
            sources.append({
                "title": meta["title"],
                "url": SOURCE_URLS.get(meta["source"]),
            })
    else:
        answer = REFUSAL_AR if language == "ar" else REFUSAL_EN
        sources = []

    return {
        "answer": answer,
        "sources": sources,
        "language": language,
        "retrieval_score": retrieval_score,
        "in_scope": in_scope,
    }


def detect_language(text: str) -> str:
    """Detect the language of the input text.

       returns either 'en' or 'ar'.
    """

    for char in text:
        if "\u0600" <= char <= "\u06FF": 
            return "ar"
    return "en"


_collection = None


def _get_collection():
    """Open the Chroma collection once and reuse it across queries.

    Opening a PersistentClient re-reads the on-disk store and get_collection
    re-reads its metadata, so doing both per question added avoidable latency to
    every answer on a pipeline that is already slow on CPU.

    Cached on first use rather than at import: src/app.py imports this module at
    startup, and building the client at import time would crash any clone where
    the index has not been built yet. Trade-off: the handle is long-lived, so
    rebuilding the index while the server is running is not picked up until the
    server restarts. The index is built once, offline, so that is the right
    default here.
    """
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = client.get_collection(COLLECTION_NAME)
    return _collection


def retrieve(question: str, n_results: int = 4) -> dict:
    """Find the knowledge base chunks that are closest in meaning to the question"""
    collection = _get_collection()
    question_embedding = embed(question)
    results = collection.query(
        query_embeddings=[question_embedding], n_results=n_results
    )
    return results


def generate_answer(question: str, documents: list[str], language: str) -> str:
    """Ask the local model to answer using only the retrieved chunks."""
    context = "\n\n".join(documents)
    lang_name = "Arabic" if language == "ar" else "English"
    system_prompt = (
        "You are the Ajman University scholarship assistant. "
        "Answer the question using ONLY the context below. "
        "If the answer is not in the context, say you do not have that "
        "information and suggest contacting the scholarship office.\n"
        "Scholarship rules apply to a specific group of students, such as an "
        "enrolment year, a college, or a programme. Every rule you state must "
        "name the group it applies to. Never attach one group's rule to another "
        "group's conditions.\n"
        "Use only what the student actually told you. Never assume or infer "
        "which group the student belongs to, and never state their enrolment "
        "year, college, or programme back to them unless they said it. If the "
        "context covers several groups and the student did not say which one "
        "they are in, give each group's rule separately with its own condition "
        "instead of choosing one for them.\n"
        "Never treat a requirement the student did not mention as already met. "
        "Write it as a condition they still have to satisfy (\"if you complete "
        "15 credit hours\"), never as a fact about them (\"since you completed "
        "15 credit hours\").\n"
        "Saying they are \"already enrolled\", \"a current student\" or "
        "\"still studying\" tells you nothing about WHICH YEAR they enrolled, "
        "so it never places them in an enrolment-year group.\n"
        "State every threshold exactly as the context writes it; do not widen, "
        "narrow, or round a range. GPA and CGPA are on a 4.00 scale where 4.00 "
        "is the maximum, so no student can be above it.\n\n"
        f"Context:\n{context}\n\n"
        # Keep this line last and positively phrased. Emphatic negations such as
        # "do not use any other language" made Qwen echo the instruction back in
        # Chinese and then answer in Chinese, roughly half the time.
        f"Reply in {lang_name}."
    )
    response = ollama.chat(
        model=GEN_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        # num_ctx is set explicitly because Ollama otherwise defaults to a small
        # window and silently drops context that does not fit.
        options={"temperature": 0.2, "num_predict": 400, "num_ctx": 8192},
    )
    return response["message"]["content"]