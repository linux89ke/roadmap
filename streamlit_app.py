import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from requests_html import HTMLSession
import concurrent.futures
import time

st.set_page_config(page_title="Product Data Scraper", layout="wide")
st.title("Product Data Scraper")

# Input for category link
category_url = st.text_input("Enter category URL")

session = HTMLSession()

def scrape_product_page(url):
    """Scrape individual product page for seller, warranty, SKU, and price."""
    r = session.get(url)
    try:
        r.html.render(timeout=20, sleep=2)
    except:
        pass
    
    soup = BeautifulSoup(r.html.html, "lxml")

    title_elem = soup.find("h1")
    title = title_elem.get_text(strip=True) if title_elem else "N/A"

    warranty = "N/A"
    for text_elem in soup.find_all(string=True):
        if "warranty" in text_elem.lower():
            warranty = text_elem.strip()
            break

    seller_elem = soup.select_one("a.-m.-upp.-hov-or5.-hov-mt1.-cl-nl, div.seller a")
    seller = seller_elem.get_text(strip=True) if seller_elem else "N/A"

    sku = "N/A"
    sku_elem = soup.find(string=lambda t: "SKU" in t)
    if sku_elem:
        sku = sku_elem.strip().split(":")[-1].strip()

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
    """Scrape all product links from category page using JS rendering."""
    all_links = []
    page = 1

    while True:
        page_url = f"{url}&page={page}"
        r = session.get(page_url)
        try:
            r.html.render(timeout=20, sleep=2)
        except:
            pass

        soup = BeautifulSoup(r.html.html, "lxml")
        product_links = [
            "https://www.jumia.co.ke" + a["href"]
            for a in soup.select("a.core") if a.get("href")
        ]

        if not product_links:
            break

        all_links.extend(product_links)
        page += 1
        time.sleep(0.5)

    return all_links

if st.button("Scrape Data"):
    if not category_url:
        st.warning("Please enter a category link.")
    else:
        st.info("Scraping in progress... please wait.")

        links = scrape_category(category_url)
        st.write(f"Found {len(links)} products. Scraping details in parallel...")

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(scrape_product_page, url): url for url in links}
            for future in concurrent.futures.as_completed(future_to_url):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append({"URL": future_to_url[future], "Error": str(e)})

        df = pd.DataFrame(results)
        st.dataframe(df)
        df.to_excel("scraped_data.xlsx", index=False)
        st.download_button("Download Excel", open("scraped_data.xlsx", "rb"), "scraped_data.xlsx")
