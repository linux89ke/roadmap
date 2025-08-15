import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests_html import HTMLSession
import time

st.set_page_config(page_title="Product Data Scraper", layout="wide")
st.title("Product Data Scraper")

# Input for category link
category_url = st.text_input("Enter category URL")

def scrape_product_page(url):
    """Scrape individual product page for seller, warranty, SKU, and price."""
    session = HTMLSession()
    r = session.get(url)
    try:
        r.html.render(timeout=20, sleep=2)
    except:
        pass  # fallback if JS rendering fails
    
    soup = BeautifulSoup(r.html.html, "lxml")

    # Product title
    title_elem = soup.find("h1")
    title = title_elem.get_text(strip=True) if title_elem else "N/A"

    # Warranty (search in multiple places)
    warranty = "N/A"
    for text_elem in soup.find_all(string=True):
        if "warranty" in text_elem.lower():
            warranty = text_elem.strip()
            break

    # Seller (including JS-rendered)
    seller_elem = soup.select_one("a.-m.-upp.-hov-or5.-hov-mt1.-cl-nl, div.seller a")
    seller = seller_elem.get_text(strip=True) if seller_elem else "N/A"

    # SKU
    sku = "N/A"
    sku_elem = soup.find(string=lambda t: "SKU" in t)
    if sku_elem:
        sku = sku_elem.strip().split(":")[-1].strip()

    # Price
    price_elem = soup.select_one("span.-b.-ubpt.-tal.-fs24")
    price = price_elem.get_text(strip=True) if price_elem else "N/A"

    return {
        "URL": url,
        "Title": title,
        "Warranty": warranty,
        "Seller": seller,
        "SKU": sku,
        "Price": price
    }

def scrape_category(url):
    """Scrape all product links from category page."""
    products = []
    page = 1

    while True:
        page_url = f"{url}?page={page}"
        resp = requests.get(page_url, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            break
        
        soup = BeautifulSoup(resp.text, "lxml")
        product_links = [
            "https://www.jumia.co.ke" + a["href"]
            for a in soup.select("a.core") if a.get("href")
        ]

        if not product_links:
            break

        for link in product_links:
            try:
                products.append(scrape_product_page(link))
            except Exception as e:
                products.append({"URL": link, "Error": str(e)})
        
        page += 1
        time.sleep(1)  # avoid hammering server
    
    return products

if st.button("Scrape Data"):
    if not category_url:
        st.warning("Please enter a category link.")
    else:
        st.info("Scraping in progress... please wait.")
        data = scrape_category(category_url)
        df = pd.DataFrame(data)
        st.dataframe(df)
        df.to_excel("scraped_data.xlsx", index=False)
        st.download_button("Download Excel", open("scraped_data.xlsx", "rb"), "scraped_data.xlsx")
