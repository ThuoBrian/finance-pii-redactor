"""Scenario catalogue: sentence templates grouped by what they test.

Every template has one ``{x}`` placeholder. The corpus builder fills it and
records the filled value as gold, tagged with the scenario's category.
"""

from __future__ import annotations

# Should be redacted. The headline recall figure counts these.
RECALL = (
    "master_person",
    "master_org",
    "alias_org",
    "unlisted_person",
    "unlisted_org",
    "case_variant",
    "initials",
    "in_table",
    "bank_payment",
    "email_url",
)

# Format-specific recall scenarios, added only where the format allows.
EXCEL_ONLY = ("excel_header", "excel_tab")
PDF_ONLY = ("pdf_linebreak",)

# Documented design limits (docs/troubleshooting.md): reported, not counted
# against headline recall.
KNOWN_LIMITS = ("surname_only", "reordered_name")

# Should NOT be redacted. Feeds the false-positive table.
NEGATIVE = ("legal_terms", "places_months_finance")

PERSON_TEMPLATES = (
    "Reimbursement approved for {x} after the field visit.",
    "Per diem for the training was paid to {x} on Friday.",
    "The advance requested by {x} was cleared by finance.",
    "Please confirm the hotel booking made by {x} last week.",
    "Fuel receipts were submitted by {x} for the district trip.",
)

ORG_TEMPLATES = (
    "Invoice 2231 from {x} was paid in full.",
    "The contract with {x} was renewed for twelve months.",
    "Quotation received from {x} for the printing work.",
    "Final payment to {x} is pending approval.",
    "Grant tranche two was received from {x} in March.",
)

TEMPLATES: dict[str, tuple[str, ...]] = {
    "master_person": PERSON_TEMPLATES,
    "unlisted_person": PERSON_TEMPLATES,
    "case_variant": PERSON_TEMPLATES,
    "initials": PERSON_TEMPLATES,
    "pdf_linebreak": PERSON_TEMPLATES,
    "master_org": ORG_TEMPLATES,
    "alias_org": ORG_TEMPLATES,
    "unlisted_org": ORG_TEMPLATES,
    "surname_only": (
        "Ask {x} about the missing receipt.",
        "The petty cash float is held by {x} this month.",
    ),
    "reordered_name": (
        "{x} approved the travel advance.",
        "Approved by: {x}",
    ),
    "bank_payment": (
        "Transfer made to Account No: {x} on the due date.",
        "Pay the supplier through M-Pesa till {x} before Friday.",
        "Bank details: SWIFT {x} for the international transfer.",
    ),
    "email_url": (
        "Send the signed claim form to {x} by Monday.",
        "The supplier price list is published at {x} for reference.",
    ),
    "legal_terms": (
        "This agreement is subject to the {x} clause in section four.",
        "Refer to the {x} before signing.",
    ),
    "places_months_finance": (
        "The workshop costs were booked under {x}.",
        "All figures for {x} are reported in the summary.",
    ),
}

LEGAL_TERMS = (
    "Force Majeure",
    "Governing Law",
    "Effective Date",
    "Project Lighthouse",
    "Statement of Work",
    "Terms and Conditions",
    "Steering Committee",
    "Grant Agreement",
    "Finance Department",
    "Annex B",
)

PLACES_MONTHS_FINANCE = (
    "Nairobi",
    "Kampala",
    "Accra",
    "Lusaka",
    "March",
    "September",
    "Accounts Payable",
    "Petty Cash",
    "Value Added Tax",
    "Cost of Sales",
)
