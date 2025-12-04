import streamlit as st
import pandas as pd
import re
import base64
import os

# --- CONFIGURATION ---
FILE_NAME_XLSX = 'cats.xlsx'
FILE_NAME_CSV = 'cats.xlsx - Sheet1.csv' 
DEFAULT_BRAND = 'Generic'
DEFAULT_COLOR = ''
DEFAULT_MATERIAL = '-'
DEFAULT_CATEGORY_NAME = 'Select a Category'

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
    Loads category data and forces strict integer formatting with commas.
    Example: 110001001 -> "110,001,001"
    """
    df = pd.DataFrame()
    
    # 1. Attempt to load the file
    if os.path.exists(FILE_NAME_XLSX):
        try:
            # Read as object to prevent initial float conversion errors if possible
            df = pd.read_excel(FILE_NAME_XLSX, dtype={'categories': object})
        except Exception as e:
            st.error(f"Error reading Excel: {e}")
            return pd.DataFrame(), {}, [DEFAULT_CATEGORY_NAME]
    elif os.path.exists(FILE_NAME_CSV):
        try:
            # Read as object (string) to preserve text content
            df = pd.read_csv(FILE_NAME_CSV, dtype={'categories': object})
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return pd.DataFrame(), {}, [DEFAULT_CATEGORY_NAME]
    else:
        st.error(f"CRITICAL ERROR: Could not find '{FILE_NAME_XLSX}' or '{FILE_NAME_CSV}'.")
        return pd.DataFrame(), {}, [DEFAULT_CATEGORY_NAME]

    # 2. Process and Format Data
    if not df.empty:
        df['name'] = df['name'].astype(str).str.strip()
        
        # STRICT FORMATTER FUNCTION
        def format_code(val):
            try:
                # Step 1: Convert to string and clean (remove existing commas/spaces)
                s_val = str(val).replace(',', '').strip()
                
                # Step 2: Convert to float first (handles 110001001.0 or 1.1E+8)
                f_val = float(s_val)
                
                # Step 3: Format as Integer with Commas
                # {:,.0f} -> Comma separator, 0 decimal places
                return "{:,.0f}".format(f_val)
            except:
                # If it's not a number (e.g., text code), return as is
                return str(val)

        # Apply formatting to the column
        df['categories'] = df['categories'].apply(format_code)

        # Create Lookup Dictionary
        name_to_code = df.set_index('name')['categories'].to_dict()
        
        # Create Dropdown List
        category_names = [DEFAULT_CATEGORY_NAME] + df['name'].unique().tolist()
        
        return df, name_to_code, category_names
    
    return pd.DataFrame(), {}, [DEFAULT_CATEGORY_NAME]


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
        'categories', # This will now hold the formatted string "110,001,001"
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
            
    # Save as string (preserving the commas in the 'categories' column)
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
        # Retrieve the pre-formatted code (e.g., "110,001,001")
        final_code = name_to_code.get(selected_category_name, '')
        
        generated_sku = generate_sku_config(new_name)
        new_short_description_html = format_to_html_list(new_short_description_raw)
        
        new_product = {
            'name': new_name,
            'description': new_description,
            'short_description': new_short_description_html,
            'sku_supplier_config': generated_sku,
            'seller_sku': generated_sku,
            'package_content': new_name,
            'categories': final_code, # Use the correctly formatted code
            'brand': new_brand,
            'color': new_color,
            'main_material': new_material,
            **TEMPLATE_DATA
        }
        
        st.session_state.products.append(new_product)
        st.success(f"Added: {new_name} | Category Code: {final_code}")

# --- OUTPUT ---
st.header("2. Generated Product List")
if st.session_state.products:
    final_df = create_output_df(st.session_state.products)
    
    # Show preview
    st.dataframe(final_df[['name', 'categories', 'sku_supplier_config']].tail(5), use_container_width=True)
    
    # Download Link
    st.markdown(get_csv_download_link(final_df), unsafe_allow_html=True)
    
    if st.button("🗑️ Clear List"):
        st.session_state.products = []
        st.rerun()
else:
    st.info("Add a product to generate the CSV.")
