import math
import os
import re
from typing import Dict, List, Optional, Tuple
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
import requests
import streamlit as st

# ------------------------------
# Streamlit Setup
# ------------------------------
st.set_page_config(page_title="ASIN Image Downloader", layout="centered")
st.title("Sitruna ASIN Image Downloader")

# ------------------------------
# Output directory (disk-based)
# ------------------------------
OUTPUT_DIR = "zip_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ------------------------------
# Session State
# ------------------------------
if "batches" not in st.session_state:
    st.session_state.batches = None

if "report_df" not in st.session_state:
    st.session_state.report_df = None

st.write(
    """
This tool downloads and renames images for each ASIN, packaged into ZIP files of **40 ASINs per batch**.
ZIPs are written to disk to ensure **stable downloads without crashing**.
"""
)

# ------------------------------
# Helpers
# ------------------------------
def is_valid_url(url: object) -> bool:
    if url is None:
        return False
    s = str(url).strip().lower()
    if s in {"", "nan", "none", "null", "na", "true", "false"}:
        return False
    return s.startswith("http://") or s.startswith("https://")


def infer_ext(url: str, content_type: Optional[str]) -> str:
    path = re.sub(r"[?#].*$", "", url)
    m = re.search(r"\.(jpe?g|png|gif|webp|bmp|tiff?)$", path, re.I)
    if m:
        return "." + m.group(1).lower()

    if content_type:
        mapping = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
            "image/tiff": ".tif",
        }
        ct = content_type.split(";")[0].lower()
        return mapping.get(ct, ".jpg")

    return ".jpg"


def suffix_for_column(col: str, pt_counter: int) -> Tuple[str, int]:
    c = col.strip().lower().replace("_", " ")
    c_words = set(c.split())

    if "swatch" in c:
        return "Swatch", pt_counter

    if c in {"main image", "image main"} or ({"main", "image"} <= c_words):
        return "Main", pt_counter

    return f"PT{pt_counter:02d}", pt_counter + 1


def download_bytes(url: str, timeout: float) -> Tuple[Optional[bytes], Optional[str], Optional[int], Optional[str]]:
    headers = {
        "User-Agent": "ASIN-Image-Downloader/1.0",
        "Accept": "image/*,*/*;q=0.8",
    }
    try:
        r = requests.get(url, timeout=timeout, headers=headers)
        if 200 <= r.status_code < 300 and r.content:
            return r.content, r.headers.get("Content-Type"), r.status_code, None
        return None, r.headers.get("Content-Type"), r.status_code, f"HTTP {r.status_code}"
    except requests.Timeout:
        return None, None, None, "timeout"
    except requests.RequestException as e:
        return None, None, None, str(e)


def build_zip_for_batch(
    batch_df: pd.DataFrame,
    asin_col: str,
    image_columns: List[str],
    zip_path: str,
    per_request_timeout: float,
) -> Tuple[Dict[str, int], List[Dict[str, object]]]:

    events: List[Dict[str, object]] = []
    files_written = 0
    errors = 0

    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zipf:
        for _, row in batch_df.iterrows():
            asin = str(row[asin_col]).strip()
            pt_counter = 1

            for col in image_columns:
                raw_url = row.get(col)
                if not is_valid_url(raw_url):
                    continue

                suffix, pt_counter = suffix_for_column(col, pt_counter)
                content, content_type, status, err = download_bytes(str(raw_url), per_request_timeout)

                if content:
                    ext = infer_ext(str(raw_url), content_type)
                    filename = f"{asin}.{suffix}{ext}"
                    zipf.writestr(filename, content)
                    files_written += 1
                    events.append(
                        {"ASIN": asin, "Column": col, "Saved As": filename, "Status": status, "Error": None}
                    )
                else:
                    errors += 1
                    events.append(
                        {"ASIN": asin, "Column": col, "Saved As": None, "Status": status, "Error": err}
                    )

    counters = {"files_written": files_written, "asins": len(batch_df), "errors": errors}
    return counters, events


# ------------------------------
# FILE UPLOAD
# ------------------------------
uploaded_file = st.file_uploader("Upload your file", type=["xlsx", "csv"])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith(".xlsx") else pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()

    st.dataframe(df.head())

    asin_col = st.selectbox("Select ASIN Column", df.columns)
    df = df.groupby(asin_col, as_index=False).first()

    image_columns = st.multiselect(
        "Choose image URL columns",
        options=df.columns,
        default=[c for c in df.columns if re.search(r"(image|img|swatch|main)", c, re.I)],
    )

    batch_size = st.number_input("Batch size", 1, 200, 40)
    timeout_each = st.slider("Per-image timeout (seconds)", 4, 30, 12)

    if st.button("Generate ZIP Batches") and st.session_state.batches is None:
        num_batches = math.ceil(len(df) / batch_size)
        all_events = []
        batches = []

        for i in range(num_batches):
            batch_df = df.iloc[i * batch_size : (i + 1) * batch_size]
            zip_name = f"asin_batch_{i+1:02d}_of_{num_batches:02d}.zip"
            zip_path = os.path.join(OUTPUT_DIR, zip_name)

            with st.spinner(f"Processing batch {i+1}/{num_batches}"):
                counters, events = build_zip_for_batch(
                    batch_df, asin_col, image_columns, zip_path, timeout_each
                )
                all_events.extend(events)
                batches.append((zip_name, zip_path, counters))

        st.session_state.batches = batches
        st.session_state.report_df = pd.DataFrame(all_events)
        st.success("All batches processed!")

# ------------------------------
# DOWNLOADS
# ------------------------------
if st.session_state.batches:
    st.write("## Download ZIP Batches")

    for i, (zip_name, zip_path, counters) in enumerate(st.session_state.batches, start=1):
        st.write(
            f"**Batch {i}:** {counters['asins']} ASINs, "
            f"{counters['files_written']} files, {counters['errors']} errors"
        )
        with open(zip_path, "rb") as f:
            st.download_button(
                "Download ZIP",
                data=f,
                file_name=zip_name,
                mime="application/zip",
                key=f"dl_{i}",
            )

    st.write("## Download Report")
    st.dataframe(st.session_state.report_df, use_container_width=True)

    st.download_button(
        "Download Report CSV",
        data=st.session_state.report_df.to_csv(index=False),
        file_name="asin_image_download_report.csv",
        mime="text/csv",
    )

    if st.button("Reset app"):
        st.session_state.clear()
        st.experimental_rerun()
