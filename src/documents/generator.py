"""PDF generation using fpdf2.

Renders template sections into formatted PDFs with lender letterhead,
consistent typography, and page numbers. Files are saved to docs/generated/
and tracked in the generated_documents table.
"""

import os
from fpdf import FPDF

from src.config import LENDER_NAME, LENDER_ADDRESS, LENDER_NMLS, LENDER_PHONE
from src.utils.db_helpers import (
    get_application, get_borrowers, get_underwriting_decisions,
    get_pricing_locks, create_generated_document,
)
from src.documents.templates import (
    initial_disclosure, approval_letter, denial_letter, closing_documents,
)

# Output directory for generated PDFs
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "generated")


class HelocPDF(FPDF):
    """Custom PDF class with letterhead header and page number footer."""

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, LENDER_NAME, new_x="LMARGIN", new_y="NEXT", align="C")
        self.set_font("Helvetica", "", 8)
        self.cell(0, 4, LENDER_ADDRESS, new_x="LMARGIN", new_y="NEXT", align="C")
        self.cell(0, 4, f"NMLS #{LENDER_NMLS}  |  {LENDER_PHONE}",
                  new_x="LMARGIN", new_y="NEXT", align="C")
        self.line(10, self.get_y() + 3, 200, self.get_y() + 3)
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def _sanitize(text: str) -> str:
    """Replace non-Latin-1 characters so fpdf2's built-in fonts don't choke.

    fpdf2's Helvetica only supports Latin-1. Rather than hunting down every
    possible Unicode character from user input, we encode to Latin-1 and
    replace anything that doesn't fit.
    """
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _render_pdf(sections: list[dict], title: str) -> bytes:
    """Render a list of sections into a PDF and return the bytes."""
    pdf = HelocPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)

    # Document title
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, _sanitize(title), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    for section in sections:
        # Section heading
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 8, _sanitize(section["heading"]), new_x="LMARGIN", new_y="NEXT")
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)

        # Section body
        pdf.set_font("Helvetica", "", 9)
        for line in section["lines"]:
            if line == "":
                pdf.ln(3)
            else:
                pdf.multi_cell(0, 5, _sanitize(line), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    return pdf.output()


def _save_pdf(pdf_bytes: bytes, filename: str) -> str:
    """Save PDF bytes to the output directory and return the full path."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    return filepath


def generate_initial_disclosure(app_id: int) -> str:
    """Generate the initial disclosure PDF on application submit."""
    app = get_application(app_id)
    borrowers = get_borrowers(app_id)
    primary = next((b for b in borrowers if b["is_primary"]), None)
    if not primary:
        raise ValueError("No primary borrower found")

    sections = initial_disclosure(app, primary)
    pdf_bytes = _render_pdf(sections, "Initial Disclosure")

    filename = f"{app['application_number']}_Initial_Disclosure.pdf"
    _save_pdf(pdf_bytes, filename)
    create_generated_document(app_id, doc_type="INITIAL_DISCLOSURE", filename=filename)
    return filename


def generate_decision_letter(app_id: int) -> str:
    """Generate approval or denial letter after UW decision."""
    app = get_application(app_id)
    borrowers = get_borrowers(app_id)
    primary = next((b for b in borrowers if b["is_primary"]), None)
    if not primary:
        raise ValueError("No primary borrower found")

    decisions = get_underwriting_decisions(app_id)
    if not decisions:
        raise ValueError("No underwriting decision found")
    decision = decisions[0]  # Most recent

    if decision["decision"] == "DENY":
        sections = denial_letter(app, primary, decision)
        title = "Notice of Adverse Action"
        doc_type = "DENIAL_LETTER"
        filename = f"{app['application_number']}_Denial_Letter.pdf"
    else:
        pricing_locks = get_pricing_locks(app_id)
        pricing = pricing_locks[0] if pricing_locks else None
        sections = approval_letter(app, primary, decision, pricing)
        title = "Approval Notification"
        doc_type = "APPROVAL_LETTER"
        filename = f"{app['application_number']}_Approval_Letter.pdf"

    pdf_bytes = _render_pdf(sections, title)
    _save_pdf(pdf_bytes, filename)
    create_generated_document(app_id, doc_type=doc_type, filename=filename)
    return filename


def generate_closing_documents(app_id: int) -> str:
    """Generate closing document package when status moves to CLOSING."""
    app = get_application(app_id)
    borrowers = get_borrowers(app_id)
    primary = next((b for b in borrowers if b["is_primary"]), None)
    if not primary:
        raise ValueError("No primary borrower found")

    pricing_locks = get_pricing_locks(app_id)
    pricing = pricing_locks[0] if pricing_locks else None

    sections = closing_documents(app, primary, pricing)
    pdf_bytes = _render_pdf(sections, "Closing Disclosure")

    filename = f"{app['application_number']}_Closing_Documents.pdf"
    _save_pdf(pdf_bytes, filename)
    create_generated_document(app_id, doc_type="CLOSING_DOCUMENTS", filename=filename)
    return filename
