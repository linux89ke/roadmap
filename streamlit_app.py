import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

st.title("Jumia Category Warranty Scraper")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
}

def get_product_links(category_url):
    links = []
    page = 1
    while True:
        url = f"{category_url}?page={page}"
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.text, "lxml")
        cards = soup.select("a.core")
        if not cards:
            break
        for a in cards:
            href = a.get("href")
            if href:
                links.append("https://www.jumia.co.ke" + href.split("#")[0])
        page += 1
        time.sleep(1)
    return list(dict.fromkeys(links))

def scrape_product(url):
    try:
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.text, "lxml")

        # Title
        title = soup.select_one("h1")
        title = title.get_text(strip=True) if title else "Not indicated"

        # SKU
        sku = "Not indicated"
        sku_tag = soup.find(text=re.compile("SKU", re.I))
        if sku_tag and sku_tag.find_next("td"):
            sku = sku_tag.find_next("td").get_text(strip=True)

        # Seller
        seller = "Not indicated"
        seller_tag = soup.find("a", {"data-testid": "seller-name"})
        if seller_tag:
            seller = seller_tag.get_text(strip=True)

        # Warranty in title
        warranty_title = "Not indicated"
        if re.search(r"warranty", title, re.I):
            warranty_title = title

        # Warranty in specs
        warranty_specs = "Not indicated"
        warranty_address = "Not indicated"
        rows = soup.find_all("tr")
        for tr in rows:
            th = tr.find("th")
            td = tr.find("td")
            if th and "warranty" in th.get_text(strip=True).lower():
                warranty_specs = td.get_text(strip=True) if td else "Not indicated"
            if th and "address" in th.get_text(strip=True).lower():
                warranty_address = td.get_text(strip=True) if td else "Not indicated"

        return {
            "SKU": sku,
            "Product Name": title,
            "Product URL": url,
            "Seller": seller,
            "Warranty in Title": warranty_title,
            "Warranty (Specs)": warranty_specs,
            "Warranty Address": warranty_address
        }
    except Exception as e:
        return {"SKU": "Error", "Product Name": f"Error: {e}", "Product URL": url,
                "Seller": "Error", "Warranty in Title": "Error", "Warranty (Specs)": "Error", "Warranty Address": "Error"}

if st.button("Scrape") and category_url := st.text_input("Enter Jumia category URL:"):
    st.write("Collecting product links...")
    links = get_product_links(category_url)
    st.success(f"Found {len(links)} products.")

    data = []
    progress = st.progress(0)
    for i, link in enumerate(links):
        details = scrape_product(link)
        data.append(details)
        progress.progress((i + 1) / len(links))
        time.sleep(1)

    df = pd.DataFrame(data)
    st.dataframe(df)

    excel_file = "jumia_products.xlsx"
    df.to_excel(excel_file, index=False)
    with open(excel_file, "rb") as f:
        st.download_button("Download Excel", f, file_name="jumia_products.xlsx")
