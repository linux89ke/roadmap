import streamlit as st
import requests
import pandas as pd
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin

st.title("Jumia Category Scraper - Warranty Extractor")

# User input
category_url = st.text_input("Enter Jumia category URL:")

if st.button("Scrape Category"):
    if not category_url:
        st.error("Please enter a valid Jumia category URL")
    else:
        all_products = []
        page = 1

        progress_bar = st.progress(0)
        status_text = st.empty()
        total_scraped = 0

        while True:
            paged_url = category_url
            if "?page=" in category_url:
                paged_url = category_url.split("?page=")[0] + f"?page={page}"
            elif category_url.endswith("/"):
                paged_url = f"{category_url}?page={page}"
            else:
                paged_url = f"{category_url}&page={page}" if "?" in category_url else f"{category_url}?page={page}"

            status_text.text(f"Fetching page {page}...")

            try:
                r = requests.get(paged_url, timeout=10)
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
                if not script_tag:
                    break

                data = json.loads(script_tag.string)
                products = data.get("props", {}).get("pageProps", {}).get("initialData", {}).get("products", [])

                if not products:
                    break  # no more products

                for product in products:
                    name = product.get("name", "")
                    sku = product.get("sku", "")
                    url = urljoin("https://www.jumia.co.ke", product.get("url", ""))
                    seller = product.get("brand", {}).get("name", "Not indicated")
                    price = product.get("price", {}).get("raw", "Not indicated")

                    # Warranty fields
                    warranty_title = "Not indicated"
                    warranty_specs = "Not indicated"
                    warranty_address = "Not indicated"

                    # Check in title
                    if "warranty" in name.lower():
                        warranty_title = name

                    # Check in product specs (if available in JSON)
                    specs = product.get("features", [])
                    for feature in specs:
                        if "warranty" in feature.get("name", "").lower():
                            warranty_specs = feature.get("value", "Not indicated")
                        if "address" in feature.get("name", "").lower():
                            warranty_address = feature.get("value", "Not indicated")

                    all_products.append({
                        "SKU": sku,
                        "Product Name": name,
                        "Product URL": url,
                        "Seller": seller,
                        "Price": price,
                        "Warranty in Title": warranty_title,
                        "Warranty (Specs)": warranty_specs,
                        "Warranty Address": warranty_address
                    })

                total_scraped += len(products)
                progress_bar.progress(min(total_scraped / 200, 1.0))  # Assuming ~200 max for bar

                page += 1

            except Exception as e:
                st.error(f"Error: {e}")
                break

        if all_products:
            df = pd.DataFrame(all_products)
            st.success(f"Scraped {len(df)} products!")
            st.dataframe(df)

            # Save to Excel
            excel_file = "jumia_products.xlsx"
            df.to_excel(excel_file, index=False)
            with open(excel_file, "rb") as f:
                st.download_button(
                    label="Download Excel File",
                    data=f,
                    file_name="jumia_products.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("No products found.")
