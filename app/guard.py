"""Upload validation. Everything stays in memory."""

import io
import os

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect

MAX_BYTES = int(float(os.environ.get("MAX_UPLOAD_MB", "5")) * 1024 * 1024)
MAX_PAGES = int(os.environ.get("MAX_PAGES", "10"))


class RejectedUpload(ValueError):
    pass


def check(data: bytes) -> int:
    """Validate a PDF upload and return its page count."""
    if not data:
        raise RejectedUpload("The file is empty.")
    if len(data) > MAX_BYTES:
        raise RejectedUpload(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if not data[:1024].lstrip().startswith(b"%PDF-"):
        raise RejectedUpload("This is not a PDF file.")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = len(pdf.pages)
    except (PDFPasswordIncorrect, PDFEncryptionError):
        raise RejectedUpload("The PDF is password protected. ATSs can't read it either.")
    except Exception:
        raise RejectedUpload("The PDF could not be opened. It may be damaged.")
    if pages == 0:
        raise RejectedUpload("The PDF has no pages.")
    if pages > MAX_PAGES:
        raise RejectedUpload(f"The PDF has {pages} pages; the limit is {MAX_PAGES}.")
    return pages
