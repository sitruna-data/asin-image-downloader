import streamlit as st
import pandas as pd
import requests
import zipfile
from io import BytesIO
import tempfile
import os

# ------------------------------
# Streamlit Setup
# ------------------------------
st.set_page_config(page_title="ASIN Image Downloader", layout="centered")

st.title("ASIN Image Downloader")
st.write("""
Upload your file with ASINs and multiple image columns.  
The app will download, rename, zip and deliver your images safely —  
even for very large files.
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
# File Upload
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

    # Show preview
    st.write("### Preview")
    st.dataframe(df.head())

    # Select ASIN column
    asin_col = st.selectbox(
        "Select ASIN Column",
        df.columns,
        index=list(df.columns).index("ASIN") if "ASIN" in df.columns else 0
    )

    # Deduplicate rows to avoid massive downloads
    df = df.groupby(asin_col).first().reset_index()

    # Image columns
    st.write("### Select Image Columns (in the correct order)")
    default_cols = [c for c in df.columns if "image" in c.lower() or "swatch" in c.lower()]

    image_columns = st.multiselect(
        "Choose columns with image URLs",
        df.columns,
        default=default_cols
    )

    # Generate ZIP
    if st.button("Generate ZIP"):

        if not image_columns:
            st.error("Please select at least one image column.")
            st.stop()

        with st.spinner("Downloading images and creating ZIP…"):

            # Create temporary ZIP on disk
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            temp_zip_path = temp_zip.name
            temp_zip.close()

            image_count = 0

            with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:

                for _, row in df.iterrows():

                    asin = str(row[asin_col]).strip()
                    pt_counter = 1

                    for col in image_columns:

                        raw_url = row[col]

                        if not is_valid_url(raw_url):
                            continue

                        url = str(raw_url).strip()
                        col_lower = col.lower()

                        # Determine filename suffix
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
                            image_count += 1

                        except Exception as e:
                            st.warning(f"Skipping {url} — {e}")

        st.success(f"Done! {image_count} images downloaded and zipped.")
        st.write("Your ZIP file is being uploaded…")

        # ------------------------------
        # UPLOAD ZIP TO FILE.IO
        # ------------------------------
        try:
            with open(temp_zip_path, "rb") as f:
                upload_response = requests.post(
                    "https://file.io",
                    files={"file": ("asin_images.zip", f)}
                ).json()

            if upload_response.get("success"):
                download_url = upload_response["link"]
                st.success("Your ZIP file is ready!")
                st.markdown(f"### 👉 [Click here to download your ZIP file]({download_url})")
            else:
                st.error("Failed to upload file for download. Please try again.")

        except Exception as e:
            st.error(f"Upload failed: {e}")

        # Clean up temporary ZIP
        try:
            os.remove(temp_zip_path)
        except:
            pass
