"""Text extraction and normalization for supported file types.

PDF text is extracted page by page so every chunk can later cite its page number.
"""

import io
import re
import unicodedata

from pypdf import PdfReader

from app.core.errors import DocumentProcessingError, UnsupportedFileError
from app.rag.types import PageText

SUPPORTED_FILE_TYPES = ("pdf", "txt")

# Below this many characters a document is treated as empty (or as a scanned PDF without a text layer).
MIN_EXTRACTED_CHARS = 20


def detect_file_type(filename: str, data: bytes) -> str:
    """Return "pdf" or "txt" after checking both the extension and the actual bytes."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_FILE_TYPES:
        raise UnsupportedFileError()
    if extension == "pdf" and not data.startswith(b"%PDF-"):
        raise UnsupportedFileError("The file has a .pdf extension but is not a PDF.")
    if extension == "txt" and b"\x00" in data[:8192]:
        raise UnsupportedFileError("The file has a .txt extension but contains binary data.")
    return extension


def extract_pages(data: bytes, file_type: str) -> list[PageText]:
    if file_type == "pdf":
        raw_pages = _extract_pdf(data)
    elif file_type == "txt":
        raw_pages = [PageText(page=None, text=_decode_text(data))]
    else:
        raise UnsupportedFileError()

    pages = [PageText(p.page, normalize_text(p.text)) for p in raw_pages]
    pages = [p for p in pages if p.text]
    if sum(len(p.text) for p in pages) < MIN_EXTRACTED_CHARS:
        if file_type == "pdf":
            raise DocumentProcessingError(
                "The PDF contains little or no extractable text. Scanned PDFs (images of text) are not supported."
            )
        raise DocumentProcessingError("The document is empty.")
    return pages


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated across line breaks
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf(data: bytes) -> list[PageText]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentProcessingError("Password-protected PDFs are not supported.")
        return [PageText(page=i, text=page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)]
    except DocumentProcessingError:
        raise
    except Exception as exc:  # pypdf raises many different exception types for malformed files
        raise DocumentProcessingError("The PDF could not be read. It may be damaged.") from exc


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Common for files saved by older Windows editors.
        return data.decode("cp1252", errors="replace")
