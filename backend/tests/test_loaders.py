import pytest

from app.core.errors import DocumentProcessingError, UnsupportedFileError
from app.rag.loaders import detect_file_type, extract_pages, normalize_text
from tests.pdf_factory import build_pdf


def test_detect_file_type_accepts_pdf_and_txt():
    assert detect_file_type("report.PDF", build_pdf(["hello"])) == "pdf"
    assert detect_file_type("notes.txt", b"plain text") == "txt"


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("image.png", b"\x89PNG..."),
        ("no_extension", b"text"),
        ("fake.pdf", b"this is not a pdf"),
        ("binary.txt", b"MZ\x00\x00\x00binary"),
    ],
)
def test_detect_file_type_rejects_unsupported_or_mismatched_files(filename, data):
    with pytest.raises(UnsupportedFileError):
        detect_file_type(filename, data)


def test_pdf_pages_keep_their_page_numbers():
    pdf = build_pdf(["Alpha content on the first page.", "Beta content on the second page."])
    pages = extract_pages(pdf, "pdf")
    assert [p.page for p in pages] == [1, 2]
    assert "Beta content" in pages[1].text


def test_txt_has_no_page_number_and_falls_back_to_cp1252():
    pages = extract_pages("Café menu: coffee costs 120 rupees.".encode("cp1252"), "txt")
    assert pages[0].page is None
    assert "Café" in pages[0].text


def test_empty_txt_is_rejected():
    with pytest.raises(DocumentProcessingError, match="empty"):
        extract_pages(b"   \n\n  ", "txt")


def test_pdf_without_text_is_rejected():
    with pytest.raises(DocumentProcessingError, match="little or no extractable text"):
        extract_pages(build_pdf([""]), "pdf")


def test_malformed_pdf_is_rejected():
    with pytest.raises(DocumentProcessingError):
        extract_pages(b"%PDF-1.4\nthis file is truncated and broken", "pdf")


def test_normalize_text_rejoins_hyphenation_and_collapses_whitespace():
    assert normalize_text("infor-\nmation   is\r\n\r\n\r\n\r\nhere\x00") == "information is\n\nhere"
