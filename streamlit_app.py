import streamlit as st
import pandas as pd
import re
import base64
import os

# --- CONFIGURATION ---
FILE_NAME_CSV = 'cats.csv' 
DEFAULT_BRAND = 'Generic'
DEFAULT_COLOR = ''
DEFAULT_MATERIAL = '-'
DEFAULT_CATEGORY_PATH = 'Select a Category'

# --- TEMPLATE DATA ---
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

@st.cache_data
def load_category_data():
    """
    Loads category data and extracts 'Root Categories' for easier filtering.
    """
    df = pd.DataFrame()
    
    if os.path.exists(FILE_NAME_CSV):
        try:
            # Read strictly as text
            df = pd.read_csv(FILE_NAME_CSV, dtype=str)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return pd.DataFrame(), {}, [], []
    else:
        st.error(f"CRITICAL ERROR: '{FILE_NAME_CSV}' not found.")
        return pd.DataFrame(), {}, [], []

    if not df.empty:
        # 1. Clean Data
        df['name'] = df['name'].str.strip()
        if 'category' in df.columns:
            df['category'] = df['category'].str.strip()
        else:
            return pd.DataFrame(), {}, [], []

        if 'categories' in df.columns:
            df['categories'] = df['categories'].str.strip()

        # 2. Extract Root Category (e.g. "Computing" from "Computing\Accessories")
        # We split by the backslash '\' and take the first part
        def get_root(path):
            if pd.isna(path): return "Other"
            parts = str(path).split('\\')
            return parts[0] if parts else "Other"

        df['root_category'] = df['category'].apply(get_root)

        # 3. Create Lookup: Full Path -> Code
        path_to_code = df.set_index('category')['categories'].to_dict()
        
        # 4. Get List of Unique Roots for the Filter
        root_list = sorted(df['root_category'].unique().tolist())
        
        return df, path_to_code, root_list
    
    return pd.DataFrame(), {}, [], []


def format_to_html_list(text):
    if not text: return ''
    lines = [line.strip() for line in text.split('\n')]
    list_items = [f'    <li>{line}</li>' for line in lines if line]
    if not list_items: return ''
    list_content = '\n'.join(list_items)
    return f'<ul>\n{list_content}\n    </ul>'


def generate_sku_config(name):
    if not name: return "GENERATEDSKU_MISSING"
    cleaned_name = re.sub(r'[^\w\s]', '', name).strip()
    words = cleaned_name.split()
    if not words: return "GENERATEDSKU_MISSING"
    
    start_index = 0
    first_word = words[0].upper()
    if re.search(r'\d', first_word) or 'PCS' in first_word or 'PACK' in first_word:
        start_index = 1
    
    sku_words = words[start_index:start_index + 3]
    if not sku_words: sku_words = words[0:1]  
    return '_'.join(sku_words).upper()


def create_output_df(product_list):
    columns = [
        'sku_supplier_config', 'seller_sku', 'name', 'brand', 
        'categories', 
        'product_weight', 'package_type', 'package_quantities', 
        'variation', 'price', 'tax_class', 'cost', 'color', 'main_material', 
        'description', 'short_description', 'package_content', 'supplier', 
        'shipment_type'
    ]
    df = pd.DataFrame(product_list, columns=columns)
    return df.fillna('', inplace=False)


def get_csv_download_link(df):
    if df.empty:
        filename = "empty.csv"
    else:
        raw_name = df.iloc[0]['name']
        cleaned_name = re.sub(r'[^a-zA-Z0-9\s]', '', raw_name).strip()
        filename_base = cleaned_name.replace(' ', '_').upper()[:30] 
        filename = f"{filename_base}_and_{len(df)-1}_more.csv" if len(df) > 1 else f"{filename_base}.csv"
            
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">**Download Generated CSV File: {filename}**</a>'
    return href

# --- APP LAYOUT ---
st.set_page_config(layout="wide", page_title="Product Data Generator")
st.title("📦 Product Data Generator")

if 'products' not in st.session_state:
    st.session_state.products = []

# --- LOAD DATA ---
cat_df, path_to_code, root_list = load_category_data()

# --- INPUT FORM ---
st.header("1. Enter New Product Details")
with st.form(key='product_form'):
    col_name, col_brand = st.columns([3, 1])
    with col_name:
        new_name = st.text_input("Product Name", placeholder="e.g., 10PCS Refrigerator Bags")
    with col_brand:
        new_brand = st.text_input("Brand", value=DEFAULT_BRAND)

    # --- NEW: DEPARTMENT FILTER ---
    st.subheader("Category Selection")
    
    # Step 1: Filter by Department
    col_filter, col_select = st.columns([1, 2])
    
    with col_filter:
        # Add "All Departments" as the default first option
        filter_options = ["All Departments"] + root_list
        selected_root = st.selectbox("1. Filter by Department", options=filter_options)
    
    with col_select:
        # Filter the main list based on Step 1
        if selected_root == "All Departments":
            filtered_paths = cat_df['category'].dropna().unique().tolist()
        else:
            filtered_paths = cat_df[cat_df['root_category'] == selected_root]['category'].dropna().unique().tolist()
        
        # Add default option
        final_options = [DEFAULT_CATEGORY_PATH] + sorted(filtered_paths)
        
        # Step 2: The actual selection
        selected_category_path = st.selectbox("2. Select Specific Category", options=final_options)

    # -------------------------------

    st.subheader("Optional Attributes")
    col_color, col_material = st.columns(2)
    with col_color:
        new_color = st.text_input("Color", value=DEFAULT_COLOR)
    with col_material:
        new_material = st.text_input("Main Material", value=DEFAULT_MATERIAL)
        
    st.markdown("---")
    new_description = st.text_area("Full Description")
    new_short_description_raw = st.text_area("Short Description (Highlights)", height=150)
    st.markdown("---")
    
    submit_button = st.form_submit_button(label='➕ Add Product to List')

if submit_button:
    if not new_name or not new_description or not new_short_description_raw:
        st.error("Please fill in Name, Description, and Short Description.")
    elif selected_category_path == DEFAULT_CATEGORY_PATH:
        st.error("Please select a Category.")
    else:
        # Retrieve the code
        final_code = path_to_code.get(selected_category_path, '')
        
        generated_sku = generate_sku_config(new_name)
        new_short_description_html = format_to_html_list(new_short_description_raw)
        
        new_product = {
            'name': new_name,
            'description': new_description,
            'short_description': new_short_description_html,
            'sku_supplier_config': generated_sku,
            'seller_sku': generated_sku,
            'package_content': new_name,
            'categories': final_code, 
            'brand': new_brand,
            'color': new_color,
            'main_material': new_material,
            **TEMPLATE_DATA
        }
        
        st.session_state.products.append(new_product)
        st.success(f"Added: {new_name} | Code: {final_code}")

# --- OUTPUT ---
st.header("2. Generated Product List")
if st.session_state.products:
    final_df = create_output_df(st.session_state.products)
    
    st.dataframe(final_df[['name', 'categories', 'sku_supplier_config']].tail(5), use_container_width=True)
    st.markdown(get_csv_download_link(final_df), unsafe_allow_html=True)
    
    if st.button("🗑️ Clear List"):
        st.session_state.products = []
        st.rerun()
else:
    st.info("Add a product to generate the CSV.")
