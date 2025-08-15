import streamlit as st
import pandas as pd
import re
import math
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests_html import HTMLSession

# ---------- SETTINGS ----------
HEADERS = {"User-Agent": "Mozilla/5.0"}
session = HTMLSession()

# ---------- HELPER: Get total pages ----------
def get_total_pages(category_url):
    r = requests.get(category_url, headers=HEADERS)
    soup = BeautifulSoup(r.text, "lxml")
    total_txt = soup.find("span", class_="total")
    if total_txt:
        try:
            total_products = int(re.sub(r"[^\d]", "", total_txt.text))
            return math.ceil(total_products / 40)  # 40 items per page
        except:
            return 1
    return 1

# ---------- HELPER: JS Render for Missing Data ----------
def scrape_with_js(url):
    try:
        r = session.get(url)
        r.html.render(timeout=20, sleep=2)
        seller_el = r.html.find('[data-testid="seller-name"]', first=True)
        warranty_el = r.html.find('[data-testid="warranty-title"]', first=True)

        seller = seller_el.text.strip() if seller_el else "Not indicated"
        warranty = warranty_el.text.strip() if warranty_el else "Not indicated"

        return seller, warranty
    except:
        return "Not indicated", "Not indicated"

# ---------- SCRAPE PRODUCT DETAILS ----------
def scrape_product_details(url):
    try:
        r = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(r.text, "lxml")

        title_el = soup.find("h1", class_="-fs20")
        title = title_el.text.strip() if title_el else "N/A"

        price_el = soup.find("span", class_="-b -ubpt -tal -fs24")
        price = price_el.text.strip() if price_el else "N/A"

        seller_el = soup.find("a", {"data-testid": "seller-name"})
        seller = seller_el.text.strip() if seller_el else "Not indicated"

        warranty_el = soup.find("p", {"data-testid": "warranty-title"})
        warranty = warranty_el.text.strip() if warranty_el else "Not indicated"

        sku_el = soup.find("span", {"class": "-pvxs"})
        sku = sku_el.text.strip() if sku_el else "N/A"

        # Fallback with JS if missing
        if seller == "Not indicated" or warranty == "Not indicated":
            js_seller, js_warranty = scrape_with_js(url)
            if seller == "Not indicated":
                seller = js_seller
            if warranty == "Not indicated":
                warranty = js_warranty

        return {
            "Product Name": title,
            "Price": price,
            "Seller": seller,
            "Warranty": warranty,
            "SKU": sku,
            "Link": url
        }
    except:
        return {
            "Product Name": "Error",
            "Price": "Error",
            "Seller": "Error",
            "Warranty": "Error",
            "SKU": "Error",
            "Link": url
        }

# ---------- GET PRODUCT LINKS FROM CATEGORY ----------
def get_product_links(category_url):
    links = []
    total_pages = get_total_pages(category_url)

    for page in range(1, total_pages + 1):
        paginated_url = f"{category_url}&page={page}" if "page=" not in category_url else re.sub(r"page=\d+", f"page={page}", category_url)
        r = requests.get(paginated_url, headers=HEADERS)
        soup = BeautifulSoup(r.text, "lxml")
        items = soup.find_all("a", class_="core")
        for item in items:
            link = item.get("href")
            if link:
                if not link.startswith("http"):
                    link = "https://www.jumia.co.ke" + link
                links.append(link)
    return list(set(links))

# ---------- STREAMLIT UI ----------
st.title("Product Data Scraper")

category_url = st.text_input("Enter category URL")

if st.button("Scrape Data"):
    if category_url.strip():
        st.write("Scraping in progress... please wait.")

        product_links = get_product_links(category_url)
        st.write(f"Found {len(product_links)} products. Scraping details in parallel...")

        data = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(scrape_product_details, url): url for url in product_links}
            for future in as_completed(futures):
                data.append(future.result())

        df = pd.DataFrame(data)
        st.dataframe(df)

        st.download_button("Download Excel", df.to_excel(index=False), "products.xlsx")
    else:
        st.warning("Please enter a valid category URL")
