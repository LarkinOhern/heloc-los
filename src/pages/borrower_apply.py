"""Multi-step HELOC application wizard.

Steps: Property → Borrower → Co-Borrower → Employment → Assets/Debts → Review/Submit
Each step saves to DB on "Next" so the borrower can resume later.
"""

import streamlit as st

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
from src.utils.formatters import fmt_currency, fmt_date, now_utc

STEPS = ["Property", "Borrower", "Co-Borrower", "Employment", "Assets & Debts", "Review & Submit"]

US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
]


def render():
    st.header("Apply for a HELOC")
    email = st.session_state.get("borrower_email", "")
    if not email:
        st.warning("Enter your email in the sidebar to begin.")
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

    # Progress bar
    cols = st.columns(len(STEPS))
    for i, label in enumerate(STEPS):
        marker = "**>>> " + label + " <<<**" if i == step else label
        if i < step:
            cols[i].success(label)
        elif i == step:
            cols[i].info(f"**{label}**")
        else:
            cols[i].write(label)

    st.divider()

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


# ── Pick / Create Application ────────────────────────────────────────────────

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
                st.session_state["wizard_step"] = 0
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

        credit_score = st.number_input(
            "Self-Reported Credit Score",
            min_value=300, max_value=850, step=1,
            value=max(primary["credit_score"], 300),
            help="This is self-reported for the prototype. A real system would pull from a credit bureau.",
        )

        citizenship = st.selectbox(
            "Citizenship Status",
            ["US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT"],
            format_func=lambda x: x.replace("_", " ").title(),
            index=["US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT"].index(
                primary.get("citizenship", "US_CITIZEN")
            ) if primary.get("citizenship") in ["US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT"] else 0,
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
    st.caption("Adding a co-borrower can combine income for qualification.")

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
                value=max(cb["credit_score"], 300),
            )

            citizenship = st.selectbox(
                "Citizenship Status",
                ["US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT"],
                format_func=lambda x: x.replace("_", " ").title(),
                index=["US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT"].index(
                    cb.get("citizenship", "US_CITIZEN")
                ) if cb.get("citizenship") in ["US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT"] else 0,
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
        with st.form(f"emp_form_{b['id']}"):
            st.caption("Add income source")
            col1, col2 = st.columns(2)
            employer = col1.text_input("Employer Name", key=f"emp_name_{b['id']}")
            position = col2.text_input("Position / Title", key=f"emp_pos_{b['id']}")

            col1, col2, col3 = st.columns(3)
            income_type = col1.selectbox(
                "Income Type",
                ["SALARY", "HOURLY", "SELF_EMPLOYED", "RETIREMENT", "OTHER"],
                format_func=lambda x: x.replace("_", " ").title(),
                key=f"emp_type_{b['id']}",
            )
            monthly_income = col2.number_input(
                "Monthly Income ($)", min_value=0.0, step=500.0,
                key=f"emp_income_{b['id']}",
            )
            years = col3.number_input(
                "Years Employed", min_value=0.0, step=0.5,
                key=f"emp_years_{b['id']}",
            )

            add_emp = st.form_submit_button(f"Add Income for {b['first_name']}")

        if add_emp and employer.strip() and monthly_income > 0:
            create_employment(
                b["id"],
                employer_name=employer.strip(),
                position=position.strip(),
                years_employed=years,
                monthly_income=monthly_income,
                income_type=income_type,
            )
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

    with st.form("asset_form"):
        st.caption("Add asset account")
        col1, col2, col3 = st.columns(3)
        acct_type = col1.selectbox(
            "Account Type",
            ["CHECKING", "SAVINGS", "INVESTMENT", "RETIREMENT", "OTHER"],
            format_func=lambda x: x.title(),
        )
        institution = col2.text_input("Financial Institution")
        balance = col3.number_input("Balance ($)", min_value=0.0, step=1000.0)
        add_asset = st.form_submit_button("Add Asset")

    if add_asset and institution.strip() and balance > 0:
        create_asset(bid, account_type=acct_type, institution=institution.strip(), balance=balance)
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

    with st.form("debt_form"):
        st.caption("Add monthly obligation")
        col1, col2 = st.columns(2)
        debt_type = col1.selectbox(
            "Debt Type",
            ["MORTGAGE", "AUTO", "STUDENT", "CREDIT_CARD", "PERSONAL", "OTHER"],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        creditor = col2.text_input("Creditor Name")
        col1, col2 = st.columns(2)
        monthly_payment = col1.number_input("Monthly Payment ($)", min_value=0.0, step=100.0)
        debt_balance = col2.number_input("Outstanding Balance ($)", min_value=0.0, step=1000.0)
        add_debt = st.form_submit_button("Add Debt")

    if add_debt and creditor.strip() and monthly_payment > 0:
        create_debt(
            bid, debt_type=debt_type, creditor=creditor.strip(),
            monthly_payment=monthly_payment, balance=debt_balance,
        )
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
            st.success(f"Application **{app['application_number']}** submitted successfully!")
            st.balloons()
            st.session_state.pop("app_id", None)
            st.session_state.pop("wizard_step", None)
