"""Educational content about HELOCs — rendered within the main app."""

import streamlit as st


def render():
    st.markdown(
        '<h1 style="color:#1565c0;">Understanding Home Equity Lines of Credit</h1>',
        unsafe_allow_html=True,
    )
    st.markdown("*Brought to you by EquityEngine*")
    st.divider()

    # ── What is a HELOC? ──────────────────────────────────────────────────
    st.markdown("### What is a HELOC?")
    st.markdown(
        """
A **Home Equity Line of Credit (HELOC)** is a revolving line of credit
secured by your home. It works similarly to a credit card -- you're approved
for a maximum credit limit and can borrow as much or as little as you need,
when you need it.

Unlike a home equity loan (which gives you a lump sum), a HELOC gives you
**flexible, ongoing access** to funds during a "draw period," typically
5-10 years. You only pay interest on the amount you've actually borrowed.
"""
    )

    st.divider()

    # ── How does it work? ─────────────────────────────────────────────────
    st.markdown("### How Does a HELOC Work?")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
**Draw Period (typically 5-10 years)**
- Borrow up to your credit limit as needed
- Make interest-only payments on what you've borrowed
- Repay and re-borrow as many times as you want
- Variable interest rate (usually tied to Prime)
"""
        )

    with col2:
        st.markdown(
            """
**Repayment Period (typically 10-20 years)**
- No further draws allowed
- Pay back principal + interest
- Monthly payments may increase
- Some lenders offer conversion to fixed-rate
"""
        )

    st.divider()

    # ── Common uses ───────────────────────────────────────────────────────
    st.markdown("### Common Uses for a HELOC")
    st.markdown(
        """
| Use Case | Why a HELOC Works Well |
|----------|----------------------|
| **Home renovations** | Borrow in stages as projects progress; may increase home value |
| **Debt consolidation** | Lower rate than credit cards or personal loans |
| **Education expenses** | Draw funds semester by semester as tuition is due |
| **Emergency fund** | Available credit line for unexpected expenses |
| **Major purchases** | Large one-time expenses at a lower rate than alternatives |
"""
    )

    st.divider()

    # ── Key terms ─────────────────────────────────────────────────────────
    st.markdown("### Key Terms to Know")

    terms = {
        "LTV (Loan-to-Value)": (
            "Your existing mortgage balance divided by your home's appraised value. "
            "Lenders use this to assess risk."
        ),
        "CLTV (Combined LTV)": (
            "Your existing mortgage PLUS the HELOC amount, divided by home value. "
            "Most lenders cap this at 80%."
        ),
        "DTI (Debt-to-Income)": (
            "Your total monthly debt payments divided by your gross monthly income. "
            "Lenders typically want this below 43%."
        ),
        "Variable Rate": (
            "HELOC rates are usually variable, tied to the Prime rate plus a margin. "
            "Your rate (and payment) can change as Prime moves."
        ),
        "Draw Period": (
            "The initial phase (usually 5-10 years) when you can borrow against your line."
        ),
        "Interest-Only Payment": (
            "During the draw period, you may only be required to pay interest on "
            "the outstanding balance, not principal."
        ),
    }

    for term, definition in terms.items():
        st.markdown(f"**{term}** -- {definition}")

    st.divider()

    # ── Placeholder for more content ──────────────────────────────────────
    st.markdown("### Frequently Asked Questions")
    st.info(
        "This section is a placeholder. In a production application, this page would "
        "include detailed FAQs, comparison calculators, rate information, and "
        "regulatory disclosures."
    )

    st.divider()
    st.caption(
        "EquityEngine is a prototype application for educational and evaluation purposes only. "
        "This content is for demonstration and should not be considered financial advice."
    )
