"""Split extracted pages into overlapping chunks that carry their own metadata."""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.types import PageText


def chunk_id_for(document_id: str, index: int) -> str:
    return f"{document_id}:{index}"


def chunk_pages(
    pages: list[PageText],
    *,
    owner_id: str,
    document_id: str,
    filename: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """Split each page separately so a chunk never spans two pages and its page citation stays exact."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        keep_separator="end",
    )
    chunks: list[Document] = []
    for page in pages:
        for piece in splitter.split_text(page.text):
            chunk_id = chunk_id_for(document_id, len(chunks))
            metadata: dict[str, str | int] = {
                "owner_id": owner_id,
                "document_id": document_id,
                "filename": filename,
                "chunk_id": chunk_id,
                "chunk_index": len(chunks),
            }
            if page.page is not None:  # Chroma metadata values cannot be None
                metadata["page"] = page.page
            chunks.append(Document(id=chunk_id, page_content=piece, metadata=metadata))
    return chunks
