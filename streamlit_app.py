import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
import time
import random
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# -----------------------------
# Config
# -----------------------------
BASE_URL = "https://www.jumia.co.ke"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}
REQUEST_TIMEOUT = 25
MAX_PAGES = 200          # safety cap for pagination
MAX_WORKERS = 12         # threads for product-page scraping
DELAY_BETWEEN_PAGE_FETCH = (0.6, 1.2)  # jitter (min, max) seconds
DELAY_BETWEEN_PRODUCT_FETCH = (0.0, 0.2)

# -----------------------------
# HTTP helper
# -----------------------------
def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp

# -----------------------------
# Product list extraction
# -----------------------------
def parse_links_from_grid(soup):
    links = set()
    # Primary grid selector
    for a in soup.select("article.prd > a.core"):
        href = a.get("href")
        if href:
            links.add(urljoin(BASE_URL, href.split("#")[0]))
    # Fallback: any <a.core> (older templates)
    if not links:
        for a in soup.select("a.core"):
            href = a.get("href")
            if href and href.startswith("/"):
                links.add(urljoin(BASE_URL, href.split("#")[0]))
    return links

def parse_links_from_jsonld(soup):
    links = set()
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "{}")
        except Exception:
            continue

        # data can be dict or list, sometimes nested in @graph
        candidates = []
        if isinstance(data, dict):
            candidates.append(data)
            if "@graph" in data and isinstance(data["@graph"], list):
                candidates += data["@graph"]
        elif isinstance(data, list):
            candidates += data

        for obj in candidates:
            # ItemList with itemListElement
            if isinstance(obj, dict) and obj.get("@type") in ("ItemList", "BreadcrumbList"):
                for item in obj.get("itemListElement", []):
                    if isinstance(item, dict):
                        # Sometimes item is nested under "item"
                        u = item.get("url") or (item.get("item") or {}).get("url")
                        if u and u.startswith("http"):
                            links.add(u.split("#")[0])
            # Product (rarely directly listed)
            if isinstance(obj, dict) and obj.get("@type") == "Product":
                u = obj.get("url")
                if u and u.startswith("http"):
                    links.add(u.split("#")[0])
    return links

def get_product_links(category_url, progress_placeholder):
    all_links = set()
    page = 1
    while page <= MAX_PAGES:
        # Build paginated URL
        if "?page=" in category_url:
            base = category_url.split("?page=")[0]
            page_url = f"{base}?page={page}"
        else:
            sep = "&" if "?" in category_url else "?"
            page_url = f"{category_url}{sep}page={page}"

        progress_placeholder.text(f"Scanning page {page} …")

        try:
            resp = fetch(page_url)
        except Exception:
            # Stop if page fetch fails (end or throttled)
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Try grid first
        links_grid = parse_links_from_grid(soup)
        # JSON-LD fallback
        links_jsonld = parse_links_from_jsonld(soup)

        found_now = links_grid | links_jsonld
        if not found_now:
            # No more products on further pages
            break

        all_links |= found_now
        page += 1
        time.sleep(random.uniform(*DELAY_BETWEEN_PAGE_FETCH))

    return list(all_links)

# -----------------------------
# Product page parsing
# -----------------------------
def text_or_default(node, default="Not indicated"):
    if not node:
        return default
    t = node.get_text(strip=True) if hasattr(node, "get_text") else str(node).strip()
    return t if t else default

def scrape_product(product_url):
    # brief polite jitter
    time.sleep(random.uniform(*DELAY_BETWEEN_PRODUCT_FETCH))

    try:
        resp = fetch(product_url)
    except Exception as e:
        return {
            "Product Name": f"Error fetching: {e}",
            "SKU": "Not indicated",
            "Seller": "Not indicated",
            "Price": "Not indicated",
            "Warranty in Title": "Not indicated",
            "Warranty (Specs)": "Not indicated",
            "Warranty Address": "Not indicated",
            "Product URL": product_url,
        }

    soup = BeautifulSoup(resp.text, "lxml")

    # Title / Name
    name = text_or_default(soup.select_one("h1"))
    # Price (common Jumia selector)
    price = text_or_default(soup.select_one("span.-b"))

    # Seller (several template variants)
    seller = "Not indicated"
    cand = soup.find("a", {"data-testid": "seller-name"})
    if cand:
        seller = text_or_default(cand)
    else:
        # Sometimes in a small paragraph near "Sold by"
        sold_by = soup.find(string=re.compile(r"Sold by", re.I))
        if sold_by and sold_by.parent:
            a = sold_by.parent.find_next("a")
            if a:
                seller = text_or_default(a)
        if seller == "Not indicated":
            # Older template
            p = soup.select_one("div.-df.-j-bet > p.-m")
            if p:
                seller = text_or_default(p)

    # SKU: various layouts (table, list)
    sku = "Not indicated"
    # table rows
    for tr in soup.select("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th and re.search(r"\bSKU\b", th.get_text(strip=True), re.I):
            sku = text_or_default(td)
            break
    if sku == "Not indicated":
        # list items
        for li in soup.select("li"):
            txt = li.get_text(" ", strip=True)
            if re.search(r"\bSKU\b", txt, re.I):
                parts = re.split(r":", txt, maxsplit=1)
                if len(parts) == 2:
                    sku = parts[1].strip() or "Not indicated"
                    break

    # Warranty in title
    warranty_in_title = "Not indicated"
    if re.search(r"(warranty|\b\d+\s?(yr|yrs|year|years)\b)", name, re.I):
        warranty_in_title = name

    # Warranty (Specs) + Warranty Address (check table rows and bullet lists)
    warranty_specs = "Not indicated"
    warranty_address = "Not indicated"

    # Tables first
    for tr in soup.select("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th:
            key = th.get_text(strip=True).lower()
            val = text_or_default(td)
            if "warranty address" in key and warranty_address == "Not indicated":
                warranty_address = val
            if ("warranty" in key) and ("address" not in key) and (warranty_specs == "Not indicated"):
                warranty_specs = val

    # Bullet lists (e.g., under “Specifications”)
    for li in soup.select("div.-pvs ul li"):
        raw = li.get_text(" ", strip=True)
        key_val = raw.split(":", 1)
        if len(key_val) == 2:
            key = key_val[0].strip().lower()
            val = key_val[1].strip() or "Not indicated"
            if "warranty address" in key and warranty_address == "Not indicated":
                warranty_address = val
            if ("warranty" in key) and ("address" not in key) and (warranty_specs == "Not indicated"):
                warranty_specs = val

    return {
        "Product Name": name,
        "SKU": sku,
        "Seller": seller,
        "Price": price,
        "Warranty in Title": warranty_in_title,
        "Warranty (Specs)": warranty_specs,
        "Warranty Address": warranty_address,
        "Product URL": product_url,
    }

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Jumia Warranty Scraper", layout="wide")
st.title("Jumia Category Warranty Scraper 🔎")
st.caption("Paste **any Jumia Kenya category URL**. The app will collect products, then scrape each product page for warranty details, SKU, seller, and price.")

st.info("Example category: https://www.jumia.co.ke/television-sets/")

category_url = st.text_input("Enter Jumia category URL:")
start = st.button("Scrape Category")

if start:
    # Basic validation
    try:
        parsed = urlparse(category_url)
        if not (parsed.scheme and parsed.netloc and "jumia.co.ke" in parsed.netloc):
            st.error("Please enter a valid Jumia Kenya URL (e.g., https://www.jumia.co.ke/television-sets/)")
            st.stop()
    except Exception:
        st.error("Please enter a valid URL.")
        st.stop()

    st.subheader("Step 1: Collecting product links")
    page_status = st.empty()
    links = get_product_links(category_url, page_status)
    st.success(f"Found {len(links)} unique product URLs.")
    if not links:
        st.stop()

    st.subheader("Step 2: Scraping product pages")
    prog = st.progress(0.0)
    status = st.empty()
    results = []

    # Multithreaded scraping
    total = len(links)
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(scrape_product, url): url for url in links}
        for fut in as_completed(futures):
            data = fut.result()
            results.append(data)
            completed += 1
            prog.progress(completed / total)
            status.text(f"Processed {completed} of {total}")

    st.success("Scraping complete!")
    df = pd.DataFrame(results)

    # Ensure warranty columns say "Not indicated" if empty
    for col in ["Warranty in Title", "Warranty (Specs)", "Warranty Address"]:
        df[col] = df[col].apply(lambda x: x if (isinstance(x, str) and x.strip()) else "Not indicated")

    st.dataframe(df, use_container_width=True)

    # Download to Excel
    @st.cache_data
    def to_excel_bytes(frame: pd.DataFrame) -> bytes:
        from io import BytesIO
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            frame.to_excel(writer, index=False, sheet_name="Jumia_Products")
        return buf.getvalue()

    st.download_button(
        "📥 Download Excel",
        data=to_excel_bytes(df),
        file_name="jumia_warranty_products.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
