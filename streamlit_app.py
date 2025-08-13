import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
}

def get_product_links(category_url):
    links = []
    page = 1
    while True:
        url = f"{category_url}?page={page}"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "lxml")
        product_cards = soup.select("a.core")
        if not product_cards:
            break
        for a in product_cards:
            href = a.get("href")
            if href and href.startswith("/"):
                links.append("https://www.jumia.co.ke" + href.split("#")[0])
        page += 1
        time.sleep(1)
    return list(dict.fromkeys(links))

def scrape_product(url):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")

        name = soup.select_one("h1").get_text(strip=True) if soup.select_one("h1") else "Not indicated"

        # SKU
        sku = "Not indicated"
        sku_tag = soup.find(string=re.compile("SKU", re.I))
        if sku_tag:
            td = sku_tag.find_next("td")
            if td:
                sku = td.get_text(strip=True)

        # Seller
        seller = "Not indicated"
        seller_tag = soup.find("a", {"data-testid": "seller-name"})
        if seller_tag:
            seller = seller_tag.get_text(strip=True)

        # Price
        price = "Not indicated"
        price_tag = soup.select_one("span.-b")
        if price_tag:
            price = price_tag.get_text(strip=True)

        # Warranty in title
        warranty_title = "Not indicated"
        if re.search(r"\b\d+\s?yr|\bwarranty", name, re.I):
            warranty_title = name

        # Warranty in specs
        warranty_specs = "Not indicated"
        warranty_address = "Not indicated"
        for tr in soup.select("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and "warranty" in th.get_text(strip=True).lower():
                warranty_specs = td.get_text(strip=True) if td else "Not indicated"
            if th and "warranty address" in th.get_text(strip=True).lower():
                warranty_address = td.get_text(strip=True) if td else "Not indicated"

        return {
            "Product Name": name,
            "SKU": sku,
            "Seller": seller,
            "Price": price,
            "Warranty in Title": warranty_title,
            "Warranty (Specs)": warranty_specs,
            "Warranty Address": warranty_address,
            "Product URL": url
        }
    except Exception as e:
        return {"Product Name": f"Error: {e}", "SKU": "Error", "Seller": "Error",
                "Price": "Error", "Warranty in Title": "Error",
                "Warranty (Specs)": "Error", "Warranty Address": "Error", "Product URL": url}

# Streamlit UI
st.title("Jumia Category Warranty Scraper")

category_url = st.text_input("Enter Jumia category URL:")

if st.button("Scrape Category") and category_url:
    st.write("Collecting product links...")
    product_links = get_product_links(category_url)
    st.success(f"Found {len(product_links)} products.")

    results = []
    progress = st.progress(0)
    for i, link in enumerate(product_links, start=1):
        details = scrape_product(link)
        results.append(details)
        progress.progress(i / len(product_links))
        time.sleep(1)  # avoid hammering

    df = pd.DataFrame(results)
    st.dataframe(df)

    # Excel export
    out_file = "jumia_products.xlsx"
    df.to_excel(out_file, index=False)
    with open(out_file, "rb") as f:
        st.download_button("Download Excel", f, file_name=out_file)
