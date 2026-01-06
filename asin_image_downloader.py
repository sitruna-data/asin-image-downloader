# app.py
import io
import math
import os
import re
import time
import uuid
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

# ------------------------------
# Streamlit Setup (must be first)
# ------------------------------
st.set_page_config(page_title="ASIN Image Downloader", layout="centered")

st.title("Sitruna ASIN Image Downloader")
st.write(
    """
This tool downloads and renames images for each ASIN, packaged into ZIP files of **40 ASINs per batch**.
Batches are created **in memory** and offered via `Download` buttons. 
"""
)

# ------------------------------
# Helpers
# ------------------------------
def is_valid_url(url: object) -> bool:
    """
    Rejects null-like strings and non-http(s) schemes.
    Why: Avoids time wasted on bad cells and data URIs.
    """
    if url is None:
        return False
    s = str(url).strip().lower()
    if s in {"", "nan", "none", "null", "na", "true", "false"}:
        return False
    return s.startswith("http://") or s.startswith("https://")


def infer_ext(url: str, content_type: Optional[str]) -> str:
    """
    Try to infer a sensible file extension.
    Why: Not all images are JPEG; keeps filenames compatible.
    """
    # From URL
    path = re.sub(r"[?#].*$", "", url)
    m = re.search(r"\.(jpe?g|png|gif|webp|bmp|tiff?)$", path, re.I)
    if m:
        return "." + m.group(1).lower()

    # From Content-Type
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        mapping = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
            "image/tiff": ".tif",
        }
        if ct in mapping:
            return mapping[ct]

    return ".jpg"  # Fallback


def suffix_for_column(col: str, pt_counter: int) -> Tuple[str, int]:
    """
    Decide filename suffix based on column name, increment pt_counter for PTxx.
    Why: Enforces consistent naming without relying on exact header strings only.
    """
    c = col.strip().lower().replace("_", " ")
    c_words = set(c.split())

    if "swatch" in c:
        return "Swatch", pt_counter

    is_main_named = c in {"main image", "image main"} or ({"main", "image"} <= c_words)
    if is_main_named:
        return "Main", pt_counter

    suffix = f"PT{pt_counter:02d}"
    return suffix, pt_counter + 1


def download_bytes(url: str, timeout: float = 12.0) -> Tuple[Optional[bytes], Optional[str], Optional[int], Optional[str]]:
    """
    Returns (content, content_type, status_code, error_msg)
    Why: Centralizes HTTP behavior and uniform error handling.
    """
    headers = {
        "User-Agent": "ASIN-Image-Downloader/1.0 (+https://streamlit.io)",
        "Accept": "image/*, */*;q=0.8",
    }
    try:
        resp = requests.get(url, timeout=timeout, headers=headers)
        status = resp.status_code
        if 200 <= status < 300 and resp.content:
            return resp.content, resp.headers.get("Content-Type"), status, None
        return None, resp.headers.get("Content-Type"), status, f"HTTP {status}"
    except requests.Timeout:
        return None, None, None, "timeout"
    except requests.RequestException as e:
        return None, None, None, str(e)


def build_zip_for_batch(
    batch_df: pd.DataFrame,
    asin_col: str,
    image_columns: List[str],
    per_request_timeout: float = 12.0,
) -> Tuple[bytes, Dict[str, int], List[Dict[str, object]]]:
    """
    Build an in-memory ZIP for one batch of ASINs.
    Returns (zip_bytes, counters, events)
    - counters: {'files_written', 'asins', 'errors'}
    - events: detailed per-download diagnostics for summary table
    Why: Keeps memory-only, no filesystem dependency.
    """
    from zipfile import ZipFile, ZIP_DEFLATED

    buf = io.BytesIO()
    events: List[Dict[str, object]] = []
    files_written = 0
    errors = 0

    with ZipFile(buf, "w", ZIP_DEFLATED) as zipf:
        for _, row in batch_df.iterrows():
            asin = str(row[asin_col]).strip()
            pt_counter = 1

            for col in image_columns:
                raw_url = row.get(col, None)
                if not is_valid_url(raw_url):
                    continue

                url = str(raw_url).strip()
                suffix, pt_counter = suffix_for_column(col, pt_counter)

                content, content_type, status, err = download_bytes(url, timeout=per_request_timeout)
                if content:
                    ext = infer_ext(url, content_type)
                    # Keep filename simple; avoid nested dirs & unsafe chars.
                    filename = f"{asin}.{suffix}{ext}"
                    zipf.writestr(filename, content)
                    files_written += 1
                    events.append(
                        {
                            "ASIN": asin,
                            "Column": col,
                            "URL": url,
                            "Saved As": filename,
                            "Status": status,
                            "Error": None,
                        }
                    )
                else:
                    errors += 1
                    events.append(
                        {
                            "ASIN": asin,
                            "Column": col,
                            "URL": url,
                            "Saved As": None,
                            "Status": status,
                            "Error": err or "download_failed",
                        }
                    )

    buf.seek(0)
    counters = {"files_written": files_written, "asins": len(batch_df), "errors": errors}
    return buf.getvalue(), counters, events


# ------------------------------
# FILE UPLOAD
# ------------------------------
uploaded_file = st.file_uploader("Upload your file", type=["xlsx", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.lower().endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()

    st.write("### Preview")
    st.dataframe(df.head())

    asin_col = st.selectbox(
        "Select ASIN Column",
        options=list(df.columns),
        index=list(df.columns).index("ASIN") if "ASIN" in df.columns else 0,
    )

    # Deduplicate by ASIN
    df = df.groupby(asin_col, as_index=False).first()

    total_asins = len(df)
    st.write(f"### Total ASINs detected: **{total_asins}**")

    # Guess image columns
    default_cols = [c for c in df.columns if re.search(r"(image|swatch|img|main)", str(c), re.I)]
    image_columns = st.multiselect(
        "Choose image URL columns (order matters for PTxx)",
        options=list(df.columns),
        default=default_cols,
    )

    # Optional knobs
    col1, col2 = st.columns(2)
    with col1:
        batch_size = st.number_input("Batch size", min_value=1, max_value=200, value=40, step=1)
    with col2:
        timeout_each = st.slider("Per-image timeout (seconds)", min_value=4, max_value=30, value=12, step=1)

    if st.button("Generate ZIP Batches"):
        if not image_columns:
            st.error("Please select at least one image column.")
            st.stop()

        num_batches = math.ceil(total_asins / batch_size)
        st.info(f"Creating **{num_batches}** ZIP batch(es)...")

        progress = st.progress(0)
        batch_download_payloads: List[Tuple[str, bytes, Dict[str, int]]] = []
        all_events: List[Dict[str, object]] = []

        for batch_idx in range(num_batches):
            start = batch_idx * batch_size
            end = (batch_idx + 1) * batch_size
            batch_df = df.iloc[start:end]

            with st.spinner(f"Processing batch {batch_idx + 1} of {num_batches}..."):
                zip_bytes, counters, events = build_zip_for_batch(
                    batch_df=batch_df,
                    asin_col=asin_col,
                    image_columns=image_columns,
                    per_request_timeout=timeout_each,
                )
                all_events.extend(events)

                # Name per batch zip
                batch_label = f"asin_batch_{batch_idx + 1:02d}_of_{num_batches:02d}.zip"
                batch_download_payloads.append((batch_label, zip_bytes, counters))

            progress.progress(int(((batch_idx + 1) / num_batches) * 100))

        st.success("All batches processed!")

        st.write("## Download Your ZIP Batches")
        for i, (zip_name, zip_bytes, counters) in enumerate(batch_download_payloads, start=1):
            st.write(
                f"**Batch {i}:** {counters['asins']} ASINs, "
                f"{counters['files_written']} files, {counters['errors']} errors"
            )
            st.download_button(
                label="Download ZIP",
                data=zip_bytes,
                file_name=zip_name,
                mime="application/zip",
                key=f"dl_{i}_{uuid.uuid4()}",
            )

        # Diagnostics table
        if all_events:
            st.write("## Download Report")
            report_df = pd.DataFrame(all_events)
            # Show failures first for quick triage
            report_df = report_df.sort_values(by=["Error", "ASIN"], na_position="last").reset_index(drop=True)
            st.dataframe(report_df, use_container_width=True)
            # Optional CSV
            st.download_button(
                "Download Report CSV",
                data=report_df.to_csv(index=False),
                file_name="asin_image_download_report.csv",
                mime="text/csv",
            )

else:
    st.info("Upload a CSV/XLSX containing an ASIN column and image URL columns to begin.")
