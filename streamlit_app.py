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
import subprocess
import os

# --- Playwright Imports ---
from playwright.sync_api import sync_playwright

# -----------------------------
# Auto-install Playwright browsers on Streamlit Cloud
# -----------------------------
if "STREAMLIT_CLOUD" in os.environ:
    if not os.path.exists("/home/appuser/.cache/ms-playwright"):
        with st.spinner("Browser setup in progress, this may take a minute..."):
            subprocess.run(["playwright", "install", "--with-deps"], check=True)

# -----------------------------
# Config
# -----------------------------
MAX_PAGES = 200
MAX_WORKERS = 4
PAGE_SLEEP = (0.4, 0.9)

# -----------------------------
# Fetching Helper (Using Playwright)
# -----------------------------
def fetch_with_playwright(url: str):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("article[class*='prd'], a[href$='.html']", timeout=20000)
            html_content = page.content()
            browser.close()
            return html_content
    except Exception as e:
        print(f"Playwright failed for {url}: {e}")
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
                if isinstance(data, list): yield from data
                else: yield data
        except Exception: continue

def find_product_objs_from_ldjson(soup: BeautifulSoup):
    products = []
    for obj in all_ldjson_objects(soup):
        if isinstance(obj, dict) and "@graph" in obj:
            for g in obj.get("@graph", []):
                if isinstance(g, dict) and g.get("@type") == "Product": products.append(g)
        if isinstance(obj, dict) and obj.get("@type") == "Product": products.append(obj)
    return products

def parse_links_from_grid(soup: BeautifulSoup, base_url: str):
    """
    Uses a multi-strategy approach to find product links, making it resilient
    to website layout changes.
    """
    links = set()

    # --- Strategy 1: The most common, modern selector ---
    for a in soup.select("article[class*='-pvl-rect'] a"):
        if href := a.get("href"):
            links.add(urljoin(base_url, href.split("#")[0]))
    if links: return list(links)

    # --- Strategy 2: The original, older selector ---
    for a in soup.select("article.prd a.core"):
        if href := a.get("href"):
            links.add(urljoin(base_url, href.split("#")[0]))
    if links: return list(links)
    
    # --- Strategy 3: Ultimate fallback based on URL structure ---
    # This finds any link that looks like a product page URL and contains a product image
    for a in soup.find_all("a", href=re.compile(r"/.+\.html$")):
        if a.find("img", {"data-src": True}):
            if href := a.get("href"):
                links.add(urljoin(base_url, href.split("#")[0]))
                
    return list(links)

def get_product_links(category_url: str, base_url: str, status_placeholder):
    all_links = set()
    page = 1
    while page <= MAX_PAGES:
        sep = "&" if "?" in category_url else "?"
        page_url = f"{category_url}{sep}page={page}"
        status_placeholder.text(f"Collecting links… page {page}")
        
        html_content = fetch_with_playwright(page_url)
        if not html_content: break
        
        soup = BeautifulSoup(html_content, "lxml")
        found = parse_links_from_grid(soup, base_url)
        
        if not found: break
        
        # Check if we are adding new links to avoid infinite loops on last page
        new_links = set(found) - all_links
        if not new_links: break
        
        all_links.update(new_links)
        page += 1
        time.sleep(random.uniform(*PAGE_SLEEP))
        
    return list(all_links)

def text_or_na(node, default="Not indicated"):
    if not node: return default
    t = node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node).strip()
    return t if t else default

# -----------------------------
# Core Extraction Logic
# -----------------------------
def extract_basic_fields(soup: BeautifulSoup):
    name, price, sku, seller = "Not indicated", "Not indicated", "Not indicated", "Not indicated"
    main_content = soup.find("main", {"role": "main"}) or soup
    products = find_product_objs_from_ldjson(soup)
    if products:
        p = products[0]
        name, sku = p.get("name", name), p.get("sku", sku)
        if isinstance(p.get("offers"), dict):
            price = p["offers"].get("price", price)
            if isinstance(p["offers"].get("seller"), dict): seller = p["offers"]["seller"].get("name", seller)
    if name == "Not indicated": name = text_or_na(main_content.select_one("h1"))
    if price == "Not indicated": price = text_or_na(main_content.select_one("span.-b"))
    if seller == "Not indicated":
        seller_header = main_content.find(lambda t: t.name in ['h2', 'h3'] and 'seller information' in t.text.lower())
        if seller_header and (content_area := seller_header.find_next_sibling()):
            node = content_area.find("a") or content_area.find(['p', 'div', 'h3'])
            if node and "follow" not in (seller_text := text_or_na(node)).lower(): seller = seller_text
    if seller == "Not indicated" and main_content.select_one('img[alt*="Jumia Express"]'): seller = "Jumia"
    return name, price, sku, seller

def extract_warranty_fields(soup: BeautifulSoup, title_text: str):
    warranty_title, warranty_specs, warranty_address = "Not indicated", "Not indicated", "Not indicated"
    main_content = soup.find("main", {"role": "main"}) or soup
    if re.search(r"(warranty|\b\d+\s?yr)", title_text or "", re.I): warranty_title = title_text
    warranty_heading = main_content.find(lambda t: t.name in ['p', 'div', 'span'] and t.get_text(strip=True).lower() == 'warranty')
    if warranty_heading and (detail_node := warranty_heading.find_next_sibling()): warranty_specs = text_or_na(detail_node)
    if warranty_specs == "Not indicated":
        for tr in main_content.select("div.-pdp-add-info tr"):
            cells = tr.find_all("td")
            if len(cells) == 2 and "warranty" in cells[0].get_text(strip=True).lower():
                warranty_specs = cells[1].get_text(strip=True); break
    if warranty_specs == "Not indicated" and (promo := main_content.find(lambda t: re.search(r'\b\d+\s?year.warranty\b', t.text, re.I))):
        warranty_specs = text_or_na(promo)
    return warranty_title, warranty_specs, warranty_address

def parse_product(url: str):
    html_content = fetch_with_playwright(url)
    if not html_content:
        return {col: "Error fetching page" for col in ["Product Title", "SKU", "Seller", "Price", "Warranty Title", "Warranty (Specs)", "Warranty Address"]} | {"Product URL": url}
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
st.title("Definitive Warranty Scraper (Playwright Version) 🎭")
st.caption("This version uses the Playwright browser engine for maximum accuracy. Paste a Jumia category URL.")
category_url = st.text_input("Enter Jumia category URL")
if go := st.button("Scrape Category"):
    try:
        parsed_url = urlparse(category_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if not all([parsed_url.scheme, parsed_url.netloc, "jumia" in base_url]): raise ValueError
    except (ValueError, AttributeError):
        st.error("Please enter a valid Jumia category URL."); st.stop()
    st.subheader("Step 1 — Collecting product links")
    link_status = st.empty()
    with st.spinner("Collecting product links…"):
        links = get_product_links(category_url, base_url, link_status)
    st.success(f"Found {len(links)} product URLs.")
    if not links: st.stop()
    st.subheader("Step 2 — Scraping product pages (using browser engine)")
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
        df[col] = df[col].apply(lambda x: str(x).strip() if x and str(x).strip() else "Not indicated")
    st.dataframe(df, use_container_width=True)
    @st.cache_data
    def to_excel_bytes(frame: pd.DataFrame) -> bytes:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            frame.to_excel(writer, index=False, sheet_name="Products")
        return buf.getvalue()
    st.download_button("📥 Download Excel", to_excel_bytes(df), "jumia_products.xlsx")
