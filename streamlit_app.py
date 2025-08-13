import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from urllib.parse import urljoin, urlparse
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# --- Configuration ---
BASE_URL = "https://www.jumia.co.ke"

@st.cache_resource
def get_driver():
    """
    Sets up and returns a Selenium WebDriver instance for Chrome.
    Caches the driver to avoid re-initializing on every script rerun.
    """
    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # This will download the correct ChromeDriver version for the environment
    service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
    
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def make_request_with_selenium(url, driver):
    """
    Makes a request using Selenium to handle dynamic JavaScript content.
    """
    try:
        driver.get(url)
        # Give the page a moment to load any dynamic content
        time.sleep(3)
        return driver.page_source
    except Exception as e:
        st.error(f"An error occurred with Selenium: {e}")
        return None

def get_product_links(category_url, driver):
    """
    Crawls through category pages to collect unique product URLs using Selenium.
    """
    links = set()
    page = 1
    st.write("🔎 Starting product link collection...")
    progress_text = st.empty()

    while True:
        paginated_url = f"{category_url}?page={page}"
        progress_text.text(f"Scanning page: {paginated_url}")

        html_content = make_request_with_selenium(paginated_url, driver)
        if not html_content:
            st.error(f"Failed to fetch {paginated_url} using Selenium.")
            break

        soup = BeautifulSoup(html_content, "lxml")
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

def scrape_product(url, driver):
    """
    Scrapes a single product page for specific details using Selenium.
    """
    html_content = make_request_with_selenium(url, driver)
    if not html_content:
        st.warning(f"Could not fetch {url}.")
        return {"Product Name": f"Error fetching page", "Price": "N/A", "Seller": "N/A", "SKU": "N/A", "Warranty Mentioned in Title": "N/A", "Warranty Details (Specs)": "N/A", "Warranty Address": "N/A", "Product URL": url}

    try:
        soup = BeautifulSoup(html_content, "lxml")
        # (The scraping logic remains the same as it operates on the HTML)
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
st.markdown("Enter a Jumia category URL to extract product details. This version uses Selenium to avoid being blocked.")

st.info("Example Category URL: `https://www.jumia.co.ke/television-sets/`")

category_url = st.text_input("Enter Jumia category URL:", key="url_input")

if st.button("🚀 Scrape Category", key="scrape_button") and category_url:
    parsed_url = urlparse(category_url)
    if not all([parsed_url.scheme, parsed_url.netloc, "jumia.co.ke" in parsed_url.netloc]):
        st.error("Please enter a valid Jumia Kenya URL (e.g., https://www.jumia.co.ke/...)")
    else:
        driver = get_driver()
        with st.spinner("Collecting product links using a headless browser... This may take a few minutes."):
            product_links = get_product_links(category_url, driver)

        if not product_links:
            st.warning("No product links were found. Please check the category URL and try again.")
        else:
            st.success(f"✅ Found {len(product_links)} unique products. Now scraping details...")

            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, link in enumerate(product_links, start=1):
                status_text.text(f"Scraping product {i}/{len(product_links)}: {link}")
                details = scrape_product(link, driver)
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
