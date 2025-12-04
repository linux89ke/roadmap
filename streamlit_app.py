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

# --- RESET FUNCTION ---
def hard_reset():
    """
    Clears the product list AND resets all widget states to defaults.
    """
    # 1. Clear the data list
    st.session_state.products = []
    
    # 2. Reset Widgets by setting their session_state keys
    # Dropdowns
    if 'dept_selector' in st.session_state: st.session_state['dept_selector'] = "Select Department"
    if 'cat_selector_a' in st.session_state: st.session_state['cat_selector_a'] = DEFAULT_CATEGORY_PATH
    if 'cat_selector_b' in st.session_state: st.session_state['cat_selector_b'] = DEFAULT_CATEGORY_PATH
    
    # Text Inputs
    if 'search_query' in st.session_state: st.session_state['search_query'] = ""
    if 'prod_name' in st.session_state: st.session_state['prod_name'] = ""
    if 'prod_brand' in st.session_state: st.session_state['prod_brand'] = DEFAULT_BRAND
    if 'prod_color' in st.session_state: st.session_state['prod_color'] = DEFAULT_COLOR
    if 'prod_material' in st.session_state: st.session_state['prod_material'] = DEFAULT_MATERIAL
    if 'prod_desc' in st.session_state: st.session_state['prod_desc'] = ""
    if 'prod_short' in st.session_state: st.session_state['prod_short'] = ""

@st.cache_data
def load_category_data():
    df = pd.DataFrame()
    if os.path.exists(FILE_NAME_CSV):
        try:
            df = pd.read_csv(FILE_NAME_CSV, dtype=str)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return pd.DataFrame(), {}, [], []
    else:
        st.error(f"CRITICAL ERROR: '{FILE_NAME_CSV}' not found.")
        return pd.DataFrame(), {}, [], []

    if not df.empty:
        if 'name' in df.columns: df['name'] = df['name'].str.strip()
        if 'category' in df.columns: df['category'] = df['category'].str.strip()
        if 'categories' in df.columns: df['categories'] = df['categories'].str.strip()

        def get_root(path):
            if pd.isna(path): return "Other"
            parts = str(path).split('\\')
            return parts[0] if parts else "Other"

        df['root_category'] = df['category'].apply(get_root)
        path_to_code = df.set_index('category')['categories'].to_dict()
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

# --- SIDEBAR (TOTAL RESET) ---
with st.sidebar:
    st.header("⚙️ Options")
    st.info("Finished with this batch? Click below to fully reset the app (List, Form, and Categories).")
    
    # We use a callback function to ensure state is cleared BEFORE the rerun
    st.button("🗑️ Start New Batch (Reset All)", on_click=hard_reset, type="primary")

st.title("📦 Product Data Generator")

if 'products' not in st.session_state:
    st.session_state.products = []

# --- LOAD DATA ---
cat_df, path_to_code, root_list = load_category_data()

# --- 1. CATEGORY SELECTION ---
st.header("1. Find Category")
tab1, tab2 = st.tabs(["📂 Browse by Department", "🔍 Global Search"])

selected_category_path = DEFAULT_CATEGORY_PATH

# --- METHOD A: DEPT FILTER ---
with tab1:
    col_dept, col_cat = st.columns([1, 2])
    with col_dept:
        # Added key='dept_selector' so we can reset it
        selected_root = st.selectbox(
            "Step A: Choose Department", 
            options=["Select Department"] + root_list,
            key='dept_selector' 
        )
    
    with col_cat:
        if selected_root and selected_root != "Select Department":
            filtered_paths = cat_df[cat_df['root_category'] == selected_root]['category'].dropna().unique().tolist()
            filtered_paths = sorted(filtered_paths)
            
            # Added key='cat_selector_a'
            cat_selection_a = st.selectbox(
                "Step B: Select Specific Category", 
                options=[DEFAULT_CATEGORY_PATH] + filtered_paths,
                key='cat_selector_a'
            )
            if cat_selection_a != DEFAULT_CATEGORY_PATH:
                selected_category_path = cat_selection_a
        else:
            st.selectbox("Step B: Select Specific Category", options=["First select a department"], disabled=True)

# --- METHOD B: GLOBAL SEARCH ---
with tab2:
    # Added key='search_query'
    search_query = st.text_input(
        "Type a keyword (e.g. 'HDMI', 'Baby', 'Dress')",
        key='search_query'
    )
    
    if search_query:
        search_results = cat_df[cat_df['category'].str.contains(search_query, case=False, na=False)]
        found_paths = sorted(search_results['category'].unique().tolist())
        if found_paths:
            # Added key='cat_selector_b'
            cat_selection_b = st.selectbox(
                f"Found {len(found_paths)} results:", 
                options=[DEFAULT_CATEGORY_PATH] + found_paths,
                key='cat_selector_b'
            )
            if cat_selection_b != DEFAULT_CATEGORY_PATH:
                selected_category_path = cat_selection_b
        else:
            st.warning("No categories found matching that keyword.")

# Display Selected Category
if selected_category_path != DEFAULT_CATEGORY_PATH:
    final_code = path_to_code.get(selected_category_path, '')
    st.success(f"✅ Selected: **{selected_category_path}** (Code: {final_code})")
else:
    st.warning("⚠️ Please select a category above before adding a product.")
    final_code = ""


# --- 2. PRODUCT DETAILS FORM ---
st.markdown("---")
st.header("2. Product Details")

# NOTE: We use st.form to group inputs, but we assign KEYS to them for resetting.
with st.form(key='product_form'):
    col_name, col_brand = st.columns([3, 1])
    with col_name:
        new_name = st.text_input("Product Name", placeholder="e.g., 10PCS Refrigerator Bags", key='prod_name')
    with col_brand:
        new_brand = st.text_input("Brand", value=DEFAULT_BRAND, key='prod_brand')

    st.subheader("Optional Attributes")
    col_color, col_material = st.columns(2)
    with col_color:
        new_color = st.text_input("Color", value=DEFAULT_COLOR, key='prod_color')
    with col_material:
        new_material = st.text_input("Main Material", value=DEFAULT_MATERIAL, key='prod_material')
        
    st.markdown("---")
    new_description = st.text_area("Full Description", key='prod_desc')
    new_short_description_raw = st.text_area("Short Description (Highlights)", height=150, key='prod_short')
    
    submit_button = st.form_submit_button(label='➕ Add Product to List')

if submit_button:
    if not new_name or not new_description or not new_short_description_raw:
        st.error("Please fill in Name, Description, and Short Description.")
    elif selected_category_path == DEFAULT_CATEGORY_PATH or not final_code:
        st.error("Please go back to Section 1 and select a valid Category.")
    else:
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
        st.success(f"Added: {new_name}")

# --- OUTPUT ---
st.markdown("---")
st.header("3. Download Data")
if st.session_state.products:
    final_df = create_output_df(st.session_state.products)
    
    st.dataframe(final_df[['name', 'categories', 'sku_supplier_config']].tail(5), use_container_width=True)
    st.markdown(get_csv_download_link(final_df), unsafe_allow_html=True)
    
else:
    st.info("Products added to the list will appear here.")
