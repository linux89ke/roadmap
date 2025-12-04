import streamlit as st
import pandas as pd
import re
import base64
from io import StringIO

# --- STATIC TEMPLATE DATA ---
# These values are extracted from the single row of your uploaded file
# 'products_20251117073717_101843 wheel.csv' and are used as defaults.
TEMPLATE_DATA = {
    'brand': 'Generic',
    'product_weight': 1,
    'package_type': '', 
    'package_quantities': '', 
    'variation': '?',
    'price': 100000,
    'tax_class': 'Default',
    'cost': '', 
    'supplier': 'MarketPlace forfeited items',
    'shipment_type': 'Own Warehouse',
}
# Default values for fields that are now optional inputs
DEFAULT_COLOR = '' # Was NaN in original file
DEFAULT_MATERIAL = '-' # Was '-' in original file
# ----------------------------


def generate_sku_config(name):
    """
    Generates sku_supplier_config and seller_sku.
    Logic: Takes the first two words of the name, cleans them (removes non-alphanumeric/hyphens), and converts to uppercase.
    """
    cleaned_name = re.sub(r'[^\w\s-]', '', name).strip()
    words = cleaned_name.split()
    
    if len(words) >= 2:
        sku = (words[0] + words[1]).replace('-', '').upper()
    elif len(words) == 1:
        sku = words[0].upper()
    else:
        sku = "GENERATEDSKU"
        
    return sku

def generate_package_content(name):
    """
    Generates package_content.
    Logic: Takes the first word of the name, cleans it, and capitalizes it.
    """
    cleaned_name = re.sub(r'[^\w\s-]', '', name).strip()
    words = cleaned_name.split()
    
    if words:
        return words[0].capitalize()
    return "Item"

def create_output_df(product_list):
    """Converts a list of product dictionaries into a final DataFrame."""
    # Define the final order of columns as seen in the original CSV
    columns = [
        'sku_supplier_config', 'seller_sku', 'name', 'brand', 'product_weight', 
        'package_type', 'package_quantities', 'variation', 'price', 'tax_class', 
        'cost', 'color', 'main_material', 'description', 'short_description', 
        'package_content', 'supplier', 'shipment_type'
    ]
    
    df = pd.DataFrame(product_list, columns=columns)
    # Ensure all NaN/None values are treated as empty strings for CSV generation
    return df.fillna('', inplace=False)

def get_csv_download_link(df):
    """Generates a link to download the DataFrame as a CSV file."""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="generated_products.csv">**Download Generated CSV File**</a>'
    return href

# --- Streamlit App Layout ---
st.set_page_config(layout="wide", page_title="Product Data Generator")
st.title("📦 Product Data Generator")

if 'products' not in st.session_state:
    st.session_state.products = []

with st.expander("ℹ️ Generation Logic", expanded=False):
    st.markdown("""
    | Field | Generation Logic | Default Value (If Optional Field is Empty) |
    | :--- | :--- | :--- |
    | **`sku_supplier_config` & `seller_sku`** | Generated from the first two words of the Name. | N/A |
    | **`package_content`** | Generated from the first word of the Name. | N/A |
    | **`color`** | User Input (Optional) | **`''` (Empty String)** |
    | **`main_material`** | User Input (Optional) | **`-` (Hyphen)** |
    | **All other fields** | Static Template values. | N/A |
    """)

# --- Input Form ---
st.header("1. Enter New Product Details")
with st.form(key='product_form'):
    # Row 1: Name and Optional Fields
    col_name, col_color, col_material = st.columns([2, 1, 1])
    
    with col_name:
        new_name = st.text_input("Product Name (This drives SKU generation)", 
                                 placeholder="e.g., Mini PCIe to PCI Express 16X Riser")

    with col_color:
        # Optional: Uses the default value if left blank
        new_color = st.text_input("Color (Optional)", 
                                  value=DEFAULT_COLOR, 
                                  placeholder="e.g., Black")

    with col_material:
        # Optional: Uses the default value if left blank
        new_material = st.text_input("Main Material (Optional)", 
                                     value=DEFAULT_MATERIAL, 
                                     placeholder="e.g., Plastic")
        
    st.markdown("---")
        
    st.subheader("Description Fields")
    new_description = st.text_area("Full Description", 
                                   placeholder="Paste the full, detailed product description here...")
    new_short_description = st.text_area("Short Description (Highlights)", 
                                         placeholder="Paste the bullet points or key features here...")

    st.markdown("---")
    
    submit_button = st.form_submit_button(label='➕ Add Product to List')

if submit_button and new_name and new_description and new_short_description:
    # 1. Generate dynamic fields
    generated_sku = generate_sku_config(new_name)
    generated_package_content = generate_package_content(new_name)
    
    # 2. Combine with static data and inputs
    new_product = {
        'name': new_name,
        'description': new_description,
        'short_description': new_short_description,
        'sku_supplier_config': generated_sku,
        'seller_sku': generated_sku,
        'package_content': generated_package_content,
        'color': new_color if new_color else DEFAULT_COLOR,  # Use input or default
        'main_material': new_material if new_material else DEFAULT_MATERIAL, # Use input or default
        **TEMPLATE_DATA # Unpacks all other static fields
    }
    
    # 3. Add to session state list
    st.session_state.products.append(new_product)
    st.success(f"Added product: **{new_name}** with SKU: **{generated_sku}**")

# --- Results and Download ---
st.header("2. Generated Product List")

if st.session_state.products:
    st.info(f"Total products added: **{len(st.session_state.products)}**")
    
    # Create the final DataFrame
    final_df = create_output_df(st.session_state.products)
    
    # Display the last few rows for review
    st.subheader("Preview of Generated Data")
    st.dataframe(final_df.tail(5), use_container_width=True)
    
    # Download link
    st.markdown(get_csv_download_link(final_df), unsafe_allow_html=True)
    
    st.markdown("---")
    if st.button("🗑️ Clear All Products"):
        st.session_state.products = []
        st.rerun()

else:
    st.warning("No products have been added yet. Fill out the form above to begin generating your CSV.")
