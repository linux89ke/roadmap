import streamlit as st
import pandas as pd
import re
import base64
import os

# --- CONFIGURATION ---
# Try to find the file automatically (supports .xlsx or .csv)
FILE_NAME_XLSX = 'cats.xlsx'
FILE_NAME_CSV = 'cats.xlsx - Sheet1.csv' 
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

@st.cache_data
def load_category_data():
    """
    Loads category data from Excel or CSV. 
    Uses caching so it only runs once per session (FAST).
    """
    df = pd.DataFrame()
    
    # 1. Try Loading Excel
    if os.path.exists(FILE_NAME_XLSX):
        try:
            df = pd.read_excel(FILE_NAME_XLSX)
        except Exception as e:
            st.error(f"Error reading Excel: {e}")
            return pd.DataFrame(), {}, {}, [DEFAULT_CATEGORY_NAME]
            
    # 2. Try Loading CSV (if Excel not found)
    elif os.path.exists(FILE_NAME_CSV):
        try:
            df = pd.read_csv(FILE_NAME_CSV)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return pd.DataFrame(), {}, {}, [DEFAULT_CATEGORY_NAME]
    else:
        st.error(f"CRITICAL ERROR: Could not find '{FILE_NAME_XLSX}' or '{FILE_NAME_CSV}'. Please add the file to the script folder.")
        return pd.DataFrame(), {}, {}, [DEFAULT_CATEGORY_NAME]

    # 3. Process Data
    if not df.empty:
        # Clean names
        df['name'] = df['name'].astype(str).str.strip()
        
        # Clean Categories Code (Handle Float/Scientific Notation)
        # Your file has numbers like 1.10E+16, we need to make them integers first
        def clean_code(val):
            try:
                # Convert float to int (removes decimals), then to string
                return str(int(float(val)))
            except:
                return str(val)

        df['categories'] = df['categories'].apply(clean_code)

        # Create dictionaries for fast lookup
        name_to_code = df.set_index('name')['categories'].to_dict()
        
        # Create list for dropdown
        category_names = [DEFAULT_CATEGORY_NAME] + df['name'].unique().tolist()
        
        return df, name_to_code, category_names
    
    return pd.DataFrame(), {}, [DEFAULT_CATEGORY_NAME]


def format_to_html_list(text):
    """Converts plain text bullet points into an HTML unordered list."""
    if not text: return ''
    lines = [line.strip() for line in text.split('\n')]
    list_items = [f'    <li>{line}</li>' for line in lines if line]
    if not list_items: return ''
    list_content = '\n'.join(list_items)
    return f'<ul>\n{list_content}\n    </ul>'


def generate_sku_config(name):
    """Generates sku based on the product name logic."""
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
    """Converts a list of product dictionaries into a final DataFrame."""
    columns = [
        'sku_supplier_config', 'seller_sku', 'name', 'brand', 
        'categories', # Final column name
        'product_weight', 'package_type', 'package_quantities', 
        'variation', 'price', 'tax_class', 'cost', 'color', 'main_material', 
        'description', 'short_description', 'package_content', 'supplier', 
        'shipment_type'
    ]
    df = pd.DataFrame(product_list, columns=columns)
    return df.fillna('', inplace=False)


def get_csv_download_link(df):
    """Generates a link to download the DataFrame as a CSV."""
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

# --- LOAD DATA (Runs once per session) ---
cat_df, name_to_code, category_names = load_category_data()

# --- INPUT FORM ---
st.header("1. Enter New Product Details")
with st.form(key='product_form'):
    col_name, col_brand = st.columns([3, 1])
    with col_name:
        new_name = st.text_input("Product Name", placeholder="e.g., 10PCS Refrigerator Bags")
    with col_brand:
        new_brand = st.text_input("Brand", value=DEFAULT_BRAND)

    # SEARCHABLE DROPDOWN
    # Streamlit handles the "Search" logic automatically within the box
    st.subheader("Category Selection")
    selected_category_name = st.selectbox("Select Category (Type to Search)", options=category_names)

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
    elif selected_category_name == DEFAULT_CATEGORY_NAME:
        st.error("Please select a Category.")
    else:
        # GET CODE & FORMAT IT
        raw_code = name_to_code.get(selected_category_name, '')
        
        # Logic: If it looks like a number, add commas (11000 -> 11,000)
        # Since we cleaned it to a string string in load_data, we can try int()
        try:
            formatted_code = f"{int(raw_code):,}"
        except:
            formatted_code = raw_code

        generated_sku = generate_sku_config(new_name)
        new_short_description_html = format_to_html_list(new_short_description_raw)
        
        new_product = {
            'name': new_name,
            'description': new_description,
            'short_description': new_short_description_html,
            'sku_supplier_config': generated_sku,
            'seller_sku': generated_sku,
            'package_content': new_name,
            'categories': formatted_code, # Use the formatted code
            'brand': new_brand,
            'color': new_color,
            'main_material': new_material,
            **TEMPLATE_DATA
        }
        
        st.session_state.products.append(new_product)
        st.success(f"Added: {new_name} | Cat: {formatted_code}")

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
