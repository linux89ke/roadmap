import streamlit as st
import requests
import pandas as pd
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
import re
import time
import json

BASE_URL = "https://www.jumia.co.ke"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json",
}

MAX_PAGES = 200
DELAY_BETWEEN_PAGE_FETCH = (0.5, 1.0)
DELAY_BETWEEN_PRODUCT_FETCH = (0.1, 0.3)

def get_category_code(url):
    # Example: https://www.jumia.co.ke/smart-tvs-2282/ -> 2282
    parts = url.rstrip("/").split("-")
    for part in reversed(parts):
        if part.isdigit():
            return part
    return None

def fetch_api_products(category_code, page=1):
    api_url = f"https://www.jumia.co.ke/api/catalog/?category={category_code}&page={page}"
    resp = requests.get(api_url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except json.JSONDecodeError:
        return None

def parse_product_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
    except:
        return "Not indicated", "Not indicated"

    warranty_specs = "Not indicated"
    warranty_address = "Not indicated"

    # Look in tables
    for tr in soup.select("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th:
            key = th.get_text(strip=True).lower()
            val = td.get_text(strip=True) if td else "Not indicated"
            if "warranty address" in key:
                warranty_address = val
            elif "warranty" in key and "address" not in key:
                warranty_specs = val

    # Also check bullet lists
    for li in soup.select("div.-pvs ul li"):
        raw = li.get_text(" ", strip=True)
        parts = raw.split(":", 1)
        if len(parts) == 2:
            key = parts[0].strip().lower()
            val = parts[1].strip() or "Not indicated"
            if "warranty address" in key:
                warranty_address = val
            elif "warranty" in key and "address" not in key:
                warranty_specs = val

    return warranty_specs, warranty_address

st.set_page_config(page_title="Jumia Kenya Warranty Scraper", layout="wide")
st.title("Jumia Kenya Warranty Scraper 🛒")
st.caption("Enter a Jumia Kenya category URL and extract product details including warranty.")

category_url = st.text_input("Enter Jumia category URL:")
start = st.button("Scrape Category")

if start:
    category_code = get_category_code(category_url)
    if not category_code:
        st.error("Could not extract category code from URL. Make sure it's a valid Jumia Kenya category URL.")
        st.stop()

    st.subheader("Step 1: Collecting product links")
    product_links = []
    page = 1
    progress_text = st.empty()
    while page <= MAX_PAGES:
        progress_text.text(f"Fetching API page {page} ...")
        data = fetch_api_products(category_code, page)
        if not data or "products" not in data or not data["products"]:
            break
        for p in data["products"]:
            url = BASE_URL + p.get("url", "")
            product_links.append((url, p))
        page += 1
        time.sleep(DELAY_BETWEEN_PAGE_FETCH[0] + (DELAY_BETWEEN_PAGE_FETCH[1]-DELAY_BETWEEN_PAGE_FETCH[0])*page/100)

    st.success(f"Found {len(product_links)} products.")

    if not product_links:
        st.warning("No products found. Exiting.")
        st.stop()

    st.subheader("Step 2: Scraping product pages")
    results = []
    prog_bar = st.progress(0)
    status_text = st.empty()

    for idx, (url, pdata) in enumerate(product_links, start=1):
        status_text.text(f"Processing {idx}/{len(product_links)}: {url}")
        warranty_title = pdata.get("name") if re.search(r"(warranty|\b\d+\s?(yr|yrs|year|years)\b)", pdata.get("name",""), re.I) else "Not indicated"
        sku = pdata.get("sku", "Not indicated")
        seller = pdata.get("seller", {}).get("name", "Not indicated")
        price = pdata.get("price", {}).get("raw", "Not indicated")
        warranty_specs, warranty_address = parse_product_page(url)
        results.append({
            "Product Title": pdata.get("name"),
            "SKU": sku,
            "Seller": seller,
            "Price": price,
            "Warranty Title": warranty_title,
            "Warranty (Specs)": warranty_specs,
            "Warranty Address": warranty_address,
            "Product URL": url
        })
        prog_bar.progress(idx / len(product_links))
        time.sleep(DELAY_BETWEEN_PRODUCT_FETCH[0] + (DELAY_BETWEEN_PRODUCT_FETCH[1]-DELAY_BETWEEN_PRODUCT_FETCH[0])*idx/100)

    st.success("Scraping complete!")

    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True)

    @st.cache_data
    def to_excel_bytes(frame: pd.DataFrame) -> bytes:
        from io import BytesIO
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            frame.to_excel(writer, index=False, sheet_name="Jumia_Products")
        return buf.getvalue()

    st.download_button(
        "📥 Download Excel",
        data=to_excel_bytes(df),
        file_name="jumia_warranty_products.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
