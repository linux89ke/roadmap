import streamlit as st
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from io import BytesIO
from requests_html import HTMLSession
import json
import re
import time
import random

# -----------------------------
# Config
# -----------------------------
MAX_PAGES = 200
MAX_WORKERS = 8
PAGE_SLEEP = (0.4, 0.9)
REQ_RETRIES = 3
REQ_TIMEOUT = 35
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 1.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

scraper = cloudscraper.create_scraper(browser={"custom": HEADERS["User-Agent"]})
html_session = HTMLSession()

# -----------------------------
# Fetching Helpers
# -----------------------------
def fetch_with_retry(url, retries=REQ_RETRIES):
    for attempt in range(1, retries + 1):
        try:
            r = scraper.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
            if r.status_code == 200 and r.text:
                return r
        except Exception:
            pass
        time.sleep(0.6 * attempt)
    return None

def fetch_with_js(url, retries=2):
    for _ in range(retries):
        try:
            r = html_session.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
            r.html.render(timeout=40, sleep=3, keep_page=True)
            r.close() # Important to close the browser tab to conserve memory
            return r
        except Exception:
            pass
    return None

# -----------------------------
# Parsing Helpers
# -----------------------------
def all_ldjson_objects(soup: BeautifulSoup):
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            text = s.string or s.get_text()
            if not text: continue
            data = json.loads(text)
            if isinstance(data, list):
                for item in data: yield item
            else:
                yield data
        except Exception:
            continue

def find_product_objs_from_ldjson(soup: BeautifulSoup):
    products = []
    for obj in all_ldjson_objects(soup):
        if isinstance(obj, dict) and "@graph" in obj and isinstance(obj["@graph"], list):
            for g in obj["@graph"]:
                if isinstance(g, dict) and g.get("@type") == "Product": products.append(g)
        if isinstance(obj, dict) and obj.get("@type") == "Product": products.append(obj)
        if isinstance(obj, dict) and isinstance(obj.get("mainEntity"), dict):
            me = obj["mainEntity"]
            if me.get("@type") == "Product": products.append(me)
    return products

def parse_links_from_grid(soup: BeautifulSoup, base_url: str):
    links = set()
    for a in soup.select("article.prd a.core"):
        href = a.get("href")
        if href: links.add(urljoin(base_url, href.split("#")[0]))
    if not links:
        for a in soup.select("a.core"):
            href = a.get("href")
            if href and href.startswith("/"): links.add(urljoin(base_url, href.split("#")[0]))
    return links

def parse_links_from_itemlist(soup: BeautifulSoup):
    links = set()
    for obj in all_ldjson_objects(soup):
        if isinstance(obj, dict) and obj.get("@type") in ("ItemList", "BreadcrumbList"):
            for item in obj.get("itemListElement", []):
                if isinstance(item, dict):
                    url = item.get("url") or (item.get("item") or {}).get("url")
                    if url and url.startswith("http"): links.add(url.split("#")[0])
    return links

def get_product_links(category_url: str, base_url: str, status_placeholder):
    all_links = set()
    page = 1
    while page <= MAX_PAGES:
        sep = "&" if "?" in category_url else "?"
        page_url = f"{category_url}{sep}page={page}"
        status_placeholder.text(f"Collecting links… page {page}")
        r = fetch_with_retry(page_url)
        if not r: break
        soup = BeautifulSoup(r.text, "lxml")
        found = parse_links_from_grid(soup, base_url) | parse_links_from_itemlist(soup)
        if not found: break
        all_links |= found
        page += 1
        time.sleep(random.uniform(*PAGE_SLEEP))
    return list(all_links)

def text_or_na(node, default="Not indicated"):
    if not node: return default
    t = node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node).strip()
    return t if t else default

# -----------------------------
# Core Extraction Logic (Rewritten for Precision)
# -----------------------------
def extract_basic_fields(soup: BeautifulSoup):
    name, price, sku, seller = "Not indicated", "Not indicated", "Not indicated", "Not indicated"

    # 1. Primary source: JSON-LD structured data
    products = find_product_objs_from_ldjson(soup)
    if products:
        p = products[0]
        name = p.get("name") or name
        sku = p.get("sku") or sku
        offers = p.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price") or offers.get("priceSpecification", {}).get("price") or price
            if isinstance(offers.get("seller"), dict): seller = offers["seller"].get("name") or seller

    # 2. Fallbacks using visual elements (since page is fully rendered)
    if name == "Not indicated": name = text_or_na(soup.select_one("h1"))
    if price == "Not indicated": price = text_or_na(soup.select_one("span.-b"))
    if sku == "Not indicated":
        for li in soup.select("li"):
            txt = li.get_text(" ", strip=True)
            if re.search(r"\bSKU\b\s*:", txt, re.I):
                sku = txt.split(":", 1)[-1].strip() or "Not indicated"; break

    # 3. Precise Seller Logic
    if seller == "Not indicated":
        # Look for the "Seller Information" box
        seller_header = soup.find(lambda t: t.name in ['h2', 'h3'] and 'seller information' in t.text.lower())
        if seller_header:
            content_area = seller_header.find_next_sibling()
            if content_area:
                # Find a link or plain text, but ignore "Follow"
                node = content_area.find("a") or content_area.find(['p', 'div', 'h3'])
                if node:
                    seller_text = text_or_na(node)
                    if "follow" not in seller_text.lower(): seller = seller_text
    
    # 4. Final Fallback: Check for Jumia Express items
    if seller == "Not indicated":
        if soup.select_one('img[alt*="Jumia Express"]'): seller = "Jumia"
        
    return name, price, sku, seller

def extract_warranty_fields(soup: BeautifulSoup, title_text: str):
    warranty_title, warranty_specs, warranty_address = "Not indicated", "Not indicated", "Not indicated"

    # 1. Check title first
    if re.search(r"(warranty|\b\d+\s?(yr|yrs|year|years)\b)", title_text or "", re.I):
        warranty_title = title_text

    # 2. Look for the structured sidebar section (most reliable)
    warranty_heading = soup.find(lambda t: t.name in ['p', 'div', 'span'] and t.get_text(strip=True).lower() == 'warranty')
    if warranty_heading:
        detail_node = warranty_heading.find_next_sibling()
        if detail_node: warranty_specs = text_or_na(detail_node)

    # 3. Look in the main specifications table (very specific selector to avoid other tables)
    for tr in soup.select("div.-pdp-add-info tr"):
        cells = tr.find_all("td")
        if len(cells) == 2:
            key = cells[0].get_text(strip=True).lower()
            val = cells[1].get_text(strip=True)
            # Use found value only if we haven't found a better one already
            if "warranty" in key and "address" not in key and warranty_specs == "Not indicated": warranty_specs = val
            if "warranty address" in key and warranty_address == "Not indicated": warranty_address = val

    # 4. Look for promotional badges (less reliable, but good fallback)
    if warranty_specs == "Not indicated":
        promo = soup.find(lambda t: t.name in ['p', 'span', 'div'] and re.search(r'\b\d+\s?(year|yr|month)s?\s+warranty\b', t.text, re.I))
        if promo: warranty_specs = text_or_na(promo)
        
    return warranty_title, warranty_specs, warranty_address

def parse_product(url: str):
    # --- "JavaScript First" Strategy ---
    r = fetch_with_js(url)
    # Fallback to simple fetch only if JS rendering fails completely
    if not r or not hasattr(r, 'html') or not r.html.html:
        r = fetch_with_retry(url)
        if not r:
            return {col: "Error fetching page" for col in ["Product Title", "SKU", "Seller", "Price", "Warranty Title", "Warranty (Specs)", "Warranty Address"]} | {"Product URL": url}
        html_content = r.text
    else:
        html_content = r.html.html

    soup = BeautifulSoup(html_content, "lxml")
    name, price, sku, seller = extract_basic_fields(soup)
    w_title, w_specs, w_addr = extract_warranty_fields(soup, name)
    return {
        "Product Title": name or "Not indicated", "SKU": sku or "Not indicated",
        "Seller": seller or "Not indicated", "Price": price or "Not indicated",
        "Warranty Title": w_title or "Not indicated", "Warranty (Specs)": w_specs or "Not indicated",
        "Warranty Address": w_addr or "Not indicated", "Product URL": url,
    }

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Warranty Scraper", layout="wide")
st.title("Universal Product Warranty Scraper 🌍")
st.caption("Paste a category URL from a supported e-commerce site (e.g., Jumia).")
category_url = st.text_input("Enter category URL")
if go := st.button("Scrape Category"):
    try:
        parsed_url = urlparse(category_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if not all([parsed_url.scheme, parsed_url.netloc]): raise ValueError
    except (ValueError, AttributeError):
        st.error("Please enter a valid category URL."); st.stop()
    st.subheader("Step 1 — Collecting product links")
    link_status = st.empty()
    with st.spinner("Collecting product links…"):
        links = get_product_links(category_url, base_url, link_status)
    st.success(f"Found {len(links)} product URLs.")
    if not links: st.stop()
    st.subheader("Step 2 — Scraping product pages (this may take a while for JS rendering)")
    prog = st.progress(0.0)
    status = st.empty()
    results = []
    total = len(links)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(parse_product, u): u for u in links}
        for i, fut in enumerate(as_completed(futures)):
            results.append(fut.result())
            prog.progress((i + 1) / total)
            status.text(f"Scraped {i + 1}/{total}")
    st.success("Scraping complete!")
    df = pd.DataFrame(results)
    for col in ["Product Title","SKU","Seller","Price","Warranty Title","Warranty (Specs)","Warranty Address"]:
        df[col] = df[col].apply(lambda x: x if (isinstance(x, str) and x.strip()) else "Not indicated")
    st.dataframe(df, use_container_width=True)
    @st.cache_data
    def to_excel_bytes(frame: pd.DataFrame) -> bytes:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            frame.to_excel(writer, index=False, sheet_name="Products")
        return buf.getvalue()
    st.download_button(
        "📥 Download Excel", data=to_excel_bytes(df),
        file_name="products.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
