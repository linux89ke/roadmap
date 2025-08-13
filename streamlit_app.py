import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from urllib.parse import urljoin, urlparse
import random

# --- Configuration ---

# Using a more comprehensive set of headers to better mimic a real browser
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "Sec-Ch-Ua": '"Not/A)Brand";v="99", "Google Chrome";v="115", "Chromium";v="115"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
}
BASE_URL = "https://www.jumia.co.ke"

# --- PROXY CONFIGURATION ---
# Replace these with your actual list of proxies from a provider.
# Format: "http://user:pass@host:port" or "http://host:port"
PROXIES = [
    # Example proxies (these will not work, replace them)
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8081",
]

def get_proxies():
    """Returns a dictionary for the requests library with a randomly chosen proxy."""
    if not PROXIES:
        return None
    proxy = random.choice(PROXIES)
    return {"http": proxy, "https": proxy}

def make_request(url, max_retries=3):
    """
    Makes a request using a rotating proxy and handles retries.
    """
    for attempt in range(max_retries):
        try:
            proxy_dict = get_proxies()
            response = requests.get(url, headers=HEADERS, proxies=proxy_dict, timeout=20)
            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                st.warning(f"Got 403 Forbidden. Retrying with a new proxy... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(2) # Wait before retrying
            else:
                st.warning(f"Request failed with status {response.status_code}. Retrying...")
        except requests.exceptions.ProxyError as e:
            st.warning(f"Proxy error: {e}. Retrying with a new proxy... (Attempt {attempt + 1}/{max_retries})")
        except requests.exceptions.RequestException as e:
            st.error(f"A network error occurred: {e}")
            break # Stop on other network errors
        time.sleep(1)
    return None


def get_product_links(category_url):
    """
    Crawls through category pages to collect unique product URLs.
    """
    links = set()
    page = 1
    st.write("🔎 Starting product link collection...")
    progress_text = st.empty()

    while True:
        paginated_url = f"{category_url}?page={page}"
        progress_text.text(f"Scanning page: {paginated_url}")

        r = make_request(paginated_url)
        if not r:
            st.error(f"Failed to fetch {paginated_url} after several retries.")
            break

        soup = BeautifulSoup(r.text, "lxml")
        product_cards = soup.select("article.prd > a.core")

        if not product_cards:
            st.write(f"No more products found on page {page}. Concluding link collection.")
            break

        for card in product_cards:
            href = card.get("href")
            if href:
                full_url = urljoin(BASE_URL, href.split("#")[0])
                links.add(full_url)

        page += 1
        time.sleep(1)

    st.write("✅ Link collection finished.")
    return list(links)

def scrape_product(url):
    """
    Scrapes a single product page for specific details.
    """
    r = make_request(url)
    if not r:
        st.warning(f"Could not fetch {url}.")
        return {"Product Name": f"Error fetching page", "Price": "N/A", "Seller": "N/A", "SKU": "N/A", "Warranty Mentioned in Title": "N/A", "Warranty Details (Specs)": "N/A", "Warranty Address": "N/A", "Product URL": url}

    try:
        soup = BeautifulSoup(r.text, "lxml")
        # (The rest of the scraping logic remains the same)
        # Product Name
        try:
            name = soup.select_one("h1.-fs24").get_text(strip=True)
        except AttributeError:
            name = "Not indicated"

        # Price
        try:
            price = soup.select_one("span.-b").get_text(strip=True)
        except AttributeError:
            price = "Not indicated"

        # Seller
        try:
            seller = soup.select_one("div.-df.-j-bet > p.-m").get_text(strip=True)
        except AttributeError:
            seller = "Not indicated"

        # SKU
        try:
            sku_element = soup.find(string=re.compile(r"SKU", re.I))
            sku = sku_element.find_next().get_text(strip=True) if sku_element else "Not indicated"
        except (AttributeError, TypeError):
            sku = "Not indicated"

        # Warranty in Title
        warranty_title = "No"
        if re.search(r"(\b\d+\s?(yr|yrs|year|years)\b|\bwarranty\b)", name, re.I):
            warranty_title = "Yes"

        # Warranty in Specifications
        warranty_specs = "Not indicated"
        warranty_address = "Not indicated"
        try:
            spec_rows = soup.select("div.-pvs > ul > li")
            for row in spec_rows:
                row_text = row.get_text(strip=True).lower()
                if "product warranty" in row_text:
                    warranty_specs = row_text.split(":", 1)[-1].strip()
                if "warranty address" in row_text:
                    warranty_address = row_text.split(":", 1)[-1].strip()
        except AttributeError:
            pass

        return {
            "Product Name": name, "Price": price, "Seller": seller, "SKU": sku,
            "Warranty Mentioned in Title": warranty_title, "Warranty Details (Specs)": warranty_specs,
            "Warranty Address": warranty_address, "Product URL": url
        }
    except Exception as e:
        st.warning(f"An unexpected error occurred while parsing {url}. Reason: {e}")
        return {"Product Name": f"Error parsing page", "Price": "N/A", "Seller": "N/A", "SKU": "N/A", "Warranty Mentioned in Title": "N/A", "Warranty Details (Specs)": "N/A", "Warranty Address": "N/A", "Product URL": url}


# --- Streamlit User Interface ---
st.set_page_config(page_title="Jumia Warranty Scraper", layout="wide")
st.title("Jumia Category Warranty Scraper 🛒")
st.markdown("Enter a Jumia category URL to extract product details, focusing on warranty information.")

st.info("Example Category URL: `https://www.jumia.co.ke/television-sets/`")

category_url = st.text_input("Enter Jumia category URL:", key="url_input")

if st.button("🚀 Scrape Category", key="scrape_button") and category_url:
    parsed_url = urlparse(category_url)
    if not all([parsed_url.scheme, parsed_url.netloc, "jumia.co.ke" in parsed_url.netloc]):
        st.error("Please enter a valid Jumia Kenya URL (e.g., https://www.jumia.co.ke/...)")
    else:
        with st.spinner("Collecting product links... This may take a few minutes."):
            product_links = get_product_links(category_url)

        if not product_links:
            st.warning("No product links were found. Please check the category URL and try again.")
        else:
            st.success(f"✅ Found {len(product_links)} unique products. Now scraping details...")

            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, link in enumerate(product_links, start=1):
                status_text.text(f"Scraping product {i}/{len(product_links)}: {link}")
                details = scrape_product(link)
                results.append(details)
                progress_bar.progress(i / len(product_links))
                time.sleep(0.5)

            status_text.text("Scraping complete!")
            st.balloons()

            df = pd.DataFrame(results)
            st.dataframe(df)

            @st.cache_data
            def convert_df_to_excel(dataframe):
                from io import BytesIO
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, index=False, sheet_name='Jumia_Products')
                return output.getvalue()

            excel_data = convert_df_to_excel(df)

            st.download_button(
                label="📥 Download Results as Excel",
                data=excel_data,
                file_name="jumia_warranty_products.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
