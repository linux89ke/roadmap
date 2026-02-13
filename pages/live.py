import streamlit as st
import pandas as pd
import io
import zipfile

st.title("SKU Category Splitter & Formatter")
st.write("Upload your SKU list to split it into category-specific Excel files with custom naming.")

# File uploader
uploaded_file = st.file_uploader("Upload SKU List (CSV or Excel)", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        # Load the file
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success("File uploaded successfully!")
        
        # Column selection
        cols = df.columns.tolist()
        sku_col = st.selectbox("Select the SKU column", options=cols, index=0)
        cat_col = st.selectbox("Select the Category column", options=cols, index=1 if len(cols) > 1 else 0)

        # Let user define a prefix for the filenames
        file_prefix = st.text_input("Enter filename prefix", value="MPL_Update")

        if st.button("Generate Excel Zip"):
            # Prepare the data
            processed_df = df[[sku_col, cat_col]].copy()
            processed_df.rename(columns={sku_col: 'sku'}, inplace=True)
            
            # Fill the required status columns
            processed_df['images_ready'] = 1
            processed_df['content_ready'] = 1
            processed_df['pet_approved'] = 1
            processed_df['status_simple'] = 'active'
            processed_df['status_config'] = 'active'

            output_cols = ['sku', 'images_ready', 'content_ready', 'pet_approved', 'status_simple', 'status_config']

            # Create an in-memory ZIP file
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                categories = processed_df[cat_col].unique()
                
                for cat in categories:
                    # Filter data for the specific category
                    cat_df = processed_df[processed_df[cat_col] == cat][output_cols]
                    
                    # Create an in-memory Excel file
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                        cat_df.to_excel(writer, index=False, sheet_name='Sheet1')
                    
                    # UPDATED NAMING LOGIC HERE
                    file_name = f"{file_prefix}_{cat}.xlsx"
                    
                    # Add Excel buffer to zip
                    zip_file.writestr(file_name, excel_buffer.getvalue())

            # Download button
            st.download_button(
                label="Download Named Excel Files (.zip)",
                data=zip_buffer.getvalue(),
                file_name="categorized_sku_updates.zip",
                mime="application/zip"
            )
            st.info(f"Processed {len(categories)} categories with custom naming.")

    except Exception as e:
        st.error(f"Error: {e}")
