import streamlit as st
import requests
import zipfile
from io import BytesIO



st.set_page_config(page_title="ASIN Image Downloader", layout="centered")

st.title("ASIN Image Downloader")
st.write("""
Upload your file with ASINs and multiple image columns.  
The app will download, rename, and zip everything for you.
""")

# ------------------------------
# Helper: Safe URL validator
# ------------------------------
def is_valid_url(url):
    """Returns True only for real, usable URLs."""
    if url is None:
        return False

    url = str(url).strip()

    if url.lower() in ["", "nan", "none", "null", "na"]:
        return False

    if not url.startswith("http"):
        return False

    return True


# ------------------------------
# FILE UPLOAD
# ------------------------------
uploaded_file = st.file_uploader("Upload your file", type=["xlsx", "csv"])

if uploaded_file:

    # Load file safely
    try:
        if uploaded_file.name.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file, engine="openpyxl")
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

    # Select image columns
    st.write("### Select Image Columns (in the correct order)")
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
            st.stop()

        with st.spinner("Downloading images…"):

            zip_buffer = BytesIO()
            image_count = 0

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

                for _, row in df.iterrows():

                    asin = str(row[asin_col]).strip()
                    pt_counter = 1  # PT01 starts after Main image

                    for col in image_columns:
                        raw_url = row[col]

                        if not is_valid_url(raw_url):
                            continue

                        url = str(raw_url).strip()
                        col_lower = col.lower()

                        # Assign proper suffix
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

            zip_buffer.seek(0)

        st.success(f"Done! {image_count} images downloaded and zipped.")

        st.download_button(
            label="📦 Download ZIP",
            data=zip_buffer,
            file_name="asin_images.zip",
            mime="application/zip"
        )
