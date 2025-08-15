import streamlit as st
import pandas as pd
import requests
import cloudscraper
from bs4 import BeautifulSoup
from requests_html import HTMLSession
import json
import time

# --- Helper: Static HTML scrape ---
def scrape_static(url):
    scraper = cloudscraper.create_scraper()
    r = scraper.get(url, timeout=15)
    soup = BeautifulSoup(r.text, 'lxml')

    seller = None
    warranty = None

    # Try JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string.strip())
            if isinstance(data, dict):
                if "offers" in data and "seller" in data["offers"]:
                    seller = data["offers"]["seller"].get("name")
        except:
            pass

    # Try meta or inline
    if not seller:
        sold_by = soup.find(text=lambda t: t and "Sold by" in t)
        if sold_by and sold_by.parent:
            seller = sold_by.parent.get_text(strip=True).replace("Sold by", "").strip()

    # Warranty guesses
    warr_text = soup.find(text=lambda t: t and "Warranty" in t)
    if warr_text and warr_text.parent:
        warranty = warr_text.parent.get_text(strip=True)

    return seller, warranty

# --- Helper: JS-rendered scrape ---
def scrape_js(url):
    session = HTMLSession()
    r = session.get(url, timeout=20)
    r.html.render(timeout=30, sleep=2)
    html = r.html.html
    soup = BeautifulSoup(html, 'lxml')

    seller, warranty = None, None

    # Seller from JSON-LD after render
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string.strip())
            if isinstance(data, dict) and "offers" in data and "seller" in data["offers"]:
                seller = data["offers"]["seller"].get("name")
        except:
            pass

    # Seller fallback
    if not seller:
        sold_by = soup.find(text=lambda t: t and "Sold by" in t)
        if sold_by and sold_by.parent:
            seller = sold_by.parent.get_text(strip=True).replace("Sold by", "").strip()

    # Warranty
    warr_text = soup.find(text=lambda t: t and "Warranty" in t)
    if warr_text and warr_text.parent:
        warranty = warr_text.parent.get_text(strip=True)

    return seller, warranty

# --- Main scraping ---
def scrape_products(url_list):
    results = []
    for url in url_list:
        seller, warranty = scrape_static(url)

        # If missing seller or warranty, try JS
        if not seller or not warranty:
            try:
                js_seller, js_warranty = scrape_js(url)
                if not seller and js_seller:
                    seller = js_seller
                if not warranty and js_warranty:
                    warranty = js_warranty
            except Exception as e:
                print(f"JS scrape failed for {url}: {e}")

        results.append({
            "URL": url,
            "Seller": seller or "NONE",
            "Warranty": warranty or "NONE"
        })

        time.sleep(1)

    return pd.DataFrame(results)

# --- Streamlit UI ---
st.title("Product Warranty & Seller Scraper")

uploaded_file = st.file_uploader("Upload a CSV or Excel file with URLs", type=["csv", "xlsx"])

if uploaded_file:
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    urls = df.iloc[:, 0].dropna().tolist()
    st.write(f"Found {len(urls)} URLs to scrape.")

    if st.button("Start Scraping"):
        output_df = scrape_products(urls)
        st.dataframe(output_df)
        output_df.to_excel("output.xlsx", index=False)
        st.download_button("Download Excel", open("output.xlsx", "rb"), "results.xlsx")
