import streamlit as st
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from io import BytesIO
from requests_html import HTMLSession
import json, re, time, random

# -----------------------------
# Config
# -----------------------------
MAX_PAGES = 200
MAX_WORKERS = 8
PAGE_SLEEP = (0.4, 0.9)
REQ_RETRIES = 3
REQ_TIMEOUT = 25
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

scraper = cloudscraper.create_scraper(browser={"custom": HEADERS["User-Agent"]})
html_session = HTMLSession()

# -----------------------------
# Helpers
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
            r.html.render(timeout=30, sleep=2)
            return r
        except Exception:
            pass
    return None

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
                if isinstance(g, dict) and g.get("@type") == "Product":
                    products.append(g)
        if isinstance(obj, dict) and obj.get("@type") == "Product":
            products.append(obj)
        if isinstance(obj, dict) and isinstance(obj.get("mainEntity"), dict):
            me = obj["mainEntity"]
            if me.get("@type") == "Product":
                products.append(me)
    return products

def parse_links_from_grid(soup: BeautifulSoup, base_url: str):
    links = set()
    for a in soup.select("article.prd a.core"):
        href = a.get("href")
        if href:
            links.add(urljoin(base_url, href.split("#")[0]))
    if not links:
        for a in soup.select("a.core"):
            href = a.get("href")
            if href and href.startswith("/"):
                links.add(urljoin(base_url, href.split("#")[0]))
    return links

def parse_links_from_itemlist(soup: BeautifulSoup):
    links = set()
    for obj in all_ldjson_objects(soup):
        if isinstance(obj, dict) and obj.get("@type") in ("ItemList", "BreadcrumbList"):
            for item in obj.get("itemListElement", []):
                if isinstance(item, dict):
                    url = item.get("url") or (item.get("item") or {}).get("url")
                    if url and url.startswith("http"):
                        links.add(url.split("#")[0])
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
    if hasattr(node, "get_text"):
        t = node.get_text(" ", strip=True)
    else:
        t = str(node).strip()
    return t if t else default

def extract_basic_fields(soup: BeautifulSoup, url: str):
    name = "Not indicated"
    price = "Not indicated"
    sku = "Not indicated"
    seller = "Not indicated"

    # JSON-LD first
    products = find_product_objs_from_ldjson(soup)
    if products:
        p = products[0]
        name = p.get("name") or name
        sku = p.get("sku") or sku
        offers = p.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price") or offers.get("priceSpecification", {}).get("price") or price
            sel = offers.get("seller")
            if isinstance(sel, dict):
                seller = sel.get("name") or seller

    # Fallbacks for basic info
    if name == "Not indicated":
        h1 = soup.select_one("h1")
        name = text_or_na(h1)

    if price == "Not indicated":
        price_span = soup.select_one("span.-b")
        price = text_or_na(price_span)

    if sku == "Not indicated":
        for li in soup.select("li"):
            txt = li.get_text(" ", strip=True)
            if re.search(r"\bSKU\b\s*:", txt, re.I):
                sku = txt.split(":", 1)[-1].strip() or "Not indicated"
                break
    
    # Primary fallbacks for Seller
    if seller == "Not indicated":
        sold_by = soup.find(string=re.compile(r"Sold by", re.I))
        if sold_by and sold_by.parent:
            a = sold_by.parent.find_next("a")
            if a:
                seller = text_or_na(a)

    # JS-Render Fallback for lazy-loaded sellers
    if seller == "Not indicated":
        r_js = fetch_with_js(url)
        if r_js:
            seller_node = r_js.html.find('[data-testid="seller-name"]', first=True)
            if seller_node:
                seller_text = seller_node.text.strip()
                if seller_text and seller_text.lower() != "follow":
                    seller = seller_text
    
    # FINAL FALLBACK: Check if it's a Jumia Express item.
    if seller == "Not indicated":
        jumia_express_badge = soup.select_one('img[alt*="Jumia Express"]')
        if jumia_express_badge:
            seller = "Jumia"

    return name, price, sku, seller

def extract_warranty_fields(soup: BeautifulSoup, title_text: str):
    warranty_title = "Not indicated"
    if re.search(r"(warranty|\b\d+\s?(yr|yrs|year|years)\b)", title_text or "", re.I):
        warranty_title = title_text

    warranty_specs = "Not indicated"
    warranty_address = "Not indicated"

    for tr in soup.select("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th: continue
        key = th.get_text(" ", strip=True).lower()
        val = text_or_na(td)
        if "warranty address" in key and warranty_address == "Not indicated":
            warranty_address = val
        elif "warranty" in key and "address" not in key and warranty_specs == "Not indicated":
            warranty_specs = val

    for li in soup.select("div.-pvs ul li, section ul li"):
        raw = li.get_text(" ", strip=True)
        if ":" in raw:
            k, v = raw.split(":", 1)
            key = k.strip().lower()
            val = v.strip() or "Not indicated"
            if "warranty address" in key and warranty_address == "Not indicated":
                warranty_address = val
            elif "warranty" in key and "address" not in key and warranty_specs == "Not indicated":
                warranty_specs = val

    for dt in soup.find_all("dt"):
        key = dt.get_text(" ", strip=True).lower()
        dd = dt.find_next_sibling("dd")
        val = text_or_na(dd)
        if "warranty address" in key and warranty_address == "Not indicated":
            warranty_address = val
        elif "warranty" in key and "address" not in key and warranty_specs == "Not indicated":
            warranty_specs = val

    if warranty_specs == "Not indicated":
        for p in soup.find_all(["p", "li"]):
            txt = p.get_text(" ", strip=True)
            if re.search(r"product warranty|warranty", txt, re.I):
                warranty_specs = txt
                break

    return warranty_title, warranty_specs, warranty_address

def parse_product(url: str):
    r = fetch_with_retry(url)
    if not r:
        return {col: "Error fetching page" for col in
                ["Product Title", "SKU", "Seller", "Price", "Warranty Title", "Warranty (Specs)", "Warranty Address"]} | {"Product URL": url}

    soup = BeautifulSoup(r.text, "lxml")
    name, price, sku, seller = extract_basic_fields(soup, url)
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
st.set_page_config(page_title="Warranty Scraper", layout="wide")
st.title("Warranty Scraper 🌍")
st.caption("Paste a category URL from Jumia or other supported sites.")

category_url = st.text_input("Enter category URL")
go = st.button("Scrape Category")

if go and category_url:
    try:
        parsed_url = urlparse(category_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if not all([parsed_url.scheme, parsed_url.netloc]):
            raise ValueError
    except (ValueError, AttributeError):
        st.error("Please enter a valid category URL.")
        st.stop()

    st.subheader("Step 1 — Collecting product links")
    link_status = st.empty()
    with st.spinner("Collecting product links…"):
        links = get_product_links(category_url, base_url, link_status)
    st.success(f"Found {len(links)} product URLs.")
    if not links:
        st.stop()

    st.subheader("Step 2 — Scraping product pages")
    prog = st.progress(0.0)
    status = st.empty()
    results = []
    total = len(links)
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(parse_product, u): u for u in links}
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            prog.progress(done / total)
            status.text(f"Scraped {done}/{total}")

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
        "📥 Download Excel",
        data=to_excel_bytes(df),
        file_name="products.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
