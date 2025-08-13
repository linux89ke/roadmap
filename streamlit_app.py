import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from urllib.parse import urlparse
import time

# Helper: Get JSON API URL for a category
def get_category_api_url(category_url, page):
    parsed = urlparse(category_url)
    path_parts = parsed.path.strip("/").split("/")
    category_slug = path_parts[-1] if path_parts[-1] else path_parts[-2]
    return f"https://www.jumia.co.ke/catalog/?q=&page={page}&slug={category_slug}"

# Helper: Get warranty details from product page
def get_product_details(product_url):
    try:
        r = requests.get(product_url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Extract SKU
        sku_elem = soup.find("span", text=re.compile(r"SKU", re.I))
        sku = sku_elem.find_next("span").text.strip() if sku_elem else "Not indicated"

        # Extract Seller
        seller_elem = soup.find("a", {"class": re.compile("-mhs")})
        seller = seller_elem.text.strip() if seller_elem else "Not indicated"

        # Warranty in title
        title_elem = soup.find("h1")
        warranty_in_title = "Not indicated"
        if title_elem and re.search(r"warranty", title_elem.text, re.I):
            warranty_in_title = title_elem.text.strip()

        # Warranty in specs
        specs_warranty = "Not indicated"
        specs_section = soup.find_all("tr")
        for tr in specs_section:
            th = tr.find("th")
            td = tr.find("td")
            if th and "warranty" in th.text.lower():
                specs_warranty = td.text.strip() if td else "Not indicated"
                break

        # Warranty address (in delivery/returns section)
        warranty_address = "Not indicated"
        delivery_section = soup.find("div", text=re.compile("Warranty Address", re.I))
        if delivery_section:
            warranty_address = delivery_section.find_next("div").text.strip()

        return sku, seller, warranty_in_title, specs_warranty, warranty_address
    except Exception:
        return "Not indicated", "Not indicated", "Not indicated", "Not indicated", "Not indicated"

# Streamlit UI
st.title("Jumia Category Warranty Scraper")

category_url = st.text_input("Enter Jumia category URL:", "")

if st.button("Fetch Data") and category_url:
    st.write("Fetching product list...")

    all_products = []
    page = 1
    total_found = 0

    progress_bar = st.progress(0)
    while True:
        api_url = get_category_api_url(category_url, page)
        r = requests.get(api_url, timeout=10)
        data = r.json()

        products = data.get("products", [])
        if not products:
            break

        for prod in products:
            total_found += 1
            product_name = prod.get("name", "No name")
            product_url = "https://www.jumia.co.ke" + prod.get("url", "")
            price = prod.get("price", "N/A")

            sku, seller, warranty_title, warranty_specs, warranty_address = get_product_details(product_url)

            all_products.append({
                "SKU": sku,
                "Product Name": product_name,
                "Product URL": product_url,
                "Seller": seller,
                "Price": price,
                "Warranty in Title": warranty_title,
                "Warranty (Specs)": warranty_specs,
                "Warranty Address": warranty_address
            })

            progress_bar.progress(min(total_found / 100, 1.0))  # Rough progress

        page += 1
        time.sleep(1)

    if all_products:
        df = pd.DataFrame(all_products)
        st.dataframe(df)

        # Excel download
        excel_file = "jumia_warranty.xlsx"
        df.to_excel(excel_file, index=False)
        with open(excel_file, "rb") as f:
            st.download_button("Download Excel", f, file_name=excel_file)
    else:
        st.warning("No products found.")
