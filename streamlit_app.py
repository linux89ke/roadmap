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
    'cost': 1,  # UPDATED: Locked to 1
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

def format_to_html_list(text):
    """Converts plain text lines into HTML bullet points."""
    if not text: return ''
    # Remove existing HTML tags if user is re-editing to avoid nested lists
    clean_text = re.sub('<[^<]+?>', '', text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    if not lines: return ''
    list_items = [f'    <li>{line}</li>' for line in lines]
    return f'<ul>\n{"".join(list_items)}\n</ul>'

def clear_form():
    for key in default_keys:
        st.session_state[key] = ""
    st.session_state['prod_brand'] = DEFAULT_BRAND
    st.session_state['prod_material'] = DEFAULT_MATERIAL
    st.session_state.quill_content = "" 
    st.session_state.quill_key += 1 
    st.session_state.edit_index = None

def load_product_for_edit(index):
    product = st.session_state.products[index]
    st.session_state['prod_name'] = product.get('name', '')
    st.session_state['prod_brand'] = product.get('brand', '')
    st.session_state['prod_color'] = product.get('color', '')
    st.session_state['prod_material'] = product.get('main_material', '')
    
    # Strip HTML back to plain text for the text area
    short_html = product.get('short_description', '')
    st.session_state['prod_short'] = re.sub('<[^<]+?>', '', short_html).replace('    ', '').strip()
    
    box_html = product.get('package_content', '')
    st.session_state['prod_in_box'] = re.sub('<[^<]+?>', '', box_html).replace('    ', '').strip()
    
    st.session_state.quill_content = product.get('description', '')
    st.session_state.quill_key += 1
    st.session_state.edit_index = index

def delete_product(index):
    if 0 <= index < len(st.session_state.products):
        st.session_state.products.pop(index)
        if st.session_state.edit_index == index:
            clear_form()
        elif st.session_state.edit_index is not None and st.session_state.edit_index > index:
            st.session_state.edit_index -= 1

@st.cache_data
def load_category_data():
    if os.path.exists(FILE_NAME_CSV):
        df = pd.read_csv(FILE_NAME_CSV, dtype=str)
        df['category'] = df['category'].str.strip()
        df['root_category'] = df['category'].apply(lambda x: str(x).split('\\')[0] if pd.notna(x) else "Other")
        path_to_code = df.set_index('category')['categories'].to_dict()
        return df, path_to_code, sorted(df['root_category'].unique().tolist())
    return pd.DataFrame(), {}, []

def generate_sku_config(name):
    if not name: return "SKU_MISSING"
    cleaned = re.sub(r'[^\w\s]', '', name).strip().upper()
    words = cleaned.split()
    if not words: return "SKU_MISSING"
    start = 1 if (re.search(r'\d', words[0]) or 'PCS' in words[0]) and len(words) > 1 else 0
    return '_'.join(words[start:start+3])

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
    
    # Process text areas into HTML bullets automatically
    short_html = format_to_html_list(st.session_state['prod_short'])
    box_raw = st.session_state['prod_in_box'].strip()
    package_content_html = format_to_html_list(box_raw if box_raw else st.session_state['prod_name'])

    new_product = {
        'name': st.session_state['prod_name'],
        'description': st.session_state.get('current_quill_html', ''),      
        'short_description': short_html, 
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
        st.toast("Product Updated!")
    else:
        st.session_state.products.append(new_product)
        st.toast("Product Added!")

    clear_form()

# --- MAIN UI ---
cat_df, path_to_code, root_list = load_category_data()

with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("Reset All", type="primary"):
        st.session_state.products = []
        clear_form()
        st.rerun()

st.title("📦 Product Bulk Builder")

# --- 1. CATEGORY ---
st.header("1. Category Selection")
tab1, tab2 = st.tabs(["Browse Categories", "Search Categories"])
with tab1:
    c1, c2 = st.columns(2)
    with c1: root = st.selectbox("Department", ["Select"] + root_list, key="dept_sel")
    with c2: 
        filtered = sorted(cat_df[cat_df['root_category']==root]['category'].tolist()) if root != "Select" else []
        st.selectbox("Specific Category", [DEFAULT_CATEGORY_PATH] + filtered, key="cat_selector_a")
with tab2:
    search = st.text_input("Search by keyword")
    results = sorted(cat_df[cat_df['category'].str.contains(search, case=False, na=False)]['category'].tolist()) if search else []
    st.selectbox("Search Results", [DEFAULT_CATEGORY_PATH] + results, key="cat_selector_b")

# --- 2. DETAILS ---
st.markdown("---")
st.header("2. Product Content")

c_n, c_b = st.columns([3, 1])
c_n.text_input("Product Name", key='prod_name')
c_b.text_input("Brand", key='prod_brand')

col_c, col_m = st.columns(2)
col_c.text_input("Color", key='prod_color')
col_m.text_input("Main Material", key='prod_material')

st.subheader("Full Description (Quill)")
st.session_state['current_quill_html'] = st_quill(
    value=st.session_state.quill_content, 
    html=True, 
    key=f"quill_{st.session_state.quill_key}"
)

st.subheader("Short Description (Auto-Bullets)")
st.text_area("Paste features (one per line)", key='prod_short', height=150, help="Each line will be saved as a <li> item.")

st.subheader("What's in the Box")
st.text_area("Contents (one per line)", key='prod_in_box', height=100)

st.markdown("---")
c_c1, c_c2 = st.columns(2)
c_c1.text_input("Custom Column Name", key='custom_col_name')
c_c2.text_input("Custom Value", key='custom_col_val')

if st.session_state.edit_index is not None:
    st.button("Update Product", on_click=save_product_callback, type="primary")
    st.button("Cancel Edit", on_click=clear_form)
else:
    st.button("Add to List", on_click=save_product_callback, type="primary")

# --- 3. OUTPUT ---
if st.session_state.products:
    st.markdown("---")
    st.header("3. Product List & Export")
    
    # Management Table
    for i, p in enumerate(st.session_state.products):
        col1, col2, col3, col4 = st.columns([4, 2, 1, 1])
        col1.write(f"**{p['name']}**")
        col2.code(p['categories'])
        col3.button("Edit", key=f"e_{i}", on_click=load_product_for_edit, args=(i,))
        col4.button("Delete", key=f"d_{i}", on_click=delete_product, args=(i,))
    
    st.markdown("---")
    # CSV Generation
    standard_cols = [
        'sku_supplier_config', 'seller_sku', 'name', 'brand', 'categories', 
        'product_weight', 'package_type', 'package_quantities', 'variation', 
        'price', 'tax_class', 'cost', 'color', 'main_material', 
        'description', 'short_description', 'package_content', 'supplier', 'shipment_type'
    ]
    df_final = pd.DataFrame(st.session_state.products)
    
    # Ensure all template columns exist and order them
    for col in standard_cols:
        if col not in df_final.columns: df_final[col] = ""
    
    custom_cols = [c for c in df_final.columns if c not in standard_cols]
    df_final = df_final[standard_cols + custom_cols]

    csv_data = df_final.to_csv(index=False)
    b64 = base64.b64encode(csv_data.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="products_export.csv" style="text-decoration:none;"><button style="background-color:#ff4b4b; color:white; border:none; padding:10px 20px; border-radius:5px; cursor:pointer;">Download CSV File</button></a>'
    st.markdown(href, unsafe_allow_html=True)
    
    with st.expander("Preview Data"):
        st.dataframe(df_final)
