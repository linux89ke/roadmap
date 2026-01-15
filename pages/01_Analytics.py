import streamlit as st
import pandas as pd

st.set_page_config(page_title="Analytics", page_icon="📊")

st.title("📊 Analytics")

st.write("Welcome to the Analytics page! This is a new page in your Streamlit app.")

# Display summary of products from session state
if st.session_state.get('products'):
    products_df = pd.DataFrame(st.session_state.products)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Products", len(products_df))
    with col2:
        st.metric("Unique Categories", products_df['categories'].nunique())
    with col3:
        st.metric("Unique Brands", products_df['brand'].nunique())
    
    st.subheader("Products Summary")
    st.dataframe(products_df[['name', 'brand', 'categories']], use_container_width=True)
else:
    st.info("No products added yet. Go to the main page to add some!")
