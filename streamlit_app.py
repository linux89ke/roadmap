import streamlit as st
import pandas as pd
import re
import base64
from io import StringIO

# --- STATIC TEMPLATE DATA ---
# These values are extracted from the single row of your uploaded file.
TEMPLATE_DATA = {
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
DEFAULT_BRAND = 'Generic' # Made editable, but defaults to 'Generic'
DEFAULT_COLOR = ''
DEFAULT_MATERIAL = '-'
# ----------------------------


def format_to_html_list(text):
    """
    Converts plain text bullet points (one per line) into an HTML unordered list.
    """
    if not text:
        return ''
    
    lines = [line.strip() for line in text.split('\n')]
    list_items = [f'      <li>{line}</li>' for line in lines if line]
    
    if not list_items:
        return ''
        
    list_content = '\n'.join(list_items)
    return f'<ul>\n{list_content}\n    </ul>'


def generate_sku_config(name):
    """
    Generates sku_supplier_config and seller_sku.
    Logic: Uses the first word of the name (as a proxy for the 'first noun').
    """
    cleaned_name = re.sub(r'[^\w\s-]', '', name).strip()
    words = cleaned_name.split()
    
    if words:
        # Take the first word, remove hyphens/spaces, and uppercase it
        sku = words[0].replace('-', '').upper()
    else:
        sku = "GENERATEDSKU"
            
    return sku

def create_output_df(product_list):
    """Converts a list of product dictionaries into a final DataFrame."""
    columns = [
        'sku_supplier_config', 'seller_sku', 'name', 'brand', 'product_weight', 
        'package_type', 'package_quantities', 'variation', 'price', 'tax_class', 
        'cost', 'color', 'main_material', 'description', 'short_description', 
        'package_content', 'supplier', 'shipment_type'
    ]
    
    df = pd.DataFrame(product_list, columns=columns)
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
    | **`sku_supplier_config` & `seller_sku`** | **Generated** from the **first word** of the Name. | N/A |
    | **`package_content`** | **Full Name** entered by the user. | N/A |
    | **`short_description`** | Line-by-line input converted to HTML list (`<ul><li>...</li></ul>`). | N/A |
    | **`brand`** | User Input (Optional) | **`Generic`** |
    | **`color`** | User Input (Optional) | **`''` (Empty String)** |
    | **`main_material`** | User Input (Optional) | **`-` (Hyphen)** |
    """)

# --- Input Form ---
st.header("1. Enter New Product Details")
with st.form(key='product_form'):
    # Row 1: Name and Brand
    col_name, col_brand = st.columns([3, 1])
    
    with col_name:
        new_name = st.text_input("Product Name (First word used for SKU)", 
                                 placeholder="e.g., Mini PCIe to PCI Express 16X Riser")

    with col_brand:
        # Brand is now editable but defaults to 'Generic'
        new_brand = st.text_input("Brand (Optional)", 
                                  value=DEFAULT_BRAND, 
                                  placeholder="e.g., Apple")

    # Row 2: Optional Attributes
    col_color, col_material = st.columns(2)
    
    with col_color:
        new_color = st.text_input("Color (Optional)", 
                                  value=DEFAULT_COLOR, 
                                  placeholder="e.g., Black")

    with col_material:
        new_material = st.text_input("Main Material (Optional)", 
                                     value=DEFAULT_MATERIAL, 
                                     placeholder="e.g., Plastic")
        
    st.markdown("---")
        
    st.subheader("Description Fields")
    new_description = st.text_area("Full Description", 
                                   placeholder="Paste the full, detailed product description here...")
    
    st.markdown("**Short Description (Highlights)**: Enter one bullet point per line.")
    new_short_description_raw = st.text_area("Short Description Input (Converts to HTML List in CSV)", 
                                             placeholder="Key feature 1\nKey feature 2\nKey feature 3",
                                             height=150)

    st.markdown("---")
    
    submit_button = st.form_submit_button(label='➕ Add Product to List')

if submit_button and new_name and new_description and new_short_description_raw:
    # 1. Generate dynamic fields
    generated_sku = generate_sku_config(new_name)
    generated_package_content = new_name 
    
    # 2. Format HTML list
    new_short_description_html = format_to_html_list(new_short_description_raw)
    
    # 3. Combine with static data and inputs
    new_product = {
        'name': new_name,
        'description': new_description,
        'short_description': new_short_description_html,
        'sku_supplier_config': generated_sku,
        'seller_sku': generated_sku,
        'package_content': generated_package_content,
        
        # Editable/Default Fields
        'brand': new_brand if new_brand else DEFAULT_BRAND,
        'color': new_color if new_color else DEFAULT_COLOR,
        'main_material': new_material if new_material else DEFAULT_MATERIAL,
        
        **TEMPLATE_DATA # Other static fields
    }
    
    st.session_state.products.append(new_product)
    st.success(f"Added product: **{new_name}** with SKU: **{generated_sku}**")

# --- Results and Download ---
st.header("2. Generated Product List")

if st.session_state.products:
    st.info(f"Total products added: **{len(st.session_state.products)}**")
    
    final_df = create_output_df(st.session_state.products)
    
    st.subheader("Preview of Generated Data")
    st.dataframe(final_df.tail(5), use_container_width=True)
    
    st.markdown(get_csv_download_link(final_df), unsafe_allow_html=True)
    
    st.markdown("---")
    if st.button("🗑️ Clear All Products"):
        st.session_state.products = []
        st.rerun()

else:
    st.warning("No products have been added yet. Fill out the form above to begin generating your CSV.")
