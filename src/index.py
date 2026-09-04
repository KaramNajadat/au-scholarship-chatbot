"""
Build the searchable knowledge base for the RAG pipeline.

Reads the collected AU scholarship records, splits them into chunks that
follow the document's own structure, turns each chunk into an embedding (a
list of numbers that captures its meaning) using the local bge-m3 model via
Ollama, and stores everything in a Chroma vector database on disk. Run once;
re-run to rebuild from scratch.
"""
import json
import re
from pathlib import Path

import chromadb
import ollama

PROJECT_ROOT = Path(__file__).parent.parent
COLLECTED_PATH = PROJECT_ROOT / "data" / "raw" / "collected.json"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"

EMBED_MODEL = "bge-m3"
COLLECTION_NAME = "au_scholarships"
MAX_SECTION = 2000     # gather up to this many characters before starting a new
                       # chunk; a single clause or line longer than this stays
                       # whole rather than being cut in half
MIN_TAIL = 300         # a leftover shorter than this joins the previous chunk
                       # instead of being emitted as an orphan

# Every scholarship rule comes with conditions naming which students it applies
# to. Splitting on character count alone tore rules away from their conditions
# and left the model to guess which went with which, so follow the document's
# own boundaries: articles and numbered clauses in the policy manual, whole
# lines everywhere else.
ARTICLE_SPLIT = re.compile(r"(?=Article\s+\d+\s)")
CLAUSE_SPLIT = re.compile(r"(?=\n\s*\d+\.\s)")


def split_on_lines(text: str) -> list[str]:
    """Gather whole lines into chunks, never splitting inside a line."""
    if len(text) <= MAX_SECTION:
        return [text]
    chunks = []
    buffer = ""
    for line in text.split("\n"):
        if buffer and len(buffer) + len(line) + 1 > MAX_SECTION:
            chunks.append(buffer)
            buffer = line
        else:
            buffer = f"{buffer}\n{line}" if buffer else line
    if buffer.strip():
        if chunks and len(buffer) < MIN_TAIL:
            chunks[-1] = f"{chunks[-1]}\n{buffer}"
        else:
            chunks.append(buffer)
    return chunks


def with_heading(piece: str, heading: str) -> str:
    """Keep a piece of an article attached to the article it came from."""
    piece = piece.strip()
    if piece.startswith(heading):
        return piece
    return f"{heading}\n{piece}"


def split_article(section: str, heading: str) -> list[str]:
    """Break an oversized article on its numbered clauses, never mid-clause."""
    chunks = []
    buffer = ""
    for clause in CLAUSE_SPLIT.split(section):
        if buffer and len(buffer) + len(clause) > MAX_SECTION:
            chunks.append(with_heading(buffer, heading))
            buffer = clause
        else:
            buffer += clause
    if buffer.strip():
        chunks.append(with_heading(buffer, heading))
    return chunks


def chunk_text(text: str) -> list[str]:
    """Split a record into chunks, following article structure where it exists."""
    sections = [s for s in ARTICLE_SPLIT.split(text) if s.strip()]
    if len(sections) < 2:
        return split_on_lines(text)
    chunks = []
    for section in sections:
        heading = section.split("\n", 1)[0].strip()
        if len(section) <= MAX_SECTION:
            chunks.append(section.strip())
        else:
            chunks.extend(split_article(section, heading))
    return chunks


def embed(text: str) -> list[float]:
    """Turn one piece of text into its embedding vector via Ollama."""
    return ollama.embeddings(model=EMBED_MODEL, prompt=text)["embedding"]


def main():
    records = json.loads(COLLECTED_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(records)} records from {COLLECTED_PATH}")

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

    ids, embeddings, documents, metadatas = [], [], [], []
    for r_index, record in enumerate(records):
        for c_index, piece in enumerate(chunk_text(record["body"])):
            chunk = f"{record['title']}\n{piece}"
            ids.append(f"{r_index}-{c_index}")
            embeddings.append(embed(chunk))
            documents.append(chunk)
            metadatas.append({
                "source": record["source"],
                "lang": record["lang"],
                "title": record["title"],
            })

    collection.add(
        ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
    )
    print(f"Indexed {len(ids)} chunks into '{COLLECTION_NAME}' at {CHROMA_PATH}")


if __name__ == "__main__":
    main()