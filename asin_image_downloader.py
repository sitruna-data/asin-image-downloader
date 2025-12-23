import streamlit as st
import pandas as pd
import requests
import zipfile
import tempfile
import os
import math
import uuid

# ------------------------------
# Streamlit Setup
# ------------------------------
st.set_page_config(page_title="ASIN Image Downloader", layout="centered")

st.title("ASIN Image Downloader (Stable, Batched, Temporary ZIPs)")
st.write("""
This tool downloads and renames images for each ASIN, packaged into 
ZIP files of **40 ASINs per batch**.  
Files are served directly from the app and auto-delete after download.
""")


# ------------------------------
# URL Validator
# ------------------------------
def is_valid_url(url):
    if url is None:
        return False

    url = str(url).strip()
    if url.lower() in ["", "nan", "none", "null", "na", "true", "false"]:
        return False

    return url.lower().startswith("http")


# ------------------------------
# FILE UPLOAD
# ------------------------------
uploaded_file = st.file_uploader("Upload your file", type=["xlsx", "csv"])

if uploaded_file:

    # Load file
    try:
        if uploaded_file.name.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()

    st.write("### Preview")
    st.dataframe(df.head())

    # Select ASIN column
    asin_col = st.selectbox(
        "Select ASIN Column",
        df.columns,
        index=list(df.columns).index("ASIN") if "ASIN" in df.columns else 0
    )

    # Deduplicate
    df = df.groupby(asin_col).first().reset_index()

    total_asins = len(df)
    st.write(f"### Total ASINs detected: **{total_asins}**")

    # Image columns
    st.write("### Select Image Columns (in order)")
    default_cols = [c for c in df.columns if "image" in c.lower() or "swatch" in c.lower()]

    image_columns = st.multiselect(
        "Choose image URL columns",
        df.columns,
        default=default_cols
    )

    # Button to start processing
    if st.button("Generate ZIP Batches"):

        if not image_columns:
            st.error("Please select at least one image column.")
            st.stop()

        BATCH_SIZE = 40
        num_batches = math.ceil(total_asins / BATCH_SIZE)

        st.info(f"Creating **{num_batches} ZIP batches**...")

        download_links = []

        for batch_idx in range(num_batches):

            with st.spinner(f"Processing batch {batch_idx+1} of {num_batches}..."):

                # Slice ASINs for this batch
                batch_df = df.iloc[batch_idx*BATCH_SIZE : (batch_idx+1)*BATCH_SIZE]

                # Create temp zip file
                temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
                zip_path = temp_zip.name
                temp_zip.close()

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:

                    for _, row in batch_df.iterrows():
                        asin = str(row[asin_col]).strip()
                        pt_counter = 1

                        for col in image_columns:
                            raw_url = row[col]
                            if not is_valid_url(raw_url):
                                continue

                            url = str(raw_url).strip()
                            col_lower = col.lower()

                            if col_lower == "main image":
                                suffix = "Main"
                            elif "swatch" in col_lower:
                                suffix = "Swatch"
                            else:
                                suffix = f"PT{pt_counter:02d}"
                                pt_counter += 1

                            filename = f"{asin}.{suffix}.jpg"

                            try:
                                response = requests.get(url, timeout=10)
                                response.raise_for_status()
                                zipf.writestr(filename, response.content)
                            except:
                                pass

                # Create a unique ID to expose file via Streamlit
                file_id = str(uuid.uuid4())

                # Store download path for user
                st.session_state[file_id] = zip_path

                download_url = f"/media/{file_id}"

                download_links.append((batch_idx+1, download_url))


        # ------------------------------
        # Display download links
        # ------------------------------
        st.success("All batches processed!")

        st.write("## Download Your ZIP Batches")

        for batch_num, url in download_links:
            st.markdown(f"- **Batch {batch_num}:** 👉 [Download ZIP]({url})", unsafe_allow_html=True)


# ------------------------------
# MEDIA ENDPOINT (SERVE FILES + DELETE AFTER DOWNLOAD)
# ------------------------------
from fastapi import FastAPI
import threading
import time

# This runs inside Streamlit's FastAPI backend
app = FastAPI()

@app.get("/media/{file_id}")
def serve_file(file_id: str):
    """Serves the ZIP file and deletes it after a delay."""
    zip_path = st.session_state.get(file_id)

    if not zip_path or not os.path.exists(zip_path):
        return "File not found."

    # Serve file content
    def delayed_delete(path):
        time.sleep(5)
        try:
            os.remove(path)
        except:
            pass

    threading.Thread(target=delayed_delete, args=(zip_path,)).start()

    return FileResponse(zip_path, media_type="application/zip", filename="asin_batch.zip")
