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
st.set_page_config(layout="wide", page_title="Product Manager")

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
    'cost': 1,  # LOCKED TO 1
    'supplier': 'MarketPlace forfeited items',
    'shipment_type': 'Own Warehouse',
}

# --- INITIALIZE SESSION STATE ---
default_keys = [
    'prod_name', 'prod_brand', 'prod_color', 'prod_material', 
    'prod_in_box', 'custom_col_name', 'custom_col_val'
]

if 'products' not in st.session_state:
    st.session_state.products = []

if 'edit_index' not in st.session_state:
    st.session_state.edit_index = None 

if 'quill_key' not in st.session_state:
    st.session_state.quill_key = 0      

if 'quill_content_full' not in st.session_state:
    st.session_state.quill_content_full = "" 

if 'quill_content_short' not in st.session_state:
    st.session_state.quill_content_short = "" 

for key in default_keys:
    if key not in st.session_state:
        st.session_state[key] = ""
    if key == 'prod_brand' and not st.session_state[key]: st.session_state[key] = DEFAULT_BRAND
    if key == 'prod_material' and not st.session_state[key]: st.session_state[key] = DEFAULT_MATERIAL

# --- HELPER FUNCTIONS ---

def format_to_html_list(text):
    if not text: return ''
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines: return ''
    return f'<ul>{"".join([f"<li>{l}</li>" for l in lines])}</ul>'

def clear_form():
    for key in default_keys:
        st.session_state[key] = ""
    st.session_state['prod_brand'] = DEFAULT_BRAND
    st.session_state['prod_material'] = DEFAULT_MATERIAL
    st.session_state.quill_content_full = "" 
    st.session_state.quill_content_short = "" 
    st.session_state.quill_key += 1 
    st.session_state.edit_index = None

def load_product_for_edit(index):
    product = st.session_state.products[index]
    st.session_state['prod_name'] = product.get('name', '')
    st.session_state['prod_brand'] = product.get('brand', '')
    st.session_state['prod_color'] = product.get('color', '')
    st.session_state['prod_material'] = product.get('main_material', '')
    
    st.session_state.quill_content_full = product.get('description', '')
    st.session_state.quill_content_short = product.get('short_description', '')
    
    box_html = product.get('package_content', '')
    st.session_state['prod_in_box'] = re.sub('<[^<]+?>', '', box_html).strip()
    
    st.session_state.quill_key += 1
    st.session_state.edit_index = index

def generate_sku_config(name):
    if not name: return "SKU_MISSING"
    cleaned = re.sub(r'[^\w\s]', '', name).strip().upper()
    words = cleaned.split()
    if not words: return "SKU_MISSING"
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
    
    cat_path = st.session_state.get('cat_selector_a', DEFAULT_CATEGORY_PATH)
    if cat_path == DEFAULT_CATEGORY_PATH:
        cat_path = st.session_state.get('cat_selector_b', DEFAULT_CATEGORY_PATH)
    
    code = path_to_code.get(cat_path, '')
    if not code or cat_path == DEFAULT_CATEGORY_PATH:
        st.error("Please select a valid Category.")
        return

    sku = generate_sku_config(st.session_state['prod_name'])
    
    box_raw = st.session_state['prod_in_box'].strip()
    package_content_html = format_to_html_list(box_raw if box_raw else st.session_state['prod_name'])

    new_product = {
        'name': st.session_state['prod_name'],
        'description': st.session_state.get('current_quill_full', ''),      
        'short_description': st.session_state.get('current_quill_short', ''), 
        'package_content': package_content_html, 
        'sku_supplier_config': sku,
        'seller_sku': sku,
        'categories': code, 
        'brand': st.session_state['prod_brand'],
        'color': st.session_state['prod_color'],
        'main_material': st.session_state['prod_material'],
        **TEMPLATE_DATA
    }

    if st.session_state['custom_col_name'] and st.session_state['custom_col_val']:
        new_product[st.session_state['custom_col_name']] = st.session_state['custom_col_val']

    if st.session_state.edit_index is not None:
        st.session_state.products[st.session_state.edit_index] = new_product
    else:
        st.session_state.products.append(new_product)

    clear_form()
    st.toast("Product Saved")

# --- UI ---
cat_df, path_to_code, root_list = load_category_data()

st.title("Bulk Product Creator")

st.header("1. Category")
t1, t2 = st.tabs(["Browse", "Search"])
with t1:
    c1, c2 = st.columns(2)
    with c1: root = st.selectbox("Dept", ["Select"] + root_list, key="d")
    with c2: st.selectbox("Category", [DEFAULT_CATEGORY_PATH] + sorted(cat_df[cat_df['root_category']==root]['category'].tolist()) if root != "Select" else [DEFAULT_CATEGORY_PATH], key="cat_selector_a")
with t2:
    s = st.text_input("Search")
    st.selectbox("Results", [DEFAULT_CATEGORY_PATH] + sorted(cat_df[cat_df['category'].str.contains(s, case=False, na=False)]['category'].tolist()) if s else [DEFAULT_CATEGORY_PATH], key="cat_selector_b")

st.markdown("---")
st.header("2. Details")

cn, cb = st.columns([3, 1])
cn.text_input("Product Name", key='prod_name')
cb.text_input("Brand", key='prod_brand')

st.subheader("Full Description")
st.session_state['current_quill_full'] = st_quill(
    value=st.session_state.quill_content_full, 
    html=True, 
    key=f"qf_{st.session_state.quill_key}",
    toolbar=["bold", "italic", "underline", "strike", {"list": "ordered"}, {"list": "bullet"}, "link", "clean"]
)

st.subheader("Short Description")
st.session_state['current_quill_short'] = st_quill(
    value=st.session_state.quill_content_short, 
    html=True, 
    key=f"qs_{st.session_state.quill_key}",
    toolbar=["bold", "italic", {"list": "bullet"}, "clean"]
)

st.subheader("What's in the Box")
st.text_area("Contents (one per line)", key='prod_in_box')

if st.button("Save Product", type="primary", on_click=save_product_callback):
    pass

# --- EXPORT ---
if st.session_state.products:
    st.markdown("---")
    df = pd.DataFrame(st.session_state.products)
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download CSV", data=csv, file_name="export.csv", mime="text/csv")
    
    for i, p in enumerate(st.session_state.products):
        col1, col2, col3 = st.columns([5, 1, 1])
        col1.write(p['name'])
        col2.button("Edit", key=f"ed_{i}", on_click=load_product_for_edit, args=(i,))
        if col3.button("Delete", key=f"de_{i}"):
            st.session_state.products.pop(i)
            st.rerun()
