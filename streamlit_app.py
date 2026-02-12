import streamlit as st
import pandas as pd
import re
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
    'variation': '-',   
    'price': 100000,
    'tax_class': 'Default',
    'cost': 1,          
    'supplier': 'MarketPlace forfeited items',
    'shipment_type': 'Own Warehouse',
    'supplier_simple': '-', 
    'supplier_duplicate': '', 
}

# --- INITIALIZE SESSION STATE ---
default_keys = [
    'prod_name', 'prod_brand', 'prod_color', 'prod_material', 
    'prod_in_box', 'prod_size', 'custom_col_name', 'custom_col_val',
    'prod_author', 'prod_binding' # Added for Books
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

# --- HELPER FUNCTIONS ---

def format_to_html_list(text):
    if not text: return ''
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines: return ''
    return f'<ul>{"".join([f"<li>{l}</li>" for l in lines])}</ul>'

def clear_form():
    for key in default_keys:
        st.session_state[key] = ""
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
    
    # Specifics
    st.session_state['prod_size'] = product.get('size', '') 
    st.session_state['prod_author'] = product.get('author', '') 
    st.session_state['prod_binding'] = product.get('binding', '') 
    
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

def create_output_df(product_list):
    standard_columns = [
        'sku_supplier_config', 'supplier_simple', 'seller_sku', 'name', 'brand', 'categories', 
        'product_weight', 'package_type', 'package_quantities', 
        'variation', 'price', 'tax_class', 'cost', 'color', 'main_material', 'size',
        'author', 'binding', 'description', 'short_description', 'package_content', 
        'supplier', 'supplier_duplicate', 'shipment_type'
    ]
    df = pd.DataFrame(product_list)
    for col in standard_columns:
        if col not in df.columns: df[col] = ""
    custom_columns = [c for c in df.columns if c not in standard_columns]
    return df[standard_columns + custom_columns].fillna('')

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
        'size': st.session_state.get('prod_size', ''), 
        'author': st.session_state.get('prod_author', ''),
        'binding': st.session_state.get('prod_binding', ''),
        **TEMPLATE_DATA
    }
    
    raw_supplier = new_product.get('supplier', '')
    new_product['supplier_duplicate'] = raw_supplier.replace(" ", "")

    if st.session_state['custom_col_name'] and st.session_state['custom_col_val']:
        new_product[st.session_state['custom_col_name']] = st.session_state['custom_col_val']

    if st.session_state.edit_index is not None:
        st.session_state.products[st.session_state.edit_index] = new_product
        st.toast("Product Updated")
    else:
        st.session_state.products.append(new_product)
        st.toast("Product Added")

    clear_form()

# --- UI ---
cat_df, path_to_code, root_list = load_category_data()

with st.sidebar:
    st.header("Options")
    if st.button("Reset Entire App", type="primary"):
        st.session_state.products = []
        clear_form()
        st.rerun()

st.title("Product Manager")

# --- 1. CATEGORY SELECTION ---
st.header("1. Find Category")
tab1, tab2 = st.tabs(["Browse by Department", "Global Search"])

selected_category_path = DEFAULT_CATEGORY_PATH
selected_root_check = "" 

with tab1:
    col_dept, col_cat = st.columns([1, 2])
    with col_dept:
        selected_root = st.selectbox("Step A: Choose Department", options=["Select Department"] + root_list, key='dept_selector')
    with col_cat:
        if selected_root and selected_root != "Select Department":
            filtered_paths = sorted(cat_df[cat_df['root_category'] == selected_root]['category'].dropna().unique().tolist())
            cat_sel_a = st.selectbox("Step B: Select Specific Category", options=[DEFAULT_CATEGORY_PATH] + filtered_paths, key='cat_selector_a')
            if cat_sel_a != DEFAULT_CATEGORY_PATH:
                selected_category_path = cat_sel_a
                selected_root_check = selected_root 
        else:
            st.selectbox("Step B: Select Specific Category", options=["First select a department"], disabled=True)

with tab2:
    search_query = st.text_input("Type a keyword", key='search_query')
    if search_query:
        search_results = cat_df[cat_df['category'].str.contains(search_query, case=False, na=False)]
        found_paths = sorted(search_results['category'].unique().tolist())
        if found_paths:
            cat_sel_b = st.selectbox(f"Found {len(found_paths)} results:", options=[DEFAULT_CATEGORY_PATH] + found_paths, key='cat_selector_b')
            if cat_sel_b != DEFAULT_CATEGORY_PATH:
                selected_category_path = cat_sel_b
                if not cat_df.empty:
                    row = cat_df[cat_df['category'] == cat_sel_b]
                    if not row.empty:
                        selected_root_check = row.iloc[0]['root_category']
        else:
            st.warning("No categories found.")

# --- CHECK FOR SPECIAL CATEGORIES ---
if selected_category_path != DEFAULT_CATEGORY_PATH:
    final_code = path_to_code.get(selected_category_path, '')
    st.success(f"Selected: {selected_category_path} (Code: {final_code})")
else:
    st.warning("Please select a category above.")


# --- DYNAMIC DEFAULTS BASED ON CATEGORY ---
current_brand_default = DEFAULT_BRAND
if selected_root_check == "Fashion":
    current_brand_default = "Fashion"
elif selected_root_check == "Books":
    current_brand_default = "Jumia Book"

# Apply default brand only if the field is empty or user hasn't typed a custom one yet
if not st.session_state['prod_brand'] or (st.session_state['prod_brand'] in [DEFAULT_BRAND, "Fashion", "Jumia Book"]):
    st.session_state['prod_brand'] = current_brand_default


# --- 2. PRODUCT DETAILS FORM ---
st.markdown("---")
if st.session_state.edit_index is not None:
    st.subheader(f"Editing Product #{st.session_state.edit_index + 1}")
else:
    st.header("2. Product Details")

c_name, c_brand = st.columns([3, 1])
c_name.text_input("Product Name", key='prod_name')
c_brand.text_input("Brand", key='prod_brand')

# --- DYNAMIC INPUT FIELDS ---
if selected_root_check == "Fashion":
    col_clr, col_mat, col_size = st.columns([1, 1, 1])
    col_clr.text_input("Color", key='prod_color')
    col_mat.text_input("Main Material", key='prod_material', value=DEFAULT_MATERIAL)
    col_size.text_input("Size", key='prod_size', placeholder="e.g., M, L, XL, 42")

elif selected_root_check == "Books":
    col_auth, col_bind = st.columns(2)
    col_auth.text_input("Author", key='prod_author')
    col_bind.selectbox("Binding", options=["-", "Paperback", "Hardcover", "Spiral Bound", "Board Book"], key='prod_binding')
    
    # Hide unrelated fields
    st.session_state['prod_color'] = ""
    st.session_state['prod_material'] = "-"
    st.session_state['prod_size'] = ""

else:
    # Standard Generic Item
    col_clr, col_mat = st.columns(2)
    col_clr.text_input("Color", key='prod_color')
    col_mat.text_input("Main Material", key='prod_material', value=DEFAULT_MATERIAL)


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

st.markdown("---")
c_c1, c_c2 = st.columns(2)
c_c1.text_input("Custom Column Name", key='custom_col_name')
c_c2.text_input("Custom Value", key='custom_col_val')

if st.session_state.edit_index is not None:
    st.button("Update Product", on_click=save_product_callback, type="primary")
    st.button("Cancel Edit", on_click=clear_form)
else:
    st.button("Add Product", on_click=save_product_callback, type="primary")

# --- 3. MANAGE & DOWNLOAD ---
if st.session_state.products:
    st.markdown("---")
    st.header("3. Manage and Download Data")
    
    st.write(f"Total Products: {len(st.session_state.products)}")

    for i, p in enumerate(st.session_state.products):
        with st.container():
            st.markdown("---")
            c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
            is_editing = (st.session_state.edit_index == i)
            name_display = f"Editing: {p['name']}" if is_editing else p['name']
            c1.write(f"**{name_display}**")
            c2.text(p['categories'])
            c3.button("Edit", key=f"e_{i}", on_click=load_product_for_edit, args=(i,))
            if c4.button("Delete", key=f"d_{i}"):
                st.session_state.products.pop(i)
                if st.session_state.edit_index == i: clear_form()
                st.rerun()

    final_df = create_output_df(st.session_state.products)
    
    # --- RENAME FOR EXPORT ONLY ---
    export_df = final_df.copy()
    export_columns = list(export_df.columns)
    # Rename 'supplier_duplicate' to 'supplier' -> results in two 'supplier' columns
    export_columns = ['supplier' if col == 'supplier_duplicate' else col for col in export_columns]
    export_df.columns = export_columns
    
    csv = export_df.to_csv(index=False).encode('utf-8')
    st.markdown("---")
    
    # GENERATE FILENAME
    first_name = st.session_state.products[0]['name'] if st.session_state.products else "Export"
    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', first_name).strip('_')
    final_filename = f"{clean_name}_warehouse_RTv.csv"
    
    st.download_button("Download Generated CSV File", data=csv, file_name=final_filename, mime="text/csv")
    
    with st.expander("View Raw Data Table"):
        st.dataframe(final_df, use_container_width=True)
else:
    st.info("No products added yet.")
