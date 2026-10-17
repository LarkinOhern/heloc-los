"""Borrower document uploads (stub — filename only) and generated doc downloads."""

import os
import streamlit as st

from src.config import REQUIRED_DOCUMENTS
from src.utils.db_helpers import (
    get_applications_by_email, get_documents, create_document,
    get_generated_documents, get_conditions, add_audit_entry,
)
from src.utils.formatters import fmt_datetime
from src.documents.generator import OUTPUT_DIR


def render():
    st.header("Documents")
    st.caption(
        "Upload required documents to support your application and download any "
        "disclosures or letters generated during the process. Document upload is "
        "a stub in this prototype -- only the filename is recorded."
    )
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
    # Documents an open condition is waiting on (C-06).
    requested = {c["doc_type"] for c in get_conditions(app["id"])
                 if c["status"] == "OPEN" and c.get("doc_type")}

    for req in REQUIRED_DOCUMENTS:
        col1, col2, col3 = st.columns([3, 2, 1])
        col1.write(req["label"])
        if req["type"] in requested and req["type"] not in uploaded_types:
            col1.caption(":orange[**Requested** by your loan officer]")

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
                add_audit_entry(app["id"], "DOCUMENT_UPLOADED",
                                f"{req['label']}: {uploaded_file.name}", email)
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
            col2.caption(fmt_datetime(doc["generated_at"]))
            filepath = os.path.join(OUTPUT_DIR, doc["filename"])
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    col3.download_button(
                        "Download",
                        data=f.read(),
                        file_name=doc["filename"],
                        mime="application/pdf",
                        key=f"dl_gen_{doc['id']}",
                    )
            else:
                col3.caption("File not found")
    else:
        st.caption("No generated documents yet. Documents will appear here as your "
                   "application progresses.")
