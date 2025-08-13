import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from urllib.parse import urljoin, urlparse

# It's a good practice to define headers to mimic a real browser visit.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
}
BASE_URL = "https://www.jumia.co.ke"

def get_product_links(category_url):
    """
    Crawls through category pages to collect unique product URLs.

    Args:
        category_url (str): The URL of the Jumia category page.

    Returns:
        list: A list of unique, absolute product URLs.
    """
    links = set()  # Use a set for automatic duplicate handling
    page = 1
    st.write("🔎 Starting product link collection...")
    progress_text = st.empty()

    while True:
        # Construct the URL for the current page
        paginated_url = f"{category_url}?page={page}"
        progress_text.text(f"Scanning page: {paginated_url}")

        try:
            r = requests.get(paginated_url, headers=HEADERS, timeout=15)
            # Stop if we encounter a page that doesn't exist or has an error
            if r.status_code != 200:
                st.warning(f"Reached end of category or encountered an issue on page {page} (Status: {r.status_code}).")
                break

            soup = BeautifulSoup(r.text, "lxml")
            # This selector targets the main product links within the article cards
            product_cards = soup.select("article.prd > a.core")

            # If no product cards are found, we've likely gone past the last page
            if not product_cards:
                st.write(f"No more products found on page {page}. Concluding link collection.")
                break

            found_new_link = False
            for card in product_cards:
                href = card.get("href")
                if href:
                    # Create an absolute URL and remove any fragments
                    full_url = urljoin(BASE_URL, href.split("#")[0])
                    if full_url not in links:
                        links.add(full_url)
                        found_new_link = True

            page += 1
            time.sleep(1)  # Be respectful to the server

        except requests.exceptions.RequestException as e:
            st.error(f"A network error occurred: {e}")
            break

    st.write("✅ Link collection finished.")
    return list(links)

def scrape_product(url):
    """
    Scrapes a single product page for specific details.

    Args:
        url (str): The URL of the product page.

    Returns:
        dict: A dictionary containing the scraped product details.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()  # Will raise an HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(r.text, "lxml")

        # --- Extract Product Details ---
        # Each extraction is in a try-except block to prevent a single missing
        # element from causing the entire scrape for this product to fail.

        # Product Name
        try:
            name = soup.select_one("h1.-fs24").get_text(strip=True)
        except AttributeError:
            name = "Not indicated"

        # Price
        try:
            # The price is usually in a span with this class.
            price = soup.select_one("span.-b").get_text(strip=True)
        except AttributeError:
            price = "Not indicated"

        # Seller
        try:
            # This selector targets the seller's name within the summary section.
            seller = soup.select_one("div.-df.-j-bet > p.-m").get_text(strip=True)
        except AttributeError:
            seller = "Not indicated"

        # SKU
        try:
            # Find the 'SKU:' text and get the text of the next element, which is the value.
            sku_element = soup.find(string=re.compile(r"SKU", re.I))
            sku = sku_element.find_next().get_text(strip=True) if sku_element else "Not indicated"
        except (AttributeError, TypeError):
            sku = "Not indicated"

        # Warranty in Title (Regex Search)
        warranty_title = "No"
        # Search for patterns like "1 Year", "2 Yrs", "warranty", etc.
        if re.search(r"(\b\d+\s?(yr|yrs|year|years)\b|\bwarranty\b)", name, re.I):
            warranty_title = "Yes"

        # Warranty in Specifications Table
        warranty_specs = "Not indicated"
        warranty_address = "Not indicated"
        try:
            # Find all rows in the specifications section
            spec_rows = soup.select("div.-pvs > ul > li")
            for row in spec_rows:
                row_text = row.get_text(strip=True).lower()
                if "product warranty" in row_text:
                    # Split the text at the colon and take the second part
                    warranty_specs = row_text.split(":", 1)[-1].strip()
                if "warranty address" in row_text:
                    warranty_address = row_text.split(":", 1)[-1].strip()
        except AttributeError:
            # This will catch errors if the spec section isn't found
            pass


        return {
            "Product Name": name,
            "Price": price,
            "Seller": seller,
            "SKU": sku,
            "Warranty Mentioned in Title": warranty_title,
            "Warranty Details (Specs)": warranty_specs,
            "Warranty Address": warranty_address,
            "Product URL": url
        }

    except requests.exceptions.RequestException as e:
        st.warning(f"Could not fetch {url}. Reason: {e}")
        return {"Product Name": f"Error fetching page", "Price": "N/A", "Seller": "N/A", "SKU": "N/A", "Warranty Mentioned in Title": "N/A", "Warranty Details (Specs)": "N/A", "Warranty Address": "N/A", "Product URL": url}
    except Exception as e:
        st.warning(f"An unexpected error occurred while scraping {url}. Reason: {e}")
        return {"Product Name": f"Error parsing page", "Price": "N/A", "Seller": "N/A", "SKU": "N/A", "Warranty Mentioned in Title": "N/A", "Warranty Details (Specs)": "N/A", "Warranty Address": "N/A", "Product URL": url}


# --- Streamlit User Interface ---
st.set_page_config(page_title="Jumia Warranty Scraper", layout="wide")
st.title("Jumia Category Warranty Scraper 🛒")
st.markdown("Enter a Jumia category URL to extract product details, focusing on warranty information.")

# Example URL for user guidance
st.info("Example Category URL: `https://www.jumia.co.ke/television-sets/`")

category_url = st.text_input("Enter Jumia category URL:", key="url_input")

if st.button("🚀 Scrape Category", key="scrape_button") and category_url:
    # Validate URL
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
                time.sleep(0.5)  # A small delay to be polite to the server

            status_text.text("Scraping complete!")
            st.balloons()

            df = pd.DataFrame(results)
            st.dataframe(df)

            # --- Excel Export ---
            @st.cache_data
            def convert_df_to_excel(dataframe):
                # Using BytesIO to create the Excel file in memory
                from io import BytesIO
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, index=False, sheet_name='Jumia_Products')
                processed_data = output.getvalue()
                return processed_data

            excel_data = convert_df_to_excel(df)

            st.download_button(
                label="📥 Download Results as Excel",
                data=excel_data,
                file_name="jumia_warranty_products.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
