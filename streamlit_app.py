import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests_html import HTMLSession
import json
import re
import streamlit as st
from time import sleep
from random import uniform

# ----------------------------------
# Utility functions
# ----------------------------------
def get_jsonld_data(soup):
    """Extract JSON-LD data from page soup."""
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                yield data
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        yield item
        except Exception:
            continue

def extract_seller(soup):
    """Try multiple ways to get seller from static HTML."""
    # JSON-LD check
    for data in get_jsonld_data(soup):
        if "offers" in data:
            offers = data["offers"]
            if isinstance(offers, dict) and "seller" in offers:
                seller_name = offers["seller"].get("name")
                if seller_name:
                    return seller_name.strip(), "jsonld"

    # Look for 'Sold by' text
    sold_by = soup.find(text=re.compile(r"Sold by", re.I))
    if sold_by:
        link = sold_by.find_next("a")
        if link:
            return link.get_text(strip=True), "sold_by_html"

    # Check meta or table rows
    for label in soup.find_all(["td", "th"]):
        if re.search(r"Seller", label.get_text(), re.I):
            val_td = label.find_next("td")
            if val_td:
                return val_td.get_text(strip=True), "table_html"

    return None, None

def extract_warranty(soup):
    """Try multiple ways to get warranty from static HTML."""
    # Look for any element mentioning warranty
    warranty_elem = soup.find(text=re.compile(r"warranty", re.I))
    if warranty_elem:
        val = warranty_elem.strip()
        # Clean extra prefixes like 'Warranty: '
        val = re.sub(r"(?i)warranty[:\s]*", "", val)
        return val.strip(), "text_match"

    # Search in specs list
    for li in soup.select("li"):
        if re.search(r"warranty", li.get_text(), re.I):
            val = re.sub(r"(?i)warranty[:\s]*", "", li.get_text())
            return val.strip(), "specs_list"

    return None, None

def fetch_rendered_html(url):
    """Use requests-html to get fully rendered page."""
    session = HTMLSession()
    r = session.get(url)
    r.html.render(timeout=20, sleep=2)
    return BeautifulSoup(r.html.html, "lxml")

def get_product_info(url):
    """Scrape product info from URL with static + rendered fallback."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    r = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(r.text, "lxml")

    # Initial scrape
    seller, seller_src = extract_seller(soup)
    warranty, warranty_src = extract_warranty(soup)

    # Rendered fallback if needed
    if not seller or not warranty:
        try:
            rendered_soup = fetch_rendered_html(url)
            if not seller:
                seller, seller_src = extract_seller(rendered_soup)
            if not warranty:
                warranty, warranty_src = extract_warranty(rendered_soup)
        except Exception as e:
            print(f"Render failed for {url}: {e}")

    return {
        "url": url,
        "seller": seller or "",
        "seller_source": seller_src or "",
        "warranty": warranty or "",
        "warranty_source": warranty_src or ""
    }

# ----------------------------------
# Streamlit UI
# ----------------------------------
st.title("E-commerce Product Data Extractor")

site_url = st.text_input("Enter category or product page URL:")

uploaded_file = st.file_uploader("Or upload a CSV/Excel file with product URLs", type=["csv", "xlsx"])

if st.button("Run Scraper"):
    urls = []

    if site_url:
        urls.append(site_url.strip())

    if uploaded_file:
        if uploaded_file.name.endswith(".csv"):
            df_input = pd.read_csv(uploaded_file)
        else:
            df_input = pd.read_excel(uploaded_file)
        urls.extend(df_input.iloc[:, 0].dropna().tolist())

    if urls:
        results = []
        progress = st.progress(0)
        for idx, link in enumerate(urls):
            info = get_product_info(link)
            results.append(info)
            progress.progress((idx + 1) / len(urls))
            sleep(uniform(0.5, 1.5))  # polite delay

        df = pd.DataFrame(results)
        st.dataframe(df)
        st.download_button("Download Excel", data=df.to_excel(index=False), file_name="products.xlsx")
