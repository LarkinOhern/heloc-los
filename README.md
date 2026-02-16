# HELOC Loan Origination System (Prototype)

A toy HELOC LOS built to prepare for evaluating vendor solutions via an RFP process. Gives the team hands-on experience with both borrower-facing (Point of Sale) and employee-facing (Loan Origination) workflows.

**This is a prototype, not production software.** It intentionally omits authentication, real credit bureau pulls, file storage, and other production concerns to focus on understanding the workflow.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run src/app.py
```

The database is automatically created and seeded with 5 sample applications on first run.

### Sample Borrower Emails (for testing)
- `homer@example.com` — Funded application (complete)
- `george@example.com` — Approved with conditions (waiting)
- `sherlock@example.com` — Denied (CLTV too high)
- `tony@example.com` — Just submitted (unassigned)
- `harry@example.com` — In review (being worked)

### Employee Logins
- **Jane Smith** (Loan Officer) — has apps 1, 3 assigned
- **Bob Wilson** (Loan Officer) — has apps 2, 5 assigned
- **Admin User** (Admin) — full access + config view

## Architecture

| Layer | Tool |
|-------|------|
| App Framework | Streamlit |
| Backend | Python 3.11+ |
| Database | SQLite (WAL mode) |
| Doc Generation | fpdf2 |
| Data Display | pandas |

### Key Files

```
src/
  app.py              # Entry point, role routing
  auth.py             # Role selector (no real auth)
  config.py           # All thresholds, pricing tables, workflow rules
  database.py         # Schema (11 tables), connection helper
  models.py           # Dataclasses
  seed.py             # Sample data generator
  pages/
    borrower_*.py     # Point of Sale (apply, status, documents)
    employee_*.py     # Loan Origination (pipeline, review, conditions)
    admin_config.py   # Config viewer + audit log
  engines/
    underwriting.py   # Rules-based decisioning
    pricing.py        # Risk-based rate calculation
  documents/
    generator.py      # PDF generation (fpdf2)
    templates.py      # Document content/structure
  utils/
    db_helpers.py     # CRUD for all tables
    formatters.py     # Currency, %, date formatting
```

## Features

### Borrower (Point of Sale)
- 6-step application wizard with save-on-next and resume by email
- Application status tracker with visual progress stepper
- Document upload stubs and generated document downloads

### Loan Officer (Loan Origination)
- Pipeline view with status counts and filters
- Application review with 7 tabs (Summary, Income, Assets & Debts, UW, Pricing, Docs, Audit)
- Status changes with transition validation
- Conditions management (add, satisfy, waive)

### Underwriting Engine
- Rules-based: credit score, LTV, CLTV, DTI, property/amount checks
- Three outcomes: Approve, Approve with Conditions, Deny
- Auto-creates conditions and updates application status

### Pricing Engine
- Prime + margin + FICO/LTV/amount tier adjustments - autopay discount
- Rate lock with 60-day expiration and countdown
- Full component breakdown for borrower explanation

### Document Generation
- Initial Disclosure (on submit)
- Approval/Denial Letter (on UW decision)
- Closing Documents (on status change to Closing)
- PDF with lender letterhead, downloadable from both sides

## RFP Evaluation Notes

Use this prototype to develop better questions for vendors. Key gaps to probe:

### Authentication & Security
- This prototype uses a role selector with no passwords
- **Ask vendors:** SSO/SAML integration? Role-based access control granularity? Audit trail for access (not just actions)?

### Data & Integration
- Prototype uses self-reported credit scores, no bureau integration
- **Ask vendors:** Credit bureau integrations (which ones)? AUS (automated underwriting system) connections? Flood/title vendor integrations? How do they handle data residency?

### Document Management
- Prototype stores filenames only, no actual file storage
- **Ask vendors:** Where are documents stored? Encryption at rest? Version control? OCR/data extraction? e-signature integration (DocuSign, etc.)?

### Workflow Configurability
- Prototype has config in code (requires developer to change)
- **Ask vendors:** Can business users configure UW rules? Pricing tables? Workflow steps? What requires professional services vs. self-service?

### Scalability & Compliance
- SQLite is single-file, not suitable for production
- **Ask vendors:** Database technology? Multi-tenancy model? TRID/RESPA compliance built-in? State-specific disclosure handling? Disaster recovery?

### Reporting
- Prototype has basic pipeline counts only
- **Ask vendors:** Built-in reports? Custom report builder? HMDA/CRA reporting? Data warehouse/BI tool integration?

### Borrower Experience
- Prototype is functional but basic
- **Ask vendors:** Mobile-responsive? White-labeling? Multilingual? Real-time status notifications? Secure messaging?
