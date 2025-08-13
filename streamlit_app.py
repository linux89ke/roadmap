import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time

# ---------------------------
# Helper function to get all product URLs from category
# ---------------------------
def get_product_links(category_url):
    product_links = []
    page = 1

    while True:
        url = f"{category_url}?page={page}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code != 200:
            break

        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select("a.core")  # Jumia product links

        if not items:
            break

        for a in items:
            href = a.get("href")
            if href and href.startswith("/"):
                product_links.append("https://www.jumia.co.ke" + href)

        page += 1
        time.sleep(1)  # Be polite to server

    return list(set(product_links))  # Remove duplicates

# ---------------------------
# Helper function to scrape product details
# ---------------------------
def scrape_product(url):
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")

        # Product title
        title_tag = soup.select_one("h1")
        title = title_tag.get_text(strip=True) if title_tag else "Not indicated"

        # Price
        price_tag = soup.select_one("span.-b")
        price = price_tag.get_text(strip=True) if price_tag else "Not indicated"

        # Seller
        seller_tag = soup.select_one('a.-mhm') or soup.select_one('div.-pvxs')
        seller = seller_tag.get_text(strip=True) if seller_tag else "Not indicated"

        # SKU (often in the "specs" section)
        sku = "Not indicated"
        for li in soup.select("li"):
            if "SKU" in li.get_text():
                sku = li.get_text(strip=True).split(":")[-1].strip()
                break

        # Warranty in title
        warranty_in_title = "Not indicated"
        match = re.search(r"\b\d+\s?YR\S*\b", title.upper())
        if match:
            warranty_in_title = match.group(0)

        # Warranty (Specs) + Address
        warranty_specs = "Not indicated"
        warranty_address = "Not indicated"

        for li in soup.select("li"):
            text = li.get_text(strip=True)
            if text.lower().startswith("warranty"):
                warranty_specs = text.split(":")[-1].strip()
            if "Warranty Address" in text:
                warranty_address = text.split(":")[-1].strip()

        return {
            "SKU": sku,
            "Product Name": title,
            "Product URL": url,
            "Seller": seller,
            "Price": price,
            "Warranty in Title": warranty_in_title,
            "Warranty (Specs)": warranty_specs,
            "Warranty Address": warranty_address
        }

    except Exception as e:
        return {
            "SKU": "Error",
            "Product Name": f"Error: {e}",
            "Product URL": url,
            "Seller": "Error",
            "Price": "Error",
            "Warranty in Title": "Error",
            "Warranty (Specs)": "Error",
            "Warranty Address": "Error"
        }

# ---------------------------
# Streamlit UI
# ---------------------------
st.title("Jumia Category Scraper")
category_url = st.text_input("Enter Jumia category URL:")

if st.button("Scrape Category"):
    if category_url:
        st.write("Fetching product links...")
        links = get_product_links(category_url)
        st.write(f"Found {len(links)} products.")

        results = []
        for link in links:
            st.write(f"Scraping: {link}")
            details = scrape_product(link)
            results.append(details)
            time.sleep(1)  # Delay to avoid blocking

        df = pd.DataFrame(results)
        st.dataframe(df)

        # Download button
        excel_file = "jumia_scrape_results.xlsx"
        df.to_excel(excel_file, index=False)
        with open(excel_file, "rb") as f:
            st.download_button("Download Excel", f, file_name=excel_file)

    else:
        st.warning("Please enter a valid category URL.")

