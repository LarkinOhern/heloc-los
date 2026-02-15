"""Borrower document uploads (stub — filename only) and generated doc downloads."""

import streamlit as st

from src.config import REQUIRED_DOCUMENTS
from src.utils.db_helpers import (
    get_applications_by_email, get_documents, create_document,
    get_generated_documents,
)
from src.utils.formatters import fmt_datetime


def render():
    st.header("Documents")
    email = st.session_state.get("borrower_email", "")
    if not email:
        st.warning("Enter your email in the sidebar.")
        return

    apps = get_applications_by_email(email)
    apps = [a for a in apps if a["status"] != "DRAFT"]

    if not apps:
        st.info("No submitted applications found. Go to **Apply** to start.")
        return

    # Pick application
    if len(apps) == 1:
        app = apps[0]
    else:
        options = {a["application_number"]: a for a in apps}
        selected = st.selectbox("Select Application", list(options.keys()))
        app = options[selected]

    st.subheader(f"Documents for {app['application_number']}")

    # ── Upload Required Documents ────────────────────────────────────────
    st.write("**Required Documents**")
    st.caption("Upload is a stub — only the filename is recorded, no actual file storage.")

    existing_docs = get_documents(app["id"])
    uploaded_types = {d["doc_type"] for d in existing_docs}

    for req in REQUIRED_DOCUMENTS:
        col1, col2, col3 = st.columns([3, 2, 1])
        col1.write(req["label"])

        if req["type"] in uploaded_types:
            doc = next(d for d in existing_docs if d["doc_type"] == req["type"])
            col2.success(f"Uploaded: {doc['filename']}")
            col3.caption(fmt_datetime(doc["uploaded_at"]))
        else:
            uploaded_file = col2.file_uploader(
                f"Upload {req['label']}",
                key=f"upload_{req['type']}",
                label_visibility="collapsed",
            )
            if uploaded_file is not None:
                create_document(
                    app["id"],
                    doc_type=req["type"],
                    filename=uploaded_file.name,
                    uploaded_by=email,
                )
                st.rerun()
            col3.write("")

    # Completion summary
    uploaded_count = len(uploaded_types)
    total_required = len(REQUIRED_DOCUMENTS)
    st.progress(uploaded_count / total_required if total_required else 0)
    st.caption(f"{uploaded_count} of {total_required} required documents uploaded")

    # ── Generated Documents (downloads) ──────────────────────────────────
    st.divider()
    st.write("**Generated Documents**")
    gen_docs = get_generated_documents(app["id"])

    if gen_docs:
        for doc in gen_docs:
            col1, col2, col3 = st.columns([3, 2, 1])
            col1.write(doc["doc_type"].replace("_", " ").title())
            col2.write(doc["filename"])
            col3.caption(fmt_datetime(doc["generated_at"]))
    else:
        st.caption("No generated documents yet. Documents will appear here as your "
                   "application progresses.")
