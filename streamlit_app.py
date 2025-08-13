import streamlit as st
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
import json
import time
from io import BytesIO
import re
from urllib.parse import urljoin

# --- Streamlit UI ---
st.set_page_config(page_title="Jumia Category Warranty Scraper", layout="wide")
st.title("Jumia Kenya Category Warranty Scraper 🛒")
st.caption("Enter a Jumia Kenya category URL to extract product details including warranty.")

category_url = st.text_input("Enter Jumia category URL:")
start = st.button("Scrape Category")

scraper = cloudscraper.create_scraper(
    browser={'custom': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                        'Chrome/115.0.0.0 Safari/537.36'}
)

# --- Helper Functions ---

def get_product_links(category_url):
    """Collect all product links from category pages"""
    links = []
    page = 1
    while True:
        url = f"{category_url}?page={page}"
        resp = scraper.get(url)
        if resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        product_tags = soup.select("article.prd a.core")
        if not product_tags:
            break
        for tag in product_tags:
            href = tag.get("href")
            if href:
                full_url = urljoin("https://www.jumia.co.ke", href.split("#")[0])
                if full_url not in links:
                    links.append(full_url)
        page += 1
        time.sleep(0.5)
    return links

def parse_product(url):
    """Extract product info including warranty from LD-JSON and page content"""
    try:
        r = scraper.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # LD-JSON parsing
        script = soup.find("script", {"type": "application/ld+json"})
        data = json.loads(script.string) if script else {}
        product = data.get("mainEntity", {})
        name = product.get("name", "Not indicated")
        sku = product.get("sku", "Not indicated")
        price = product.get("offers", {}).get("price", "Not indicated")
        seller = product.get("offers", {}).get("seller", {}).get("name", "Not indicated")
        # Warranty in title
        warranty_title = "Yes" if re.search(r"(warranty|\b\d+\s?(yr|yrs|year|years)\b)", name, re.I) else "Not indicated"
        # Warranty in specs & address
        warranty_specs = "Not indicated"
        warranty_address = "Not indicated"
        # Bullet lists / tables
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
        return {
            "Product Title": name,
            "SKU": sku,
            "Seller": seller,
            "Price": price,
            "Warranty Title": warranty_title,
            "Warranty (Specs)": warranty_specs,
            "Warranty Address": warranty_address,
            "Product URL": url
        }
    except Exception as e:
        return {
            "Product Title": "Error fetching page",
            "SKU": "Not indicated",
            "Seller": "Not indicated",
            "Price": "Not indicated",
            "Warranty Title": "Not indicated",
            "Warranty (Specs)": "Not indicated",
            "Warranty Address": "Not indicated",
            "Product URL": url
        }

# --- Main Scraping ---
if start and category_url:
    st.info("Collecting product links...")
    links = get_product_links(category_url)
    if not links:
        st.warning("No products found. Please check the category URL.")
        st.stop()
    st.success(f"Found {len(links)} products. Scraping details now...")

    results = []
    prog_bar = st.progress(0)
    for idx, link in enumerate(links, start=1):
        result = parse_product(link)
        results.append(result)
        prog_bar.progress(idx / len(links))
        time.sleep(0.2)

    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True)

    # Download buttons
    @st.cache_data
    def to_excel_bytes(frame: pd.DataFrame) -> bytes:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            frame.to_excel(writer, index=False, sheet_name="Jumia_Products")
        return output.getvalue()

    st.download_button(
        "📥 Download Excel",
        data=to_excel_bytes(df),
        file_name="jumia_warranty_products.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

