from app.rag.chunking import chunk_pages
from app.rag.types import PageText


def _chunk(pages, **overrides):
    options = {"owner_id": "user-1", "document_id": "doc-1", "filename": "f.pdf", "chunk_size": 200, "chunk_overlap": 20}
    return chunk_pages(pages, **(options | overrides))


def test_chunks_never_span_pages_and_keep_metadata():
    pages = [PageText(1, "First page sentence. " * 30), PageText(2, "Second page sentence. " * 30)]
    chunks = _chunk(pages)

    assert len(chunks) > 2
    for index, chunk in enumerate(chunks):
        assert len(chunk.page_content) <= 200
        assert chunk.id == chunk.metadata["chunk_id"] == f"doc-1:{index}"
        assert chunk.metadata["owner_id"] == "user-1"
        assert chunk.metadata["document_id"] == "doc-1"
        expected_page = 1 if "First" in chunk.page_content else 2
        assert chunk.metadata["page"] == expected_page
        assert not ("First" in chunk.page_content and "Second" in chunk.page_content)


def test_txt_chunks_have_no_page_key():
    chunks = _chunk([PageText(None, "Some text without pages.")])
    assert "page" not in chunks[0].metadata
