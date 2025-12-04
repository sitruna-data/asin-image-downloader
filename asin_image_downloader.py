import streamlit as st
import pandas as pd
import requests
import zipfile
import tempfile
import os

st.set_page_config(page_title="ASIN Image Downloader", layout="centered")

st.title("ASIN Image Downloader")
st.write("Upload your file with ASINs and multiple image columns. The app will download, rename, and zip everything for you.")

# FILE UPLOAD
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

    # Image columns (multi-select)
    st.write("### Select Image Columns (in order)")
    image_columns = st.multiselect(
        "Choose columns with image URLs",
        df.columns,
        default=[c for c in df.columns if "Image" in c or "Swatch" in c]
    )

    # Button
    if st.button("Generate ZIP"):
        if not image_columns:
            st.error("Please select at least one image column.")
        else:
            with st.spinner("Downloading images…"):
                temp_dir = tempfile.mkdtemp()
                zip_path = os.path.join(temp_dir, "asin_images.zip")
                image_count = 0

                with zipfile.ZipFile(zip_path, "w") as zipf:
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

                                file_path = os.path.join(temp_dir, filename)

                                with open(file_path, "wb") as f:
                                    f.write(response.content)

                                zipf.write(file_path, filename)
                                image_count += 1

                            except Exception as e:
                                st.warning(f"Failed to download {url} — {e}")

            st.success(f"Done! {image_count} images downloaded and zipped.")

            with open(zip_path, "rb") as f:
                st.download_button(
                    label="Download ZIP",
                    data=f,
                    file_name="asin_images.zip",
                    mime="application/zip"
                )
