"""PDF document tools package."""

from app.services.pdf.annotate import add_page_numbers, esign_pdf, watermark_pdf
from app.services.pdf.compress import compress_pdf
from app.services.pdf.convert import jpg_to_pdf, pdf_to_excel, pdf_to_jpg, pdf_to_word, word_to_pdf
from app.services.pdf.merge import merge_pdfs
from app.services.pdf.ocr import ocr_pdf
from app.services.pdf.secure import protect_pdf, rotate_pdf, unlock_pdf
from app.services.pdf.split import split_pdf

__all__ = [
    "merge_pdfs",
    "split_pdf",
    "compress_pdf",
    "pdf_to_word",
    "word_to_pdf",
    "pdf_to_excel",
    "pdf_to_jpg",
    "jpg_to_pdf",
    "rotate_pdf",
    "unlock_pdf",
    "protect_pdf",
    "ocr_pdf",
    "watermark_pdf",
    "add_page_numbers",
    "esign_pdf",
]
