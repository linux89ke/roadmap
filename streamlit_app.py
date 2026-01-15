import streamlit as st
import pandas as pd
import re
import base64
import os

# --- IMPORT QUILL ---
try:
    from streamlit_quill import st_quill
except ImportError:
    st.error("Please run: pip install streamlit-quill")
    st.stop()

# --- APP CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Product Data Generator")

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

# --- INITIALIZE SESSION STATE ---
default_keys = [
    'prod_name', 'prod_brand', 'prod_color', 'prod_material', 
    'prod_short', 'prod_in_box', 'custom_col_name', 'custom_col_val'
]

if 'products' not in st.session_state:
    st.session_state.products = []

if 'edit_index' not in st.session_state:
    st.session_state.edit_index = None  # None = Adding new, Integer = Editing index

if 'quill_key' not in st.session_state:
    st.session_state.quill_key = 0      # Used to force reset/reload Quill

if 'quill_content' not in st.session_state:
    st.session_state.quill_content = "" # Holds HTML for Quill

# Initialize widget state if not present
for key in default_keys:
    if key not in st.session_state:
        st.session_state[key] = ""
    # Set defaults
    if key == 'prod_brand' and not st.session_state[key]: st.session_state[key] = DEFAULT_BRAND
    if key == 'prod_material' and not st.session_state[key]: st.session_state[key] = DEFAULT_MATERIAL

# --- HELPER FUNCTIONS ---

def clear_form():
    """Resets text inputs and Quill to defaults, keeps Category active."""
    for key in default_keys:
        st.session_state[key] = ""
    
    # Restore defaults
    st.session_state['prod_brand'] = DEFAULT_BRAND
    st.session_state['prod_material'] = DEFAULT_MATERIAL
    
    # Reset Quill
    st.session_state.quill_content = "" 
    st.session_state.quill_key += 1 
    
    # Reset Edit Mode
    st.session_state.edit_index = None

def load_product_for_edit(index):
    """Loads a product from the list into the form widgets."""
    product = st.session_state.products[index]
    
    st.session_state['prod_name'] = product.get('name', '')
    st.session_state['prod_brand'] = product.get('brand', '')
    st.session_state['prod_color'] = product.get('color', '')
    st.session_state['prod_material'] = product.get('main_material', '')
    
    # We clear short/box inputs because we can't easily convert HTML back to raw text lists
    # without a complex parser. Editing will require re-typing these specific fields if changed.
    st.session_state['prod_short'] = "" 
    st.session_state['prod_in_box'] = ""
    
    # Load Quill
    st.session_state.quill_content = product.get('description', '')
    st.session_state.quill_key += 1
    
    st.session_state.edit_index = index

def delete_product(index):
    """Removes a product from the list."""
    if 0 <= index < len(st.session_state.products):
        st.session_state.products.pop(index)
        # If we were editing the deleted item, clear form
        if st.session_state.edit_index == index:
            clear_form()
        # If we were editing an item AFTER the deleted one, shift index down
        elif st.session_state.edit_index is not None and st.session_state.edit_index > index:
            st.session_state.edit_index -= 1

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
        # Dummy fallback
        return pd.DataFrame({'category':['Test'], 'root_category':['Test'], 'categories':['123']}), {'Test':'123'}, ['Test']

    if not df.empty:
        for col in ['name', 'category', 'categories']:
            if col in df.columns: df[col] = df[col].str.strip()

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
    standard_columns = [
        'sku_supplier_config', 'seller_sku', 'name', 'brand', 
        'categories', 
        'product_weight', 'package_type', 'package_quantities', 
        'variation', 'price', 'tax_class', 'cost', 'color', 'main_material', 
        'description', 'short_description', 'package_content', 'supplier', 
        'shipment_type'
    ]
    df = pd.DataFrame(product_list)
    existing_standard = [c for c in standard_columns if c in df.columns]
    custom_columns = [c for c in df.columns if c not in standard_columns]
    final_order = existing_standard + custom_columns
    return df[final_order].fillna('')

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

# --- LOGIC TO SAVE PRODUCT (CALLBACK) ---
def save_product_callback():
    # 1. Validate
    if not st.session_state['prod_name']:
        st.error("Product Name is required.")
        return
    
    # We need access to the selected category here. 
    # Since 'selected_category_path' is calculated in the main script, 
    # we need to grab the widget values from state directly.
    cat_path = DEFAULT_CATEGORY_PATH
    
    # Try Method A first
    if st.session_state.get('cat_selector_a') and st.session_state['cat_selector_a'] != DEFAULT_CATEGORY_PATH:
        cat_path = st.session_state['cat_selector_a']
    # Try Method B if A is not set
    elif st.session_state.get('cat_selector_b') and st.session_state['cat_selector_b'] != DEFAULT_CATEGORY_PATH:
        cat_path = st.session_state['cat_selector_b']
        
    code = path_to_code.get(cat_path, '')

    if cat_path == DEFAULT_CATEGORY_PATH or not code:
        st.error("Please select a valid Category.")
        return

    # 2. Process Data
    generated_sku = generate_sku_config(st.session_state['prod_name'])
    short_desc_html = format_to_html_list(st.session_state['prod_short'])
    final_box_content = st.session_state['prod_in_box'] if st.session_state['prod_in_box'].strip() else st.session_state['prod_name']
    package_content_html = format_to_html_list(final_box_content)
    
    # Use the Description from Session State (Quill)
    # Note: st_quill writes to its own key, but we need to capture it.
    new_product = {
        'name': st.session_state['prod_name'],
        'description': st.session_state.get('current_quill_html', ''),      
        'short_description': short_desc_html, 
        'package_content': package_content_html, 
        'sku_supplier_config': generated_sku,
        'seller_sku': generated_sku,
        'categories': code, 
        'brand': st.session_state['prod_brand'],
        'color': st.session_state['prod_color'],
        'main_material': st.session_state['prod_material'],
        **TEMPLATE_DATA
    }
    
    if st.session_state['custom_col_name'] and st.session_state['custom_col_val']:
        new_product[st.session_state['custom_col_name']] = st.session_state['custom_col_val']

    # 3. Add or Update
    if st.session_state.edit_index is not None:
        # Update existing
        st.session_state.products[st.session_state.edit_index] = new_product
        st.toast(f"Updated: {st.session_state['prod_name']}")
    else:
        # Add new
        st.session_state.products.append(new_product)
        st.toast(f"Added: {st.session_state['prod_name']}")

    # 4. Clear Form
    clear_form()

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Options")
    if st.button("🗑️ Reset Entire App", type="primary"):
        st.session_state.products = []
        clear_form()
        st.rerun()

st.title("Product Data Generator")

# --- LOAD DATA ---
cat_df, path_to_code, root_list = load_category_data()

# --- 1. CATEGORY SELECTION ---
st.header("1. Find Category")
tab1, tab2 = st.tabs(["Browse by Department", " Global Search"])

selected_category_path = DEFAULT_CATEGORY_PATH

# Method A: Dept Filter
with tab1:
    col_dept, col_cat = st.columns([1, 2])
    with col_dept:
        selected_root = st.selectbox(
            "Step A: Choose Department", 
            options=["Select Department"] + root_list,
            key='dept_selector' 
        )
    with col_cat:
        if selected_root and selected_root != "Select Department":
            filtered_paths = cat_df[cat_df['root_category'] == selected_root]['category'].dropna().unique().tolist()
            filtered_paths = sorted(filtered_paths)
            cat_selection_a = st.selectbox(
                "Step B: Select Specific Category", 
                options=[DEFAULT_CATEGORY_PATH] + filtered_paths,
                key='cat_selector_a'
            )
            if cat_selection_a != DEFAULT_CATEGORY_PATH:
                selected_category_path = cat_selection_a
        else:
            st.selectbox("Step B: Select Specific Category", options=["First select a department"], disabled=True)

# Method B: Global Search
with tab2:
    search_query = st.text_input("Type a keyword", key='search_query')
    if search_query:
        search_results = cat_df[cat_df['category'].str.contains(search_query, case=False, na=False)]
        found_paths = sorted(search_results['category'].unique().tolist())
        if found_paths:
            cat_selection_b = st.selectbox(
                f"Found {len(found_paths)} results:", 
                options=[DEFAULT_CATEGORY_PATH] + found_paths,
                key='cat_selector_b'
            )
            if cat_selection_b != DEFAULT_CATEGORY_PATH:
                selected_category_path = cat_selection_b
        else:
            st.warning("No categories found.")

if selected_category_path != DEFAULT_CATEGORY_PATH:
    final_code = path_to_code.get(selected_category_path, '')
    st.success(f" Selected: **{selected_category_path}** (Code: {final_code})")
else:
    st.warning("Please select a category above.")
    final_code = ""

# --- 2. PRODUCT DETAILS FORM ---
st.markdown("---")

if st.session_state.edit_index is not None:
    st.markdown(f"### ✏️ Editing Product #{st.session_state.edit_index + 1}")
else:
    st.header("2. Product Details")

with st.container():
    col_name, col_brand = st.columns([3, 1])
    with col_name:
        st.text_input("Product Name", key='prod_name', placeholder="e.g., 10PCS Refrigerator Bags")
    with col_brand:
        st.text_input("Brand", key='prod_brand')

    st.subheader("Optional Attributes")
    col_color, col_material = st.columns(2)
    with col_color:
        st.text_input("Color", key='prod_color')
    with col_material:
        st.text_input("Main Material", key='prod_material')
        
    st.markdown("---")

    # --- EDITOR 1: FULL DESCRIPTION ---
    st.subheader("Full Description")
    current_quill_html = st_quill(
        value=st.session_state.quill_content, 
        placeholder="Enter full description here...",
        html=True,
        key=f"quill_{st.session_state.quill_key}"
    )
    # Save the current quill output to session state so callback can access it
    st.session_state['current_quill_html'] = current_quill_html

    # --- EDITOR 2: SHORT DESCRIPTION ---
    st.markdown("---")
    st.subheader("Short Description")
    st.text_area("Enter highlights (one per line)", height=150, key='prod_short')

    # --- IN THE BOX ---
    st.markdown("---")
    st.subheader("What's in the Box")
    st.text_area("Enter package content", height=100, key='prod_in_box')
    
    # --- CUSTOM COLUMN ---
    st.markdown("---")
    c_custom_1, c_custom_2 = st.columns(2)
    with c_custom_1:
        st.text_input("Custom Column Name", key='custom_col_name')
    with c_custom_2:
        st.text_input("Custom Value", key='custom_col_val')
    
    st.markdown("---")
    
    # --- ACTION BUTTONS ---
    col_btn_1, col_btn_2 = st.columns([1, 4])
    
    with col_btn_1:
        if st.session_state.edit_index is not None:
            st.button("💾 Update Product", on_click=save_product_callback, type="primary", use_container_width=True)
        else:
            st.button("➕ Add Product", on_click=save_product_callback, type="primary", use_container_width=True)
            
    with col_btn_2:
        if st.session_state.edit_index is not None:
            st.button("❌ Cancel Edit", on_click=clear_form)

# --- 3. MANAGE & DOWNLOAD ---
st.markdown("---")
st.header("3. Manage & Download Data")

if st.session_state.products:
    
    st.write(f"**Total Products:** {len(st.session_state.products)}")
    
    # Header Row
    c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
    c1.markdown("**Product Name**")
    c2.markdown("**Category Code**")
    c3.markdown("**Action**")
    c4.markdown("**Action**")
    
    for i, prod in enumerate(st.session_state.products):
        with st.container():
            st.markdown("---")
            c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
            
            is_editing = (st.session_state.edit_index == i)
            name_display = f"✏️ **{prod['name']}** (Editing)" if is_editing else prod['name']
            
            c1.markdown(name_display)
            c2.text(prod['categories'])
            
            # Use Callbacks (on_click) to avoid Session State crash
            c3.button("Edit", key=f"edit_{i}", on_click=load_product_for_edit, args=(i,))
            c4.button("Delete", key=f"del_{i}", on_click=delete_product, args=(i,))

    st.markdown("---")
    
    # --- DOWNLOAD SECTION ---
    final_df = create_output_df(st.session_state.products)
    st.markdown(get_csv_download_link(final_df), unsafe_allow_html=True)

    with st.expander("View Raw Data Table"):
        st.dataframe(final_df, use_container_width=True)

else:
    st.info("No products added yet.")
