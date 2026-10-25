"""Command-line playground for the RAG pipeline (no API, no database).

Run from the backend folder with the virtual environment active:
    python -m scripts.rag_cli ingest ..\\samples\\northwind_handbook.txt
    python -m scripts.rag_cli ask "How many days of annual leave do I get?"
    python -m scripts.rag_cli search "remote work"        # retrieval only, shows scores
    python -m scripts.rag_cli delete <document_id>

Uses its own Chroma collection and a fixed owner, so it never touches application data.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from app.core.config import get_settings
from app.core.errors import AppError
from app.rag.ingestion import content_hash, ingest_document
from app.rag.loaders import detect_file_type
from app.rag.providers import get_chat_model, get_embeddings
from app.rag.qa import answer_question
from app.rag.vector_store import ChromaVectorStore, build_chroma_client, collection_name_for

CLI_OWNER_ID = "cli-user"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ingest").add_argument("paths", nargs="+", type=Path)
    commands.add_parser("ask").add_argument("question")
    commands.add_parser("search").add_argument("query")
    commands.add_parser("delete").add_argument("document_id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    settings = get_settings()
    store = ChromaVectorStore(build_chroma_client(settings), collection_name_for(settings, "_cli"), get_embeddings(settings))

    try:
        if args.command == "ingest":
            for path in args.paths:
                data = path.read_bytes()
                file_type = detect_file_type(path.name, data)
                # The CLI derives the ID from the content, so re-ingesting a file replaces its chunks.
                document_id = content_hash(data)[:16]
                count = ingest_document(
                    data,
                    file_type=file_type,
                    owner_id=CLI_OWNER_ID,
                    document_id=document_id,
                    filename=path.name,
                    vector_store=store,
                    chunk_size=settings.chunk_size,
                    chunk_overlap=settings.chunk_overlap,
                )
                print(f"Indexed {path.name}: {count} chunks (document_id={document_id})")
        elif args.command == "search":
            for chunk in store.search(args.query, owner_id=CLI_OWNER_ID, k=settings.retrieval_top_k):
                page = f" p.{chunk.page}" if chunk.page else ""
                print(f"{chunk.score:.3f}  {chunk.filename}{page}  {chunk.text[:90]!r}")
        elif args.command == "ask":
            result = answer_question(
                args.question,
                owner_id=CLI_OWNER_ID,
                vector_store=store,
                chat_model=get_chat_model(settings),
                top_k=settings.retrieval_top_k,
                min_relevance=settings.min_relevance_score,
                relevance_margin=settings.relevance_margin,
            )
            print(f"\nAnswer:\n{result.answer}\n")
            for citation in result.citations:
                page = f", page {citation.page}" if citation.page else ""
                print(f"[{citation.label}] {citation.filename}{page} (score {citation.score:.3f})")
                print(f"     {citation.excerpt[:160]!r}")
        elif args.command == "delete":
            print(f"Deleted {store.delete_document(args.document_id)} chunks")
    except AppError as exc:
        print(f"Error ({exc.code}): {exc.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
