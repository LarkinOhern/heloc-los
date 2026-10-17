"""Multi-step HELOC application wizard.

Steps: Property → Borrower → Co-Borrower → Employment → Assets/Debts → Review/Submit
Each step saves to DB on "Next" so the borrower can resume later.
"""

import streamlit as st
import streamlit.components.v1 as components

from src.config import (
    PROPERTY_TYPES, PROPERTY_TYPE_LABELS, MIN_HELOC_AMOUNT, MAX_HELOC_AMOUNT,
    MIN_PROPERTY_VALUE,
)
from src.utils.db_helpers import (
    create_application, get_applications_by_email, get_application,
    update_application, create_borrower, get_borrowers, update_borrower,
    delete_borrower, create_employment, get_employment, delete_employment,
    create_asset, get_assets, delete_asset, create_debt, get_debts,
    delete_debt, add_audit_entry,
)
from src.documents.generator import generate_initial_disclosure
from src.utils.formatters import fmt_currency, fmt_date, now_utc, md_escape

STEPS = ["Property", "Borrower", "Co-Borrower", "Employment", "Assets & Debts", "Review & Submit"]

CITIZENSHIP_OPTIONS = ["US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT"]
CITIZENSHIP_LABELS = {
    "US_CITIZEN": "U.S. citizen",
    "PERMANENT_RESIDENT": "Permanent resident",
    "NON_PERMANENT_RESIDENT": "Non-permanent resident",
}

US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
]


def render():
    st.header("Apply for a HELOC")
    st.caption(
        "Complete each step below to submit your application. Your progress "
        "is saved automatically -- close the browser and come back anytime."
    )
    email = st.session_state.get("borrower_email", "")
    if not email:
        st.warning("Enter your email in the sidebar to begin.")
        return

    # ── Just submitted: keep the confirmation on screen ─────────────────────
    # The success message used to vanish on the next click, which dropped the
    # borrower on a blank "start a new application" page (finding O-01).
    done = st.session_state.get("just_submitted")
    if done and done[0] == email and "app_id" not in st.session_state:
        st.success(
            f"Application **{done[1]}** was submitted. Track it on the **Status** "
            f"page. Your initial disclosure is under **Documents**."
        )
        if st.button("Start another application"):
            st.session_state.pop("just_submitted", None)
            st.rerun()
        return

    # ── Resume or start new ──────────────────────────────────────────────────
    if "app_id" not in st.session_state:
        _pick_or_create_application(email)
        return

    app = get_application(st.session_state["app_id"])
    if not app:
        st.error("Application not found.")
        st.session_state.pop("app_id", None)
        return

    if app["status"] != "DRAFT":
        st.info(f"Application **{app['application_number']}** has been submitted. "
                f"Check the **Status** page for updates.")
        if st.button("Start a new application"):
            st.session_state.pop("app_id", None)
            st.rerun()
        return

    # ── Step navigation ──────────────────────────────────────────────────────
    step = st.session_state.get("wizard_step", 0)
    reachable = max(step, first_open_step(app))

    # Progress bar. Any step up to the first unfinished one is a button, so a
    # returning borrower can jump straight to where they were (finding F-06).
    cols = st.columns(len(STEPS))
    for i, label in enumerate(STEPS):
        if i == step:
            cols[i].info(f"**{label}**")
        elif i <= reachable:
            if cols[i].button(f"✓ {label}" if i < reachable else label,
                              key=f"goto_step_{i}", use_container_width=True):
                st.session_state["wizard_step"] = i
                st.rerun()
        else:
            cols[i].write(label)

    st.divider()

    # Bring the new step's heading into view; the page used to stay scrolled
    # to where the previous step's button was (finding O-02).
    if st.session_state.get("_last_step_shown") != step:
        st.session_state["_last_step_shown"] = step
        components.html(
            "<script>const m = window.parent.document.querySelector("
            "'section.stMain, section.main, [data-testid=stMain]');"
            "if (m) m.scrollTo({top: 0}); window.parent.scrollTo({top: 0});</script>",
            height=0,
        )

    # Render the current step
    if step == 0:
        _step_property(app)
    elif step == 1:
        _step_borrower(app)
    elif step == 2:
        _step_coborrower(app)
    elif step == 3:
        _step_employment(app)
    elif step == 4:
        _step_assets_debts(app)
    elif step == 5:
        _step_review_submit(app)


# ── Add-forms that start empty after each add ─────────────────────────────────

def _form_version(name: str) -> int:
    """Version number baked into an add-form's widget keys.

    Bumping it after a successful add gives the next render brand-new, empty
    widgets, so a second click can't re-add the same entry (finding F-05).
    A failed validation keeps the version, so the borrower's input stays put.
    """
    return st.session_state.get(f"_formv_{name}", 0)


def _bump_form(name: str):
    st.session_state[f"_formv_{name}"] = _form_version(name) + 1


# ── Pick / Create Application ────────────────────────────────────────────────

def first_open_step(app: dict) -> int:
    """The first wizard step that still needs input, used when resuming.

    Co-borrower and assets/debts are optional, so a draft with income on file
    resumes at Assets & Debts, and one with assets or debts at Review.
    """
    if not (app["property_address"] and app["property_value"] > 0
            and app["heloc_amount_requested"] > 0):
        return 0
    primary = next((b for b in get_borrowers(app["id"]) if b["is_primary"]), None)
    if not primary or not primary["first_name"]:
        return 1
    if not get_employment(primary["id"]):
        return 2
    if not get_assets(primary["id"]) and not get_debts(primary["id"]):
        return 4
    return 5


def _pick_or_create_application(email: str):
    existing = get_applications_by_email(email)
    drafts = [a for a in existing if a["status"] == "DRAFT"]

    if drafts:
        st.subheader("Resume an existing application")
        for d in drafts:
            col1, col2, col3 = st.columns([3, 2, 1])
            col1.write(f"**{d['application_number']}**")
            col2.write(f"Created: {fmt_date(d['created_at'])}")
            if col3.button("Resume", key=f"resume_{d['id']}"):
                st.session_state["app_id"] = d["id"]
                st.session_state["wizard_step"] = first_open_step(d)
                st.rerun()
        st.divider()

    st.subheader("Start a new application")
    if st.button("Begin New Application"):
        app_id = create_application()
        create_borrower(app_id, is_primary=True, email=email)
        add_audit_entry(app_id, "APPLICATION_CREATED", "Draft application created", email)
        st.session_state["app_id"] = app_id
        st.session_state["wizard_step"] = 0
        st.rerun()


# ── Step 0: Property ─────────────────────────────────────────────────────────

def _step_property(app: dict):
    st.subheader("Property Information")
    st.caption(
        "Tell us about the property securing this HELOC. We use the property value "
        "and your existing mortgage balance to calculate your available equity."
    )

    with st.form("property_form"):
        property_type = st.selectbox(
            "Property Type",
            PROPERTY_TYPES,
            format_func=lambda x: PROPERTY_TYPE_LABELS.get(x, x),
            index=PROPERTY_TYPES.index(app["property_type"]) if app["property_type"] in PROPERTY_TYPES else 0,
        )
        address = st.text_input("Street Address", value=app["property_address"])
        col1, col2, col3 = st.columns(3)
        city = col1.text_input("City", value=app["property_city"])
        state = col2.selectbox(
            "State", US_STATES,
            index=US_STATES.index(app["property_state"]) if app["property_state"] in US_STATES else 0,
        )
        zipcode = col3.text_input("ZIP Code", value=app["property_zip"])

        property_value = st.number_input(
            "Estimated Property Value ($)",
            min_value=0.0, step=10000.0, value=float(app["property_value"]),
        )
        existing_mortgage = st.number_input(
            "Current Mortgage Balance ($)",
            min_value=0.0, step=5000.0, value=float(app["existing_mortgage_balance"]),
        )

        st.divider()
        heloc_amount = st.number_input(
            "HELOC Amount Requested ($)",
            min_value=0.0, step=5000.0, value=float(app["heloc_amount_requested"]),
        )
        heloc_purpose = st.text_area(
            "Purpose of HELOC",
            value=app["heloc_purpose"],
            placeholder="e.g., Home renovation, debt consolidation, education expenses",
        )
        autopay = st.checkbox(
            "Enroll in autopay (0.25% rate discount)",
            value=bool(app["autopay_enrolled"]),
        )

        submitted = st.form_submit_button("Save & Continue")

    if submitted:
        errors = []
        if not address.strip():
            errors.append("Street address is required.")
        if not city.strip():
            errors.append("City is required.")
        if not zipcode.strip():
            errors.append("ZIP code is required.")
        if property_value < MIN_PROPERTY_VALUE:
            errors.append(f"Property value must be at least {fmt_currency(MIN_PROPERTY_VALUE)}.")
        if heloc_amount < MIN_HELOC_AMOUNT:
            errors.append(f"HELOC amount must be at least {fmt_currency(MIN_HELOC_AMOUNT)}.")
        if heloc_amount > MAX_HELOC_AMOUNT:
            errors.append(f"HELOC amount cannot exceed {fmt_currency(MAX_HELOC_AMOUNT)}.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            update_application(
                app["id"],
                property_type=property_type,
                property_address=address.strip(),
                property_city=city.strip(),
                property_state=state,
                property_zip=zipcode.strip(),
                property_value=property_value,
                existing_mortgage_balance=existing_mortgage,
                heloc_amount_requested=heloc_amount,
                heloc_purpose=heloc_purpose.strip(),
                autopay_enrolled=int(autopay),
            )
            st.session_state["wizard_step"] = 1
            st.rerun()


# ── Step 1: Primary Borrower ─────────────────────────────────────────────────

def _step_borrower(app: dict):
    st.subheader("Primary Borrower Information")
    st.caption(
        "We need some basic information about you. Your credit score is self-reported "
        "for this prototype -- a production system would pull it from a credit bureau."
    )

    borrowers = get_borrowers(app["id"])
    primary = next((b for b in borrowers if b["is_primary"]), None)
    if not primary:
        primary = {"first_name": "", "last_name": "", "email": st.session_state.get("borrower_email", ""),
                    "phone": "", "ssn_last4": "", "date_of_birth": "", "credit_score": 0,
                    "citizenship": "US_CITIZEN"}

    with st.form("borrower_form"):
        col1, col2 = st.columns(2)
        first = col1.text_input("First Name", value=primary["first_name"])
        last = col2.text_input("Last Name", value=primary["last_name"])

        col1, col2 = st.columns(2)
        email = col1.text_input("Email", value=primary["email"])
        phone = col2.text_input("Phone", value=primary["phone"])

        col1, col2 = st.columns(2)
        ssn4 = col1.text_input("Last 4 of SSN", value=primary["ssn_last4"], max_chars=4)
        dob = col2.text_input("Date of Birth (YYYY-MM-DD)", value=primary["date_of_birth"])

        # Blank until the borrower enters it. Defaulting to 300 meant an
        # untouched field submitted the lowest possible score (finding O-03).
        credit_score = st.number_input(
            "Self-Reported Credit Score",
            min_value=300, max_value=850, step=1,
            value=primary["credit_score"] or None,
            placeholder="300–850",
            help="This is self-reported for the prototype. A real system would pull from a credit bureau.",
        )

        citizenship = st.selectbox(
            "Citizenship Status",
            CITIZENSHIP_OPTIONS,
            format_func=CITIZENSHIP_LABELS.get,
            index=CITIZENSHIP_OPTIONS.index(primary["citizenship"])
            if primary.get("citizenship") in CITIZENSHIP_OPTIONS else 0,
        )

        col_back, col_next = st.columns(2)
        back = col_back.form_submit_button("Back")
        submitted = col_next.form_submit_button("Save & Continue")

    if back:
        st.session_state["wizard_step"] = 0
        st.rerun()

    if submitted:
        errors = []
        if not first.strip():
            errors.append("First name is required.")
        if not last.strip():
            errors.append("Last name is required.")
        if not email.strip():
            errors.append("Email is required.")
        if credit_score is None:
            errors.append("Enter your credit score (300–850). An estimate is fine.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            data = dict(
                first_name=first.strip(), last_name=last.strip(),
                email=email.strip().lower(), phone=phone.strip(),
                ssn_last4=ssn4.strip(), date_of_birth=dob.strip(),
                credit_score=credit_score, citizenship=citizenship,
            )
            if primary.get("id"):
                update_borrower(primary["id"], **data)
            else:
                create_borrower(app["id"], is_primary=True, **data)
            st.session_state["wizard_step"] = 2
            st.rerun()


# ── Step 2: Co-Borrower (Optional) ───────────────────────────────────────────

def _step_coborrower(app: dict):
    st.subheader("Co-Borrower Information (Optional)")
    st.caption(
        "Adding a co-borrower combines household income for qualification purposes "
        "and may help you qualify for a larger credit line or better rate."
    )

    borrowers = get_borrowers(app["id"])
    coborrower = next((b for b in borrowers if not b["is_primary"]), None)

    has_co = st.checkbox(
        "I have a co-borrower",
        value=coborrower is not None,
        key="has_coborrower",
    )

    if has_co:
        cb = coborrower or {"first_name": "", "last_name": "", "email": "",
                             "phone": "", "ssn_last4": "", "date_of_birth": "",
                             "credit_score": 0, "citizenship": "US_CITIZEN"}

        with st.form("coborrower_form"):
            col1, col2 = st.columns(2)
            first = col1.text_input("First Name", value=cb["first_name"])
            last = col2.text_input("Last Name", value=cb["last_name"])

            col1, col2 = st.columns(2)
            email = col1.text_input("Email", value=cb["email"])
            phone = col2.text_input("Phone", value=cb["phone"])

            col1, col2 = st.columns(2)
            ssn4 = col1.text_input("Last 4 of SSN", value=cb["ssn_last4"], max_chars=4)
            dob = col2.text_input("Date of Birth (YYYY-MM-DD)", value=cb["date_of_birth"])

            credit_score = st.number_input(
                "Self-Reported Credit Score",
                min_value=300, max_value=850, step=1,
                value=cb["credit_score"] or None,
                placeholder="300–850",
            )

            citizenship = st.selectbox(
                "Citizenship Status",
                CITIZENSHIP_OPTIONS,
                format_func=CITIZENSHIP_LABELS.get,
                index=CITIZENSHIP_OPTIONS.index(cb["citizenship"])
                if cb.get("citizenship") in CITIZENSHIP_OPTIONS else 0,
            )

            col_back, col_next = st.columns(2)
            back = col_back.form_submit_button("Back")
            submitted = col_next.form_submit_button("Save & Continue")

        if back:
            st.session_state["wizard_step"] = 1
            st.rerun()

        if submitted:
            errors = []
            if not first.strip():
                errors.append("Co-borrower first name is required.")
            if not last.strip():
                errors.append("Co-borrower last name is required.")
            if credit_score is None:
                errors.append("Enter the co-borrower's credit score (300–850).")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                data = dict(
                    first_name=first.strip(), last_name=last.strip(),
                    email=email.strip().lower(), phone=phone.strip(),
                    ssn_last4=ssn4.strip(), date_of_birth=dob.strip(),
                    credit_score=credit_score, citizenship=citizenship,
                )
                if coborrower and coborrower.get("id"):
                    update_borrower(coborrower["id"], **data)
                else:
                    create_borrower(app["id"], is_primary=False, **data)
                st.session_state["wizard_step"] = 3
                st.rerun()
    else:
        # Remove co-borrower if they unchecked
        if coborrower and coborrower.get("id"):
            delete_borrower(coborrower["id"])

        col_back, col_next = st.columns(2)
        if col_back.button("Back"):
            st.session_state["wizard_step"] = 1
            st.rerun()
        if col_next.button("Skip & Continue"):
            st.session_state["wizard_step"] = 3
            st.rerun()


# ── Step 3: Employment / Income ───────────────────────────────────────────────

def _step_employment(app: dict):
    st.subheader("Employment & Income")
    st.caption(
        "List all income sources for each borrower. Stable, verifiable income "
        "strengthens your application. Include salary, self-employment, retirement, "
        "and any other recurring income."
    )

    borrowers = get_borrowers(app["id"])

    for b in borrowers:
        label = "Primary Borrower" if b["is_primary"] else "Co-Borrower"
        st.write(f"**{label}: {b['first_name']} {b['last_name']}**")

        existing_jobs = get_employment(b["id"])

        # Show existing employment entries
        for job in existing_jobs:
            with st.expander(
                f"{job['employer_name']} — {fmt_currency(job['monthly_income'])}/mo",
                expanded=False,
            ):
                st.write(f"**Position:** {job['position']}")
                st.write(f"**Years:** {job['years_employed']}")
                st.write(f"**Type:** {job['income_type']}")
                if st.button("Remove", key=f"del_emp_{job['id']}"):
                    delete_employment(job["id"])
                    st.rerun()

        # Add new employment
        v = _form_version(f"emp_{b['id']}")
        with st.form(f"emp_form_{b['id']}_{v}"):
            st.caption("Add income source")
            col1, col2 = st.columns(2)
            employer = col1.text_input("Employer Name", key=f"emp_name_{b['id']}_{v}")
            position = col2.text_input("Position / Title", key=f"emp_pos_{b['id']}_{v}")

            col1, col2, col3 = st.columns(3)
            income_type = col1.selectbox(
                "Income Type",
                ["SALARY", "HOURLY", "SELF_EMPLOYED", "RETIREMENT", "OTHER"],
                format_func=lambda x: x.replace("_", " ").title(),
                key=f"emp_type_{b['id']}_{v}",
            )
            monthly_income = col2.number_input(
                "Monthly Income ($)", min_value=0.0, step=500.0,
                key=f"emp_income_{b['id']}_{v}",
            )
            years = col3.number_input(
                "Years Employed", min_value=0.0, step=0.5,
                key=f"emp_years_{b['id']}_{v}",
            )

            add_emp = st.form_submit_button(f"Add Income for {b['first_name']}")

        if add_emp and not (employer.strip() and monthly_income > 0):
            st.error("Enter an employer name and a monthly income above $0 to add this income source.")
        elif add_emp:
            create_employment(
                b["id"],
                employer_name=employer.strip(),
                position=position.strip(),
                years_employed=years,
                monthly_income=monthly_income,
                income_type=income_type,
            )
            _bump_form(f"emp_{b['id']}")
            st.rerun()

        st.divider()

    # Navigation
    col_back, col_next = st.columns(2)
    if col_back.button("Back"):
        st.session_state["wizard_step"] = 2
        st.rerun()

    # Validate at least one income source for primary borrower
    primary = next((b for b in borrowers if b["is_primary"]), None)
    has_income = bool(get_employment(primary["id"])) if primary else False

    if col_next.button("Save & Continue"):
        if not has_income:
            st.error("At least one income source is required for the primary borrower.")
        else:
            st.session_state["wizard_step"] = 4
            st.rerun()


# ── Step 4: Assets & Debts ───────────────────────────────────────────────────

def _step_assets_debts(app: dict):
    st.subheader("Assets & Debts")
    st.caption(
        "List your financial accounts and monthly obligations. We use this to "
        "calculate your debt-to-income ratio (DTI), a key factor in underwriting."
    )

    borrowers = get_borrowers(app["id"])
    primary = next((b for b in borrowers if b["is_primary"]), None)
    if not primary:
        st.error("Primary borrower not found.")
        return

    # Use primary borrower for assets/debts (simplification)
    bid = primary["id"]

    # ── Assets ────────────────────────────────────────────────────────────
    st.write("**Assets**")
    existing_assets = get_assets(bid)

    for asset in existing_assets:
        col1, col2, col3 = st.columns([3, 2, 1])
        col1.write(f"{asset['institution']} ({asset['account_type']})")
        col2.write(fmt_currency(asset["balance"]))
        if col3.button("Remove", key=f"del_asset_{asset['id']}"):
            delete_asset(asset["id"])
            st.rerun()

    av = _form_version("asset")
    with st.form(f"asset_form_{av}"):
        st.caption("Add asset account")
        col1, col2, col3 = st.columns(3)
        acct_type = col1.selectbox(
            "Account Type",
            ["CHECKING", "SAVINGS", "INVESTMENT", "RETIREMENT", "OTHER"],
            format_func=lambda x: x.title(),
            key=f"asset_type_{av}",
        )
        institution = col2.text_input("Financial Institution", key=f"asset_inst_{av}")
        balance = col3.number_input("Balance ($)", min_value=0.0, step=1000.0,
                                    key=f"asset_bal_{av}")
        add_asset = st.form_submit_button("Add Asset")

    if add_asset and not (institution.strip() and balance > 0):
        st.error("Enter the institution and a balance above $0 to add this account.")
    elif add_asset:
        create_asset(bid, account_type=acct_type, institution=institution.strip(), balance=balance)
        _bump_form("asset")
        st.rerun()

    st.divider()

    # ── Debts ─────────────────────────────────────────────────────────────
    st.write("**Monthly Debts / Obligations**")
    existing_debts = get_debts(bid)

    for debt in existing_debts:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        col1.write(f"{debt['creditor']} ({debt['debt_type']})")
        col2.write(f"{fmt_currency(debt['monthly_payment'])}/mo")
        col3.write(f"Bal: {fmt_currency(debt['balance'])}")
        if col4.button("Remove", key=f"del_debt_{debt['id']}"):
            delete_debt(debt["id"])
            st.rerun()

    dv = _form_version("debt")
    with st.form(f"debt_form_{dv}"):
        st.caption("Add monthly obligation")
        col1, col2 = st.columns(2)
        debt_type = col1.selectbox(
            "Debt Type",
            ["MORTGAGE", "AUTO", "STUDENT", "CREDIT_CARD", "PERSONAL", "OTHER"],
            format_func=lambda x: x.replace("_", " ").title(),
            key=f"debt_type_{dv}",
        )
        creditor = col2.text_input("Creditor Name", key=f"debt_cred_{dv}")
        col1, col2 = st.columns(2)
        monthly_payment = col1.number_input("Monthly Payment ($)", min_value=0.0, step=100.0,
                                            key=f"debt_pmt_{dv}")
        debt_balance = col2.number_input("Outstanding Balance ($)", min_value=0.0, step=1000.0,
                                         key=f"debt_bal_{dv}")
        add_debt = st.form_submit_button("Add Debt")

    if add_debt and not (creditor.strip() and monthly_payment > 0):
        st.error("Enter the creditor and a monthly payment above $0 to add this debt.")
    elif add_debt:
        create_debt(
            bid, debt_type=debt_type, creditor=creditor.strip(),
            monthly_payment=monthly_payment, balance=debt_balance,
        )
        _bump_form("debt")
        st.rerun()

    st.divider()

    # Navigation
    col_back, col_next = st.columns(2)
    if col_back.button("Back"):
        st.session_state["wizard_step"] = 3
        st.rerun()
    if col_next.button("Save & Continue to Review"):
        st.session_state["wizard_step"] = 5
        st.rerun()


# ── Step 5: Review & Submit ──────────────────────────────────────────────────

def _step_review_submit(app: dict):
    st.subheader("Review Your Application")
    st.caption(
        "Please review all information below before submitting. After submission, "
        "you'll receive an initial disclosure and can track your application status."
    )

    # Refresh app data
    app = get_application(app["id"])
    borrowers = get_borrowers(app["id"])
    primary = next((b for b in borrowers if b["is_primary"]), None)
    coborrower = next((b for b in borrowers if not b["is_primary"]), None)

    # Property
    st.write("**Property**")
    col1, col2 = st.columns(2)
    col1.write(f"Address: {app['property_address']}, {app['property_city']}, "
               f"{app['property_state']} {app['property_zip']}")
    col2.write(f"Type: {PROPERTY_TYPE_LABELS.get(app['property_type'], app['property_type'])}")
    col1, col2, col3 = st.columns(3)
    col1.metric("Property Value", fmt_currency(app["property_value"]))
    col2.metric("Existing Mortgage", fmt_currency(app["existing_mortgage_balance"]))
    col3.metric("HELOC Requested", fmt_currency(app["heloc_amount_requested"]))
    if app["heloc_purpose"]:
        st.write(f"**Purpose:** {app['heloc_purpose']}")
    st.write(f"**Autopay:** {'Yes' if app['autopay_enrolled'] else 'No'}")

    st.divider()

    # Primary borrower
    if primary:
        st.write("**Primary Borrower**")
        col1, col2 = st.columns(2)
        col1.write(f"Name: {primary['first_name']} {primary['last_name']}")
        col2.write(f"Credit Score: {primary['credit_score']} (self-reported)")

        jobs = get_employment(primary["id"])
        total_income = sum(j["monthly_income"] for j in jobs)
        st.write(f"Monthly Income: {fmt_currency(total_income)} "
                 f"({len(jobs)} source{'s' if len(jobs) != 1 else ''})")

    # Co-borrower
    if coborrower:
        st.divider()
        st.write("**Co-Borrower**")
        col1, col2 = st.columns(2)
        col1.write(f"Name: {coborrower['first_name']} {coborrower['last_name']}")
        col2.write(f"Credit Score: {coborrower['credit_score']} (self-reported)")

        co_jobs = get_employment(coborrower["id"])
        co_income = sum(j["monthly_income"] for j in co_jobs)
        st.write(f"Monthly Income: {fmt_currency(co_income)} "
                 f"({len(co_jobs)} source{'s' if len(co_jobs) != 1 else ''})")

    # Assets & debts summary
    if primary:
        st.divider()
        assets = get_assets(primary["id"])
        debts = get_debts(primary["id"])
        col1, col2 = st.columns(2)
        col1.metric("Total Assets", fmt_currency(sum(a["balance"] for a in assets)))
        col2.metric("Total Monthly Debts", fmt_currency(sum(d["monthly_payment"] for d in debts)))

        # The mortgage balance is asked for twice; flag a mismatch (O-04).
        mortgages = [d for d in debts if d["debt_type"] == "MORTGAGE"]
        if mortgages:
            listed = sum(d["balance"] for d in mortgages)
            stated = app["existing_mortgage_balance"]
            if abs(listed - stated) > max(1000, 0.02 * stated):
                st.warning(md_escape(
                    f"Your mortgage balance on the Property step ({fmt_currency(stated)}) "
                    f"doesn't match the mortgage you listed under debts "
                    f"({fmt_currency(listed)}). Go back and correct whichever is wrong."
                ))

    st.divider()

    # E-consent
    econsent = st.checkbox(
        "I consent to receive electronic disclosures and communications.",
        value=bool(app["econsent_given"]),
        key="econsent_check",
    )

    # Navigation
    col_back, col_submit = st.columns(2)
    if col_back.button("Back"):
        st.session_state["wizard_step"] = 4
        st.rerun()

    if col_submit.button("Submit Application", type="primary"):
        if not econsent:
            st.error("You must consent to electronic disclosures to submit.")
        else:
            now = now_utc()
            update_application(
                app["id"],
                status="SUBMITTED",
                econsent_given=1,
                econsent_date=now,
                submitted_at=now,
            )
            add_audit_entry(
                app["id"], "STATUS_CHANGE",
                "Status changed from DRAFT to SUBMITTED",
                st.session_state.get("borrower_email", ""),
            )
            # Generate initial disclosure PDF on submit
            generate_initial_disclosure(app["id"])
            add_audit_entry(
                app["id"], "DOCUMENT_GENERATED",
                "Initial Disclosure generated",
                st.session_state.get("borrower_email", ""),
            )
            st.success(f"Application **{app['application_number']}** submitted successfully!")
            st.balloons()
            st.session_state["just_submitted"] = (
                st.session_state.get("borrower_email", ""), app["application_number"],
            )
            st.session_state.pop("app_id", None)
            st.session_state.pop("wizard_step", None)
