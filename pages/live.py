import streamlit as st
import pandas as pd
import io
import zipfile

# Mapping dictionary for categories
CATEGORY_MAPPING = {
    'AU': 'Automotive',
    'BM': 'Books & Magazines',
    'BN': 'Beddings & Linens',
    'CA': 'Car Accessories',
    'CL': 'Computers & Laptops',
    'CM': 'Cameras',
    'CP': 'Cleaning Products',
    'DR': 'Drinks',
    'DS': 'DVD, software and ebooks',
    'DV': 'Dietary Supplements & Vitamins',
    'EA': 'Electronics & Phone Accessories',
    'EC': 'Electronic Gaming',
    'EL': 'Electronics',
    'FA': 'Fashion',
    'FC': 'Fashion Accessories',
    'FD': 'Furniture & Decor',
    'FF': 'Fresh Food & Grocery',
    'FS': 'Footwear & Shoes',
    'HA': 'Home Appliances',
    'HB': 'Health & Beauty',
    'HL': 'Home & Living',
    'IP': 'Industrial, Scientific & Power Tools',
    'LB': 'Lights & Bulbs',
    'LS': 'Livestock',
    'LU': 'Luggages & Baggages',
    'MI': 'Musical Instruments',
    'MP': 'Mobile Phones & Tablets',
    'MW': 'Men & Women Clothes',
    'OP': 'Oils, Paints & Fluids',
    'OT': 'Other',
    'PB': 'Plumbing',
    'PF': 'Perfume',
    'SE': 'Sports & Fitness Equipment',
    'SH': 'Shoes',
    'SK': 'Sewing & Knitting',
    'SL': 'Swimsuits & Lingeries',
    'SN': 'Stationeries',
    'ST': 'Skincare & Toileteries',
    'TB': 'Toys & Board Games',
    'TG': 'Toys & Baby',
    'VP': 'Vehicle & Parts'
}

st.title("SKU Category Splitter & Formatter")
st.write("Upload your SKU list to split it into category-specific CSV files with full descriptive names.")

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

        if st.button("Generate CSV Zip"):
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
                    
                    # Convert to tab-separated string (matching original template)
                    csv_data = cat_df.to_csv(sep='\t', index=False)
                    
                    # Get full name from mapping
                    full_name = CATEGORY_MAPPING.get(str(cat).strip(), str(cat))
                    # Sanitize filename
                    file_name = f"{full_name.replace('/', '_').replace('\\', '_')}.csv"
                    
                    # Add CSV data to zip
                    zip_file.writestr(file_name, csv_data)

            # Download button
            st.download_button(
                label="Download Categories as CSV (.zip)",
                data=zip_buffer.getvalue(),
                file_name="categorized_sku_csv_updates.zip",
                mime="application/zip"
            )
            st.info(f"Processed {len(categories)} categories.")

    except Exception as e:
        st.error(f"Error: {e}")
