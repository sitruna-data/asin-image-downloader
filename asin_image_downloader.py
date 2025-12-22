import streamlit as st

st.set_page_config(page_title="ASIN Image Downloader Debug", layout="centered")

st.title("ASIN Image Downloader – Debug Mode")

st.write("If an error occurs before the UI loads, it will be displayed below.")

try:
    import pandas as pd
    import requests
    import zipfile
    from io import BytesIO
    import openpyxl  # required for xlsx

    st.success("Imports loaded successfully!")

    # ------------------------------
    # FILE UPLOAD
    # ------------------------------
    uploaded_file = st.file_uploader("Upload your file", type=["xlsx", "csv"])

    if uploaded_file:

        st.write("File uploaded. Attempting to read...")

        try:
            if uploaded_file.name.endswith(".xlsx"):
                df = pd.read_excel(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)

            st.write("### Preview")
            st.dataframe(df.head())

        except Exception as e:
            st.error(f"Error reading file: {e}")
            st.stop()

        asin_col = st.selectbox(
            "Select ASIN Column",
            df.columns,
        )

        image_columns = st.multiselect(
            "Select Image Columns",
            df.columns,
            default=[c for c in df.columns if "Image" in c or "Swatch" in c]
        )

        if st.button("Generate ZIP"):
            try:
                zip_buffer = BytesIO()
                image_count = 0

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for _, row in df.iterrows():
                        asin = str(row[asin_col]).strip()
                        pt_counter = 1

                        for col in image_columns:
                            url = str(row[col]).strip()
                            if not url:
                                continue

                            col_lower = col.lower()

                            if col_lower == "main image":
                                suffix = "Main"
                            elif "swatch" in col_lower:
                                suffix = "Swatch"
                            else:
                                suffix = f"PT{pt_counter:02d}"
                                pt_counter += 1

                            filename = f"{asin}.{suffix}.jpg"

                            response = requests.get(url, timeout=10)
                            response.raise_for_status()
                            zipf.writestr(filename, response.content)
                            image_count += 1

                zip_buffer.seek(0)

                st.success(f"Done! {image_count} images processed.")

                st.download_button(
                    label="Download ZIP",
                    data=zip_buffer,
                    file_name="asin_images.zip",
                    mime="application/zip"
                )

            except Exception as e:
                st.error(f"ERROR WHILE GENERATING ZIP: {e}")

except Exception as e:
    st.error(f"FATAL ERROR DURING STARTUP: {e}")
