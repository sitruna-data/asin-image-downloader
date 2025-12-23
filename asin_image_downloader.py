import streamlit as st
import pandas as pd
import requests
import zipfile
from io import BytesIO
import tempfile
import os
import math

# ------------------------------
# Streamlit Setup
# ------------------------------
st.set_page_config(page_title="ASIN Image Downloader", layout="centered")

st.title("ASIN Image Downloader (Batched & Cloud-Stable)")
st.write("""
This tool downloads and renames images for each ASIN, then packages them into 
ZIP files of **40 ASINs per batch** to avoid Streamlit Cloud timeouts.
Each ZIP is uploaded safely to **transfer.sh** for reliable downloading.
""")


# ------------------------------
# URL Validator
# ------------------------------
def is_valid_url(url):
    """Return True only for real usable URLs."""
    if url is None:
        return False

    url = str(url).strip()
    if url.lower() in ["", "nan", "none", "null", "na", "true", "false"]:
        return False

    if not url.lower().startswith("http"):
        return False

    return True


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

    # Deduplicate to one row per ASIN
    df = df.groupby(asin_col).first().reset_index()

    total_asins = len(df)
    st.write(f"### Total ASINs detected: **{total_asins}**")

    # Image columns
    st.write("### Select Image Columns (in order)")
    default_cols = [c for c in df.columns if "image" in c.lower() or "swatch" in c.lower()]

    image_columns = st.multiselect(
        "Choose columns containing image URLs",
        df.columns,
        default=default_cols
    )

    # Button
    if st.button("Generate ZIP Batches"):

        if not image_columns:
            st.error("Please select at least one image column.")
            st.stop()

        BATCH_SIZE = 40
        num_batches = math.ceil(total_asins / BATCH_SIZE)

        st.info(f"Creating **{num_batches} batches** of up to {BATCH_SIZE} ASINs each...")

        batch_download_links = []

        # Process batches
        for batch_idx in range(num_batches):
            with st.spinner(f"Processing batch {batch_idx+1} of {num_batches}..."):

                # Slice the batch
                batch_df = df.iloc[batch_idx*BATCH_SIZE : (batch_idx+1)*BATCH_SIZE]

                # Create a temp ZIP
                temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
                temp_zip_path = temp_zip.name
                temp_zip.close()

                with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:

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

                # ------------------------------
                # UPLOAD ZIP TO TRANSFER.SH
                # ------------------------------
                try:
                    with open(temp_zip_path, "rb") as f:
                        upload_response = requests.put(
                            f"https://transfer.sh/asin_batch_{batch_idx+1}.zip",
                            data=f
                        )

                    if upload_response.status_code == 200:
                        download_url = upload_response.text.strip()
                        batch_download_links.append((batch_idx+1, download_url))
                    else:
                        batch_download_links.append(
                            (batch_idx+1, f"UPLOAD FAILED: HTTP {upload_response.status_code}")
                        )

                except Exception as e:
                    batch_download_links.append((batch_idx+1, f"UPLOAD ERROR: {e}"))

                # Clean up
                try:
                    os.remove(temp_zip_path)
                except:
                    pass

        st.success("All batches processed!")

        st.write("## Download Your ZIP Batches")

        for batch_num, url in batch_download_links:
            if url.startswith("http"):
                st.markdown(f"- **Batch {batch_num}:** [Download ZIP]({url})")
            else:
                st.markdown(f"- **Batch {batch_num}:** ❌ {url}")
