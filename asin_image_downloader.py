import streamlit as st
import pandas as pd
import requests
import zipfile
import openpyxl
from io import BytesIO

st.set_page_config(page_title="ASIN Image Downloader", layout="centered")

st.title("ASIN Image Downloader")
st.write("Upload your file with ASINs and multiple image columns. The app will download, rename, and zip everything for you.")

# ------------------------------
# FILE UPLOAD
# ------------------------------
uploaded_file = st.file_uploader("Upload your file", type=["xlsx", "csv"])

if uploaded_file:

    # Load file
    if uploaded_file.name.endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        df = pd.read_csv(uploaded_file)

    st.write("### Preview")
    st.dataframe(df.head())

    # Select ASIN column
    asin_col = st.selectbox(
        "Select ASIN Column",
        df.columns,
        index=list(df.columns).index("ASIN") if "ASIN" in df.columns else 0
    )

    # Select image columns
    st.write("### Select Image Columns (in order)")
    image_columns = st.multiselect(
        "Choose columns with image URLs",
        df.columns,
        default=[c for c in df.columns if "Image" in c or "Swatch" in c]
    )

    # ------------------------------
    # GENERATE ZIP BUTTON
    # ------------------------------
    if st.button("Generate ZIP"):

        if not image_columns:
            st.error("Please select at least one image column.")

        else:
            with st.spinner("Downloading images…"):

                zip_buffer = BytesIO()
                image_count = 0

                # Create in-memory ZIP
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

                    for _, row in df.iterrows():
                        asin = str(row[asin_col]).strip()
                        pt_counter = 1  # PT01 starts after Main

                        for col in image_columns:
                            url = str(row[col]).strip()

                            if not url or url.lower() == "nan":
                                continue

                            col_lower = col.lower()

                            # Decide suffix
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
                                st.warning(f"Failed to download {url} — {e}")

                zip_buffer.seek(0)

            st.success(f"Done! {image_count} images downloaded and zipped.")

            st.download_button(
                label="Download ZIP",
                data=zip_buffer,
                file_name="asin_images.zip",
                mime="application/zip"
            )
