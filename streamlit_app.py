import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from io import BytesIO
import json
import re
import time
import random
import requests
import cloudscraper
from tenacity import retry, stop_after_attempt, wait_exponential

# -----------------------------
# Config
# -----------------------------
MAX_PAGES = 50  # Maximum pages to try
MAX_WORKERS = 4  # Balanced for cloud environments
PAGE_SLEEP = (1.0, 2.0)  # Delay to avoid bot detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
]
EXCLUDED_SUBCATS = ["sp-", "mlp-", "cart", "account", "login", "signup", "help", "sell", "official-stores", "flash-sale", "contact", "about"]

# -----------------------------
# Fetching Helper
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_page(url: str, proxy=None):
    try:
        scraper = cloudscraper.create_scraper()
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        proxies = {"http": proxy, "https": proxy} if proxy else None
        response = scraper.get(url, headers=headers, proxies=proxies, timeout=20)
        response.raise_for_status()
        return response.text
    except Exception as e:
        st.error(f"Failed to fetch {url}: {str(e)}")
        return None

# -----------------------------
# Parsing Helpers
# -----------------------------
def all_ldjson_objects(soup: BeautifulSoup):
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            text = s.string or s.get_text()
            if text:
                data = json.loads(text)
                if isinstance(data, list):
                    yield from data
                else:
                    yield data
        except Exception:
            continue

def find_product_objs_from_ldjson(soup: BeautifulSoup):
    products = []
    for obj in all_ldjson_objects(soup):
        if isinstance(obj, dict) and "@graph" in obj:
            for g in obj.get("@graph", []):
                if isinstance(g, dict) and g.get("@type") == "Product":
                    products.append(g)
        if isinstance(obj, dict) and obj.get("@type") == "Product":
            products.append(obj)
    return products

def parse_data_layer(soup: BeautifulSoup):
    data_layer = {}
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        if "dataLayer" in text:
            try:
                match = re.search(r'dataLayer\s*=\s*($$ .*? $$);', text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    if isinstance(data, list) and data:
                        return data[0]
            except Exception:
                continue
    return data_layer

def parse_links_from_grid(soup: BeautifulSoup, base_url: str):
    links = set()
    # Strategy 1: Main product grid
    product_grid = soup.select_one("div[class*='-paxs'], div[class*='row'], section[class*='card'], div[class*='products'], div[class*='item'], div[class*='prd-grid']")
    if product_grid:
        product_cards = product_grid.find_all("article", recursive=False) or product_grid.find_all("div", recursive=False)
        for card in product_cards:
            if link_tag := card.find("a", href=True):
                href = link_tag['href'].split("#")[0]
                if href.endswith(".html") and not any(excl in href.lower() for excl in EXCLUDED_SUBCATS):
                    links.add(urljoin(base_url, href))
        if links:
            return list(links)
    
    # Strategy 2: Broader article or div-based search
    for card in soup.select("article[class*='prd'], div[class*='prd'], div[class*='item']"):
        if link_tag := card.find("a", href=True):
            href = link_tag['href'].split("#")[0]
            if href.endswith(".html") and not any(excl in href.lower() for excl in EXCLUDED_SUBCATS):
                links.add(urljoin(base_url, href))
        if links:
            return list(links)
    
    # Strategy 3: Generic link search
    for link_tag in soup.select("a[href$='.html']"):
        href = link_tag['href'].split("#")[0]
        if not any(excl in href.lower() for excl in EXCLUDED_SUBCATS):
            links.add(urljoin(base_url, href))
    
    return list(links)

def get_total_pages(soup: BeautifulSoup):
    try:
        pagination = soup.select_one("nav.pagination, div.pagination, ul.pagination")
        if pagination:
            last_page = pagination.find_all("a")[-2].get_text(strip=True)  # Skip 'Next'
            if last_page.isdigit():
                return min(int(last_page), MAX_PAGES)
        page_info = soup.find(lambda t: re.search(r'\b\d+\s*of\s*\d+\b', t.get_text()))
        if page_info:
            match = re.search(r'\b\d+\s*of\s*(\d+)\b', page_info.get_text())
            if match:
                return min(int(match.group(1)), MAX_PAGES)
        # Check for 'dataLayer' pagination info
        data_layer = parse_data_layer(soup)
        if data_layer.get("ecommerce", {}).get("impressions"):
            total_items = len(data_layer["ecommerce"]["impressions"])
            return min((total_items // 40) + 1, MAX_PAGES)  # Assume 40 items per page
        return MAX_PAGES
    except Exception:
        return MAX_PAGES

def get_product_links(category_url: str, base_url: str, status_placeholder, proxy=None, depth=0):
    if depth > 1:
        status_placeholder.text(f"Skipping {category_url}: Maximum subcategory depth reached.")
        return set()
    
    all_links = set()
    page = 1
    
    html_content = fetch_page(category_url, proxy)
    if not html_content:
        st.error(f"Failed to fetch {category_url}. Check URL or proxy settings.")
        return []
    
    soup = BeautifulSoup(html_content, "lxml")
    
    # Check for subcategories
    subcategories = soup.select("a[href*='/'][href$='/']")
    for subcat in subcategories:
        subcat_url = urljoin(base_url, subcat['href'])
        if ("jumia.co.ke" in subcat_url and 
            not any(excl in subcat_url.lower() for excl in EXCLUDED_SUBCATS) and
            not any(x in subcat_url.lower() for x in ["login", "account", "cart"])):
            status_placeholder.text(f"Exploring subcategory: {subcat_url}")
            all_links.update(get_product_links(subcat_url, base_url, status_placeholder, proxy, depth + 1))
    
    max_pages = get_total_pages(soup)
    status_placeholder.text(f"Detected {max_pages} pages for {category_url}")
    
    while page <= max_pages:
        pagination_formats = [
            f"{category_url}{'' if category_url.endswith('/') else '/'}{'?page=' if '?' not in category_url else '&page='}{page}",
            f"{category_url.rstrip('/')}/page/{page}/"
        ]
        page_url = pagination_formats[0]
        html_content = None
        for fmt in pagination_formats:
            status_placeholder.text(f"Collecting links… page {page} ({fmt})")
            html_content = fetch_page(fmt, proxy)
            if html_content:
                page_url = fmt
                break
        else:
            st.warning(f"Failed to fetch page {page} for all pagination formats. Stopping pagination.")
            break
        
        soup = BeautifulSoup(html_content, "lxml")
        found_links = parse_links_from_grid(soup, base_url)
        
        if not found_links:
            st.warning(f"No product links found on page {page} ({page_url}). Stopping pagination.")
            break
        
        new_links = set(found_links) - all_links
        if not new_links and page > 1:
            st.warning(f"No new links found on page {page} ({page_url}). Stopping pagination.")
            break
        
        all_links.update(new_links)
        status_placeholder.text(f"Found {len(new_links)} new links on page {page} (Total: {len(all_links)})")
        page += 1
        time.sleep(random.uniform(*PAGE_SLEEP))
        
    return list(all_links)

def text_or_na(node, default="Not indicated"):
    if not node:
        return default
    t = node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node).strip()
    return t if t else default

# -----------------------------
# Core Extraction Logic
# -----------------------------
def clean_price(price_str: str) -> str:
    if not price_str or price_str == "Not indicated":
        return "Not indicated"
    price_str = re.sub(r'[^\d,.]', '', price_str)
    price_str = price_str.replace(',', '')
    return price_str

def extract_basic_fields(soup: BeautifulSoup):
    name, price, sku, seller = "Not indicated", "Not indicated", "Not indicated", "Not indicated"
    main_content = soup.find("main", {"role": "main"}) or soup
    
    # Try dataLayer first
    data_layer = parse_data_layer(soup)
    if data_layer.get("ecommerce", {}).get("detail", {}).get("products"):
        product = data_layer["ecommerce"]["detail"]["products"][0]
        name = product.get("name", name)
        sku = product.get("id", sku)
        price = product.get("price", price)
        seller = data_layer.get("dimension23", seller)
    
    # Try ld+json
    products = find_product_objs_from_ldjson(soup)
    if products:
        p = products[0]
        name = p.get("name", name)
        sku = p.get("sku", sku)
        if isinstance(p.get("offers"), dict):
            price = p["offers"].get("price", price)
            if isinstance(p["offers"].get("seller"), dict):
                seller = p["offers"]["seller"].get("name", seller)
    
    # Fallback to HTML parsing
    if name == "Not indicated":
        name = text_or_na(main_content.select_one("h1"))
    if price == "Not indicated":
        price = text_or_na(main_content.select_one("span.-b, span.price, div.price, span[data-price], div.-prc"))
    if seller == "Not indicated":
        seller_node = main_content.select_one("div.seller-info, div.-seller, p.seller-name, a.seller-link, div.seller-details, span.seller")
        if seller_node:
            seller_text = text_or_na(seller_node)
            if "follow" not in seller_text.lower():
                seller = seller_text
        else:
            for node in main_content.select("p, div, span"):
                text = node.get_text(strip=True).lower()
                if "seller" in text and not any(x in text for x in ["follow", "rating", "score"]):
                    seller = text_or_na(node)
                    break
    if seller == "Not indicated" and main_content.select_one('img[alt*="Jumia Express"]'):
        seller = "Jumia"
    
    return name, clean_price(price), sku, seller

def extract_warranty_fields(soup: BeautifulSoup, title_text: str):
    warranty_title, warranty_specs, warranty_address = "Not indicated", "Not indicated", "Not indicated"
    main_content = soup.find("main", {"role": "main"}) or soup
    
    if re.search(r"(warranty|\b\d+\s?(yr|year|month))", title_text or "", re.I):
        warranty_title = title_text
    
    warranty_heading = main_content.find(lambda t: t.name in ['p', 'div', 'span'] and 'warranty' in t.get_text(strip=True).lower())
    if warranty_heading and (detail_node := warranty_heading.find_next_sibling()):
        warranty_specs = text_or_na(detail_node)
    
    if warranty_specs == "Not indicated":
        for tr in main_content.select("div.-pdp-add-info tr, table.specifications tr, div.-spec"):
            cells = tr.find_all("td")
            if len(cells) == 2 and "warranty" in cells[0].get_text(strip=True).lower():
                warranty_specs = cells[1].get_text(strip=True)
                break
    
    if warranty_specs == "Not indicated":
        desc = main_content.select_one("div.markup, div.-product-desc, div.description")
        if desc:
            desc_text = desc.get_text(strip=True).lower()
            match = re.search(r'warranty\s*[:\-]?\s*(\d+\s*(year|month|yr|mo)s?\s*(?:warranty)?)', desc_text, re.I)
            if match:
                warranty_specs = match.group(0)
    
    warranty_address_node = main_content.find(lambda t: t.name in ['p', 'div', 'span'] and 'warranty address' in t.get_text(strip=True).lower())
    if warranty_address_node:
        warranty_address = text_or_na(warranty_address_node.find_next_sibling() or warranty_address_node)
    
    return warranty_title, warranty_specs, warranty_address

def parse_product(url: str, proxy=None):
    html_content = fetch_page(url, proxy)
    if not html_content:
        return {col: "Error fetching page" for col in ["Product Title", "SKU", "Seller", "Price", "Warranty Title", "Warranty (Specs)", "Warranty Address"]} | {"Product URL": url}
    soup = BeautifulSoup(html_content, "lxml")
    name, price, sku, seller = extract_basic_fields(soup)
    w_title, w_specs, w_addr = extract_warranty_fields(soup, name)
    return {
        "Product Title": name or "Not indicated",
        "SKU": sku or "Not indicated",
        "Seller": seller or "Not indicated",
        "Price": price or "Not indicated",
        "Warranty Title": w_title or "Not indicated",
        "Warranty (Specs)": w_specs or "Not indicated",
        "Warranty Address": w_addr or "Not indicated",
        "Product URL": url,
    }

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Jumia Warranty Scraper", layout="wide")
st.title("Jumia Warranty Scraper")
st.caption("Scrapes product details from any Jumia Kenya category page. Enter a category URL and optional proxy settings.")

category_url = st.text_input("Enter Jumia category URL", value="https://www.jumia.co.ke/phones-tablets/", placeholder="e.g., https://www.jumia.co.ke/fashion/ or https://www.jumia.co.ke/baby-products/")
proxy = st.text_input("Proxy (optional, format: http://user:pass@host:port)", placeholder="Leave blank for no proxy")
debug_mode = st.checkbox("Enable Debug Mode (logs raw HTML for failed pages)")

if st.button("Scrape Category"):
    try:
        parsed_url = urlparse(category_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if not all([parsed_url.scheme, parsed_url.netloc, "jumia.co.ke" in base_url]) or "product" in parsed_url.path.lower():
            raise ValueError("Invalid URL. Please enter a valid Jumia category URL (e.g., https://www.jumia.co.ke/electronics/).")
        if any(excl in parsed_url.path.lower() for excl in EXCLUDED_SUBCATS):
            raise ValueError(f"Invalid category URL. URLs containing {', '.join(EXCLUDED_SUBCATS)} are not supported.")
    except (ValueError, AttributeError) as e:
        st.error(str(e))
        st.stop()

    st.subheader("Step 1 — Collecting product links")
    link_status = st.empty()
    with st.spinner("Collecting product links… This may take a moment."):
        links = get_product_links(category_url, base_url, link_status, proxy)
    
    if not links:
        st.error(
            "No product URLs found. Possible causes:\n"
            "- The category URL may be incorrect or empty.\n"
            "- The website may have blocked the request (try using a proxy or running locally).\n"
            "- The HTML structure may have changed (enable Debug Mode to inspect HTML).\n"
            "Please check the URL or try again later."
        )
        if debug_mode:
            html_content = fetch_page(category_url, proxy)
            if html_content:
                st.text_area("Debug: Raw HTML", html_content[:5000], height=300)
        st.stop()
    
    st.success(f"Found {len(links)} product URLs.")
    st.subheader("Step 2 — Scraping product pages")
    prog = st.progress(0.0)
    status = st.empty()
    results = []
    total = len(links)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(parse_product, u, proxy): u for u in links}
        for i, fut in enumerate(as_completed(futures)):
            result = fut.result()
            results.append(result)
            prog.progress((i + 1) / total)
            status.text(f"Scraped {i + 1}/{total}")
            if debug_mode and "Error fetching page" in result.values():
                html_content = fetch_page(result["Product URL"], proxy)
                if html_content:
                    st.text_area(f"Debug: Raw HTML for {result['Product URL']}", html_content[:5000], height=300)
    
    st.success("Scraping complete!")
    df = pd.DataFrame(results)
    for col in ["Product Title", "SKU", "Seller", "Price", "Warranty Title", "Warranty (Specs)", "Warranty Address"]:
        df[col] = df[col].apply(lambda x: str(x).strip() if x and str(x).strip() else "Not indicated")
    st.dataframe(df, use_container_width=True)
    
    try:
        import xlsxwriter
        @st.cache_data
        def to_excel_bytes(frame: pd.DataFrame) -> bytes:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                frame.to_excel(writer, index=False, sheet_name="Products")
            return buf.getvalue()
        st.download_button("📥 Download Excel", to_excel_bytes(df), "jumia_products.xlsx")
    except ImportError:
        st.error("Excel download unavailable: xlsxwriter module not found. Using CSV download instead.")
    
    st.download_button("📥 Download CSV", df.to_csv(index=False), "jumia_products.csv")
