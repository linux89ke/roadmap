import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re

st.title("Jumia Warranty Scraper")

category_url = st.text_input("Enter Jumia category URL:")

if st.button("Scrape"):
    if not category_url:
        st.error("Please enter a category URL.")
    else:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        }

        all_products = []
        page_num = 1
        st.write("Fetching product links...")

        # Step 1: Get all product links from the category
        while True:
            url = f"{category_url}?page={page_num}"
            res = requests.get(url, headers=headers)
            soup = BeautifulSoup(res.text, "lxml")
            product_cards = soup.select("a.core")

            if not product_cards:
                break

            for card in product_cards:
                link = "https://www.jumia.co.ke" + card.get("href").split("#")[0]
                all_products.append(link)

            page_num += 1
            time.sleep(1)

        all_products = list(dict.fromkeys(all_products))  # remove duplicates
        st.success(f"Found {len(all_products)} products.")

        if not all_products:
            st.stop()

        # Step 2: Visit each product page
        product_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, product_url in enumerate(all_products):
            try:
                r = requests.get(product_url, headers=headers)
                soup = BeautifulSoup(r.text, "lxml")

                # Product name
                name = soup.select_one("h1").get_text(strip=True) if soup.select_one("h1") else "Not indicated"

                # SKU
                sku = "Not indicated"
                sku_tag = soup.find(text=re.compile("SKU"))
                if sku_tag:
                    sku_el = sku_tag.find_next("td")
                    if sku_el:
                        sku = sku_el.get_text(strip=True)

                # Seller
                seller = "Not indicated"
                seller_tag = soup.find("a", {"data-testid": "seller-name"})
                if seller_tag:
                    seller = seller_tag.get_text(strip=True)

                # Warranty in title
                warranty_title = "Not indicated"
                if "warranty" in name.lower():
                    warranty_title = name

                # Warranty in specs
                warranty_specs = "Not indicated"
                warranty_tag = soup.find(text=re.compile("Warranty", re.I))
                if warranty_tag:
                    warranty_el = warranty_tag.find_next("td")
                    if warranty_el:
                        warranty_specs = warranty_el.get_text(strip=True)

                # Warranty address
                warranty_address = "Not indicated"
                warranty_address_tag = soup.find(text=re.compile("Warranty Address", re.I))
                if warranty_address_tag:
                    address_el = warranty_address_tag.find_next("td")
                    if address_el:
                        warranty_address = address_el.get_text(strip=True)

                product_data.append({
                    "Product Name": name,
                    "SKU": sku,
                    "Seller": seller,
                    "Warranty (Title)": warranty_title,
                    "Warranty (Specs)": warranty_specs,
                    "Warranty Address": warranty_address,
                    "Product URL": product_url
                })

            except Exception as e:
                st.write(f"Error scraping {product_url}: {e}")

            # Update progress
            progress_bar.progress((idx + 1) / len(all_products))
            status_text.text(f"Processed {idx + 1} of {len(all_products)} products")

            time.sleep(1)

        # Step 3: Export to Excel
        df = pd.DataFrame(product_data)
        output_file = "jumia_warranty_data.xlsx"
        df.to_excel(output_file, index=False)

        st.success("Scraping complete!")
        st.download_button("Download Excel", data=open(output_file, "rb"), file_name="jumia_warranty_data.xlsx")
