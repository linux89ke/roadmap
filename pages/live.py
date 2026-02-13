import streamlit as st
import pandas as pd
import io
import zipfile

st.title("SKU Category Splitter & Formatter")
st.write("Upload your SKU list to split it into category-specific files with pre-filled status columns.")

# File uploader
uploaded_file = st.file_uploader("Upload SKU List (CSV or Excel)", type=["csv", "xlsx"])

if uploaded_file is not None:
    # Load the file
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success("File uploaded successfully!")
        st.write("Preview of uploaded data:")
        st.dataframe(df.head())

        # Column selection
        cols = df.columns.tolist()
        sku_col = st.selectbox("Select the SKU column", options=cols, index=0)
        cat_col = st.selectbox("Select the Category column", options=cols, index=1 if len(cols) > 1 else 0)

        if st.button("Process and Generate Zip"):
            # Prepare the data
            processed_df = df[[sku_col, cat_col]].copy()
            processed_df.rename(columns={sku_col: 'sku'}, inplace=True)
            
            # Add fixed columns
            processed_df['images_ready'] = 1
            processed_df['content_ready'] = 1
            processed_df['pet_approved'] = 1
            processed_df['status_simple'] = 'active'
            processed_df['status_config'] = 'active'

            # Create an in-memory ZIP file
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                categories = processed_df[cat_col].unique()
                
                for cat in categories:
                    # Filter data for the category
                    cat_df = processed_df[processed_df[cat_col] == cat].drop(columns=[cat_col])
                    
                    # Convert to tab-separated string
                    tsv_data = cat_df.to_csv(sep='\t', index=False)
                    
                    # Add to zip
                    file_name = f"category_{cat}.csv"
                    zip_file.writestr(file_name, tsv_data)

            # Download button
            st.download_button(
                label="Download All Categories (.zip)",
                data=zip_buffer.getvalue(),
                file_name="processed_categories.zip",
                mime="application/zip"
            )
            st.info(f"Processed {len(categories)} categories.")

    except Exception as e:
        st.error(f"Error processing file: {e}")
