import streamlit as st
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from io import BytesIO
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
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/115.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}

scraper = cloudscraper.create_scraper(browser={"custom": HEADERS["User-Agent"]})

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

def all_ldjson_objects(soup: BeautifulSoup):
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            text = s.string or s.get_text()
            if not text:
                continue
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    yield item
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
        if not r:
            break
        soup = BeautifulSoup(r.text, "lxml")
        grid = parse_links_from_grid(soup, base_url)
        itemlist = parse_links_from_itemlist(soup)
        found = grid | itemlist
        if not found:
            break
        all_links |= found
        page += 1
        time.sleep(random.uniform(*PAGE_SLEEP))
    return list(all_links)

def text_or_na(node, default="Not indicated"):
    if not node:
        return default
    if hasattr(node, "get_text"):
        t = node.get_text(" ", strip=True)
    else:
        t = str(node).strip()
    return t if t else default

# -----------------------------
# Data extraction
# -----------------------------
def extract_basic_fields(soup: BeautifulSoup):
    name = "Not indicated"
    price = "Not indicated"
    sku = "Not indicated"
    seller = "Not indicated"
    seller_source = "Not found"

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
            if isinstance(sel, dict) and sel.get("name"):
                seller = sel.get("name")
                seller_source = "JSON-LD"

    # Fallbacks
    if name == "Not indicated":
        h1 = soup.select_one("h1")
        if h1:
            name = text_or_na(h1)
    if price == "Not indicated":
        price_span = soup.select_one("span.-b")
        if price_span:
            price = text_or_na(price_span)
    if sku == "Not indicated":
        for li in soup.select("li"):
            txt = li.get_text(" ", strip=True)
            if re.search(r"\bSKU\b\s*:", txt, re.I):
                sku = txt.split(":", 1)[-1].strip() or "Not indicated"
                break

    # Improved seller detection
    if seller == "Not indicated":
        seller_label = soup.find(
            lambda tag: tag.name in ['span', 'div', 'p', 'li', 'h2', 'h3']
            and re.search(r"seller|sold by", tag.get_text(strip=True), re.I)
        )
        if seller_label:
            link = seller_label.find_next("a")
            if link:
                seller = text_or_na(link)
                seller_source = "HTML label + link"
            else:
                next_text = seller_label.find_next(string=True)
                if next_text and next_text.strip():
                    seller = next_text.strip()
                    seller_source = "HTML label + sibling text"

    if seller == "Not indicated" or seller.lower() == 'follow':
        seller_header = soup.find(
            lambda tag: tag.name in ['h2', 'h3'] and 'seller information' in tag.get_text(strip=True).lower()
        )
        if seller_header:
            content_area = seller_header.find_next_sibling()
            if content_area:
                seller_link = content_area.find("a")
                if seller_link:
                    link_text = text_or_na(seller_link, default="")
                    if "follow" not in link_text.lower():
                        seller = link_text
                        seller_source = "Seller information block"

    return name, price, sku, seller, seller_source

def extract_warranty_fields(soup: BeautifulSoup, title_text: str):
    warranty_title = "Not indicated"
    warranty_specs = "Not indicated"
    warranty_address = "Not indicated"
    warranty_source = []

    if re.search(r"(warranty|\b\d+\s?(yr|yrs|year|years)\b)", title_text or "", re.I):
        warranty_title = title_text
        warranty_source.append("Title")

    for tr in soup.select("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th:
            continue
        key = th.get_text(" ", strip=True).lower()
        val = text_or_na(td)
        if "warranty address" in key and warranty_address == "Not indicated":
            warranty_address = val
            warranty_source.append("Table: warranty address")
        elif "warranty" in key and "address" not in key and warranty_specs == "Not indicated":
            warranty_specs = val
            warranty_source.append("Table: warranty specs")

    for li in soup.select("div.-pvs ul li, section ul li"):
        raw = li.get_text(" ", strip=True)
        if ":" in raw:
            k, v = raw.split(":", 1)
            key = k.strip().lower()
            val = v.strip() or "Not indicated"
            if "warranty address" in key and warranty_address == "Not indicated":
                warranty_address = val
                warranty_source.append("List: warranty address")
            elif "warranty" in key and "address" not in key and warranty_specs == "Not indicated":
                warranty_specs = val
                warranty_source.append("List: warranty specs")

    for dt in soup.find_all("dt"):
        key = dt.get_text(" ", strip=True).lower()
        dd = dt.find_next_sibling("dd")
        val = text_or_na(dd)
        if "warranty address" in key and warranty_address == "Not indicated":
            warranty_address = val
            warranty_source.append("Definition list: warranty address")
        elif "warranty" in key and "address" not in key and warranty_specs == "Not indicated":
            warranty_specs = val
            warranty_source.append("Definition list: warranty specs")

    if warranty_specs == "Not indicated":
        for p in soup.find_all(["p", "li"]):
            txt = p.get_text(" ", strip=True)
            if re.search(r"product warranty|warranty", txt, re.I):
                warranty_specs = txt
                warranty_source.append("Paragraph fallback")
                break

    return warranty_title, warranty_specs, warranty_address, ", ".join(warranty_source) or "Not found"

def parse_product(url: str):
    r = fetch_with_retry(url)
    if not r:
        return {
            "Product Title": "Error fetching page",
            "SKU": "Not indicated",
            "Seller": "Not indicated",
            "Seller Source": "Not found",
            "Price": "Not indicated",
            "Warranty Title": "Not indicated",
            "Warranty (Specs)": "Not indicated",
            "Warranty Address": "Not indicated",
            "Warranty Source": "Not found",
            "Product URL": url,
        }
    soup = BeautifulSoup(r.text, "lxml")
    name, price, sku, seller, seller_source = extract_basic_fields(soup)
    w_title, w_specs, w_addr, w_source = extract_warranty_fields(soup, name)
    return {
        "Product Title": name or "Not indicated",
        "SKU": sku or "Not indicated",
        "Seller": seller or "Not indicated",
        "Seller Source": seller_source,
        "Price": price or "Not indicated",
        "Warranty Title": w_title or "Not indicated",
        "Warranty (Specs)": w_specs or "Not indicated",
        "Warranty Address": w_addr or "Not indicated",
        "Warranty Source": w_source,
        "Product URL": url,
    }

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Scraper", layout="wide")
st.title("Warranty Scraper 🌍")
st.caption("Paste a category URL from any Jumia country. The app will detect the site and scrape warranty/seller data with source tracking.")

category_url = st.text_input("Enter category URL (e.g., https://www.jumia.ug/laptops/)")
go = st.button("Scrape Category")

if go and category_url:
    try:
        parsed_url = urlparse(category_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if not all([parsed_url.scheme, parsed_url.netloc, "jumia" in parsed_url.netloc]):
            raise ValueError
        st.info(f"Detected Jumia site: **{base_url}**")
    except (ValueError, AttributeError):
        st.error("Please enter a valid Jumia category URL.")
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

    def worker(u):
        return parse_product(u)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(worker, u): u for u in links}
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
            frame.to_excel(writer, index=False, sheet_name="Jumia_Products")
        return buf.getvalue()

    st.download_button(
        "📥 Download Excel",
        data=to_excel_bytes(df),
        file_name="jumia_products.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
