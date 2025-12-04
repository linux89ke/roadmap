import streamlit as st
import pandas as pd
import re
import base64
from io import StringIO
from datetime import datetime
import numpy as np # Needed for NaN values

# --- CONFIGURATION ---
CATEGORIES_FILE = 'cats.xlsx'
DEFAULT_BRAND = 'Generic'
DEFAULT_COLOR = ''
DEFAULT_MATERIAL = '-'
DEFAULT_CATEGORY_NAME = 'Select a Category'

# --- STATIC TEMPLATE DATA ---
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
# ----------------------------


@st.cache_data
def load_category_data(file_path):
    """Loads and preprocesses the category data for fast lookup."""
    try:
        # 1. Load the data
        cat_df = pd.read_excel(file_path)
        
        # 2. Clean 'name' column for better searching/mapping
        cat_df['name'] = cat_df['name'].astype(str).str.strip()
        
        # 3. Create dictionaries for instant lookup (Category Name -> Path/Code)
        name_to_path = cat_df.set_index('name')['category'].to_dict()
        name_to_code = cat_df.set_index('name')['categories'].to_dict()
        
        # 4. Create a list of names for the searchable dropdown, including a default
        category_names = [DEFAULT_CATEGORY_NAME] + cat_df['name'].unique().tolist()
        
        return cat_df, name_to_path, name_to_code, category_names
    
    except FileNotFoundError:
        st.error(f"Category file '{file_path}' not found. Please place it in the script directory.")
        return pd.DataFrame(), {}, {}, [DEFAULT_CATEGORY_NAME]
    except Exception as e:
        st.error(f"Error loading category file: {e}")
        return pd.DataFrame(), {}, {}, [DEFAULT_CATEGORY_NAME]


def format_to_html_list(text):
    """
    Converts plain text bullet points (one per line) into an HTML unordered list.
    """
    if not text:
        return ''
    
    lines = [line.strip() for line in text.split('\n')]
    list_items = [f'    <li>{line}</li>' for line in lines if line]
    
    if not list_items:
        return ''
        
    list_content = '\n'.join(list_items)
    # Using four spaces for indentation to match your original formatting style
    return f'<ul>\n{list_content}\n    </ul>'


def generate_sku_config(name):
    """
    Generates sku_supplier_config and seller_sku using an automated heuristic.
    """
    if not name:
        return "GENERATEDSKU_MISSING"

    cleaned_name = re.sub(r'[^\w\s]', '', name).strip()
    words = cleaned_name.split()

    if not words:
        return "GENERATEDSKU_MISSING"

    # Skip first word if it looks like a quantity (number or ends with 'PCS', 'PACK')
    start_index = 0
    first_word = words[0].upper()
    if re.search(r'\d', first_word) or 'PCS' in first_word or 'PACK' in first_word:
        start_index = 1
    
    # Take the next three words from the start index
    sku_words = words[start_index:start_index + 3]
    
    if not sku_words:
        sku_words = words[0:1]  
    
    # Join words with underscores and uppercase
    sku = '_'.join(sku_words).upper()
    
    return sku


def create_output_df(product_list):
    """Converts a list of product dictionaries into a final DataFrame."""
    # NOTE: Added 'category_path' and 'category_code' columns
    columns = [
        'sku_supplier_config', 'seller_sku', 'name', 'brand', 'category_path', 
        'category_code', 'product_weight', 'package_type', 'package_quantities', 
        'variation', 'price', 'tax_class', 'cost', 'color', 'main_material', 
        'description', 'short_description', 'package_content', 'supplier', 
        'shipment_type'
    ]
    
    df = pd.DataFrame(product_list, columns=columns)
    # Replace NaN values with empty strings for export compatibility
    return df.fillna('', inplace=False)

def get_csv_download_link(df):
    """Generates a link to download the DataFrame as a CSV file with a descriptive filename."""
    
    # 1. Determine Filename based on the first product's name
    if df.empty:
        filename = "empty_product_export.csv"
    else:
        # Clean the first product's name for a safe filename
        raw_name = df.iloc[0]['name']
        cleaned_name = re.sub(r'[^a-zA-Z0-9\s]', '', raw_name).strip()
        filename_base = cleaned_name.replace(' ', '_').upper()[:30] # Truncate for safety

        if len(df) > 1:
            filename = f"{filename_base}_and_{len(df)-1}_more.csv"
        else:
            filename = f"{filename_base}.csv"
            
    # 2. Generate download link
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">**Download Generated CSV File: {filename}**</a>'
    return href

# --- Streamlit App Layout ---
st.set_page_config(layout="wide", page_title="Product Data Generator")
st.title("📦 Product Data Generator")

# --- Initialize Session State and Load Data ---
if 'products' not in st.session_state:
    st.session_state.products = []

# Load category data once and store lookups in session state
if 'category_data_loaded' not in st.session_state:
    cat_df, name_to_path, name_to_code, category_names = load_category_data(CATEGORIES_FILE)
    st.session_state.name_to_path = name_to_path
    st.session_state.name_to_code = name_to_code
    st.session_state.category_names = category_names
    st.session_state.category_data_loaded = True

with st.expander("ℹ️ Generation Logic", expanded=False):
    st.markdown("""
    | Field | Generation Logic | Default Value (If Optional Field is Empty) |
    | :--- | :--- | :--- |
    | **`sku_supplier_config` & `seller_sku`** | **Automated:** Skips leading quantity (e.g., '10PCS'), then takes the **next three words** and joins them with underscores. | N/A |
    | **`category_path` & `category_code`** | **Lookup:** Fetched automatically from `cats.xlsx` based on the selected **Category Name**. | N/A |
    | **`package_content`** | **Full Name** entered by the user. | N/A |
    | **`short_description`** | Line-by-line input converted to HTML list (`<ul><li>...</li></ul>`). | N/A |
    | **`brand`** | User Input (Optional) | **`Generic`** |
    """)

# --- Input Form ---
st.header("1. Enter New Product Details")
with st.form(key='product_form'):
    
    # Row 1: Name and Brand
    col_name, col_brand = st.columns([3, 1])
    with col_name:
        new_name = st.text_input("Product Name (Full Listing Title)", 
                                 placeholder="e.g., 10PCS Refrigerator Food Seal Pocket Fridge Bags - white")

    with col_brand:
        new_brand = st.text_input("Brand (Optional)", 
                                 value=DEFAULT_BRAND, 
                                 placeholder="e.g., Samsung")

    # Row 2: Category Selection (NEW)
    st.subheader("Category Selection")
    # Using st.selectbox allows typing to filter the list, making it searchable.
    selected_category_name = st.selectbox(
        "Select Category Name (Searchable)",
        options=st.session_state.category_names,
        index=0 # Default to 'Select a Category'
    )

    # Row 3: Optional Attributes
    st.subheader("Optional Attributes")
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

if submit_button:
    
    # Validation
    if not new_name or not new_description or not new_short_description_raw:
        st.error("Please fill in the Product Name, Full Description, and Short Description fields.")
        st.stop()
    
    if selected_category_name == DEFAULT_CATEGORY_NAME:
        st.error("Please select a Category Name from the searchable dropdown.")
        st.stop()
        
    # 1. Category Lookup (Fast and instant using dictionaries)
    category_path = st.session_state.name_to_path.get(selected_category_name, '')
    category_code = st.session_state.name_to_code.get(selected_category_name, '')
    
    # 2. Generate dynamic fields
    generated_sku = generate_sku_config(new_name)
    generated_package_content = new_name
    
    # 3. Format HTML list
    new_short_description_html = format_to_html_list(new_short_description_raw)
    
    # 4. Combine with static data and inputs
    new_product = {
        'name': new_name,
        'description': new_description,
        'short_description': new_short_description_html,
        
        # Generated Fields
        'sku_supplier_config': generated_sku,
        'seller_sku': generated_sku,
        'package_content': generated_package_content,
        
        # New Category Fields
        'category_path': category_path,
        'category_code': category_code,
        
        # Editable/Default Fields
        'brand': new_brand if new_brand else DEFAULT_BRAND,
        'color': new_color if new_color else DEFAULT_COLOR,
        'main_material': new_material if new_material else DEFAULT_MATERIAL,
        
        **TEMPLATE_DATA # Other static fields
    }
    
    st.session_state.products.append(new_product)
    st.success(f"Added product: **{new_name}** | Category: **{selected_category_name}** | Code: **{category_code}**")

# --- Results and Download ---
st.header("2. Generated Product List")

if st.session_state.products:
    st.info(f"Total products added: **{len(st.session_state.products)}**")
    
    final_df = create_output_df(st.session_state.products)
    
    st.subheader("Preview of Generated Data (Last 5 Products)")
    st.dataframe(final_df.tail(5), use_container_width=True)
    
    st.markdown(get_csv_download_link(final_df), unsafe_allow_html=True)
    
    st.markdown("---")
    if st.button("🗑️ Clear All Products"):
        st.session_state.products = []
        st.rerun()

else:
    st.warning("No products have been added yet. Fill out the form above and select a category to begin generating your CSV.")
