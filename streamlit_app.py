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
st.set_page_config(layout="wide", page_title="Product Bulk Creator")

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
    'cost': 1,  # FIXED: Always 1
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
    st.session_state.edit_index = None 

if 'quill_key' not in st.session_state:
    st.session_state.quill_key = 0      

if 'quill_content' not in st.session_state:
    st.session_state.quill_content = "" 

for key in default_keys:
    if key not in st.session_state:
        st.session_state[key] = ""
    if key == 'prod_brand' and not st.session_state[key]: st.session_state[key] = DEFAULT_BRAND
    if key == 'prod_material' and not st.session_state[key]: st.session_state[key] = DEFAULT_MATERIAL

# --- HELPER FUNCTIONS ---

def clear_form():
    """Resets text inputs and Quill to defaults."""
    for key in default_keys:
        st.session_state[key] = ""
    st.session_state['prod_brand'] = DEFAULT_BRAND
    st.session_state['prod_material'] = DEFAULT_MATERIAL
    st.session_state.quill_content = "" 
    st.session_state.quill_key += 1 
    st.session_state.edit_index = None

def load_product_for_edit(index):
    """Loads a product from the list into the form."""
    product = st.session_state.products[index]
    st.session_state['prod_name'] = product.get('name', '')
    st.session_state['prod_brand'] = product.get('brand', '')
    st.session_state['prod_color'] = product.get('color', '')
    st.session_state['prod_material'] = product.get('main_material', '')
    
    # Strip HTML tags for the text area to allow re-editing as plain text
    raw_short = product.get('short_description', '')
    clean_short = re.sub('<[^<]+?>', '', raw_short).strip()
    st.session_state['prod_short'] = clean_short
    
    st.session_state.quill_content = product.get('description', '')
    st.session_state.quill_key += 1
    st.session_state.edit_index = index

def format_to_html_list(text):
    """Automatically converts lines of text into an HTML Unordered List."""
    if not text: return ''
    # Split by lines and remove empty lines/whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines: return ''
    
    list_items = [f'<li>{line}</li>' for line in lines]
    return f'<ul>{" ".join(list_items)}</ul>'

def generate_sku_config(name):
    if not name: return "SKU_MISSING"
    cleaned = re.sub(r'[^\w\s]', '', name).strip().upper()
    words = cleaned.split()
    if not words: return "SKU_MISSING"
    # Skip numeric prefixes like "10PCS"
    start = 1 if (re.search(r'\d', words[0]) or 'PCS' in words[0]) and len(words) > 1 else 0
    return '_'.join(words[start:start+3])

@st.cache_data
def load_category_data():
    if os.path.exists(FILE_NAME_CSV):
        df = pd.read_csv(FILE_NAME_CSV, dtype=str)
        df['category'] = df['category'].str.strip()
        df['root_category'] = df['category'].apply(lambda x: str(x).split('\\')[0] if pd.notna(x) else "Other")
        path_to_code = df.set_index('category')['categories'].to_dict()
        return df, path_to_code, sorted(df['root_category'].unique().tolist())
    return pd.DataFrame(), {}, []

def save_product_callback():
    if not st.session_state['prod_name']:
        st.error("Product Name is required.")
        return
    
    # Resolve Category
    cat_path = st.session_state.get('cat_selector_a', DEFAULT_CATEGORY_PATH)
    if cat_path == DEFAULT_CATEGORY_PATH:
        cat_path = st.session_state.get('cat_selector_b', DEFAULT_CATEGORY_PATH)
    
    code = path_to_code.get(cat_path, '')
    if not code or cat_path == DEFAULT_CATEGORY_PATH:
        st.error("Please select a valid Category.")
        return

    sku = generate_sku_config(st.session_state['prod_name'])
    
    # AUTO-BULLET LOGIC
    short_html = format_to_html_list(st.session_state['prod_short'])
    
    # In the box logic
    box_raw = st.session_state['prod_in_box'].strip()
    box_content = format_to_html_list(box_raw if box_raw else st.session_state['prod_name'])

    new_product = {
        'name': st.session_state['prod_name'],
        'description': st.session_state.get('current_quill_html', ''),      
        'short_description': short_html, 
        'package_content': box_content, 
        'sku_supplier_config': sku,
        'seller_sku': sku,
        'categories': code, 
        'brand': st.session_state['prod_brand'],
        'color': st.session_state['prod_color'],
        'main_material': st.session_state['prod_material'],
        **TEMPLATE_DATA # This ensures cost is always 1
    }

    if st.session_state['custom_col_name'] and st.session_state['custom_col_val']:
        new_product[st.session_state['custom_col_name']] = st.session_state['custom_col_val']

    if st.session_state.edit_index is not None:
        st.session_state.products[st.session_state.edit_index] = new_product
    else:
        st.session_state.products.append(new_product)

    clear_form()
    st.toast("Product Saved!")

# --- UI RENDER ---
cat_df, path_to_code, root_list = load_category_data()

st.header("1. Category & Details")
t1, t2 = st.tabs(["Browse", "Search"])
with t1:
    c1, c2 = st.columns(2)
    root = c1.selectbox("Dept", ["Select"] + root_list)
    cat_selection_a = c2.selectbox("Category", [DEFAULT_CATEGORY_PATH] + sorted(cat_df[cat_df['root_category']==root]['category'].tolist()) if root != "Select" else [DEFAULT_CATEGORY_PATH], key='cat_selector_a')
with t2:
    search = st.text_input("Search Category")
    cat_selection_b = st.selectbox("Results", [DEFAULT_CATEGORY_PATH] + sorted(cat_df[cat_df['category'].str.contains(search, case=False, na=False)]['category'].tolist()) if search else [DEFAULT_CATEGORY_PATH], key='cat_selector_b')

st.markdown("---")

col_n, col_b = st.columns([3, 1])
col_n.text_input("Product Name", key='prod_name')
col_b.text_input("Brand", key='prod_brand')

st.subheader("Full Description")
st.session_state['current_quill_html'] = st_quill(value=st.session_state.quill_content, html=True, key=f"q_{st.session_state.quill_key}")

st.subheader("Short Description (Automatic Bullets)")
st.text_area("Paste features here (one per line)", key='prod_short', help="Every new line will automatically become a bullet point in the output.")

st.subheader("What's in the Box")
st.text_area("Package contents", key='prod_in_box')

if st.button("Add/Update Product", on_click=save_product_callback, type="primary"):
    pass

# --- DOWNLOAD ---
if st.session_state.products:
    st.markdown("---")
    df_out = pd.DataFrame(st.session_state.products)
    csv = df_out.to_csv(index=False).encode('utf-8')
    st.download_button("Download CSV", data=csv, file_name="products.csv", mime="text/csv")
    st.dataframe(df_out)
