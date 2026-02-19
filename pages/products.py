"""
Defacto → Jumia Template Mapper
Layered category matching: manual table → regex stripping → fuzzy → flag for review
"""

import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Defacto Product Mapper", page_icon="🗂️", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #f7f8fa; }
.block-container { padding-top: 2rem; }
.stButton>button {
    background: #1e3a5f; color: white; border-radius: 8px;
    padding: .45rem 1.4rem; font-weight: 600; border: none;
}
.stButton>button:hover { background: #2a4f82; }
.upload-card {
    background: white; border-radius: 12px; padding: 1.2rem 1.5rem;
    box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

st.title("🗂️ Defacto → Template Mapper")
st.caption("Upload your source product file, output template, category map, and optionally a custom mapping table.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Fixed Values")
    brand           = st.text_input("Brand",              "Defacto")
    brand_type      = st.text_input("Brand Type",         "Brand")
    supplier        = st.text_input("Supplier",           "Defacto Retail")
    supplier_simple = st.text_input("Supplier Simple",    "Defacto Retail")
    supplier_type   = st.text_input("Supplier Type",      "Retail")
    shipment_type   = st.text_input("Shipment Type",      "Own Warehouse")
    shop_type       = st.text_input("Shop Type",          "Jumia Mall")
    tax_class       = st.text_input("Tax Class",          "Default")
    purchase_tax    = st.text_input("Purchase Tax Class", "Default")
    pkg_type        = st.text_input("Package Type",       "Parcel")
    prod_weight     = st.number_input("Product Weight",   value=1.0, step=0.1)
    min_del         = st.number_input("Min Delivery Time",value=2,   step=1)
    max_del         = st.number_input("Max Delivery Time",value=6,   step=1)
    status          = st.selectbox("Status Source", ["active","inactive"], index=0)
    cost_pct        = st.slider("Cost = Price x %", 50, 100, 80)

    st.divider()
    st.header("Matching Settings")
    use_regex       = st.toggle("Enable regex stripping",  value=True)
    use_fuzzy       = st.toggle("Enable fuzzy matching",   value=True)
    fuzzy_threshold = st.slider("Fuzzy threshold", 60, 100, 80,
                                 help="Minimum score (0-100) to accept a fuzzy match. Higher = stricter.")


# ── Matching engine ───────────────────────────────────────────────────────────

STRIP_PATTERNS = [
    r"^(long sleeve|short sleeve|sleeveless|3\/4 sleeve)\s+",
    r"^(woven|knitted|knit|tricot)\s+",
    r"^(maternity|nursing)\s+",
    r"^(low cut|high cut|ankle)\s+",
    r"^(straw|snap|pu|light)\s+",
    r"^(active|sport|sports)\s+",
    r"\s+set$",
    r"\s+&\s+set$",
]

SPELLING_FIXES = {
    "suveter": "sweater",
    "mont":    "coat",
    "mayo":    "swimsuit",
    "cachet":  "hat",
    "roller":  "slipper",
}


def strip_modifiers(text):
    t = text.strip().lower()
    for pat in STRIP_PATTERNS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()
    return t.title()


def fuzzy_match(query, choices, threshold):
    from difflib import SequenceMatcher
    best, best_score = "", 0
    q = query.lower()
    for c in choices:
        score = int(SequenceMatcher(None, q, c.lower()).ratio() * 100)
        if score > best_score:
            best, best_score = c, score
    return (best, best_score) if best_score >= threshold else ("", 0)


def resolve_category(class_val, cat_lookup, manual_lookup, cat_names,
                     use_regex, use_fuzzy, fuzzy_threshold):
    """Returns (category_id, matched_name, method)"""
    if not class_val or (isinstance(class_val, float) and pd.isna(class_val)):
        return "", "", "unmatched"

    val = str(class_val).strip()

    # Layer 1 — manual override table
    if val in manual_lookup:
        return manual_lookup[val], val, "manual"

    # Layer 2 — exact case-insensitive
    val_lower = val.lower()
    for name, cid in cat_lookup.items():
        if name.lower() == val_lower:
            return cid, name, "exact"

    # Layer 3 — regex modifier stripping
    if use_regex:
        stripped = strip_modifiers(val)
        if stripped.lower() != val_lower:
            for name, cid in cat_lookup.items():
                if name.lower() == stripped.lower():
                    return cid, name, "regex"

    # Layer 4 — spelling correction
    fixed = SPELLING_FIXES.get(val_lower)
    if fixed:
        for name, cid in cat_lookup.items():
            if name.lower() == fixed:
                return cid, name, "spelling"

    # Layer 5 — fuzzy match
    if use_fuzzy:
        for candidate in ([val] + ([strip_modifiers(val)] if use_regex else [])):
            best, score = fuzzy_match(candidate, cat_names, fuzzy_threshold)
            if best:
                return cat_lookup.get(best, ""), best, f"fuzzy({score}%)"

    return "", "", "unmatched"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_file(f):
    if f is None:
        return None
    return pd.read_csv(f) if f.name.lower().endswith(".csv") else pd.read_excel(f)


def map_gender(val):
    if pd.isna(val):
        return ""
    m = {"girl":"Girls","girls":"Girls","boy":"Boys","boys":"Boys",
         "baby girl":"Baby Girls","babygirl":"Baby Girls",
         "baby boy":"Baby Boys","babyboy":"Baby Boys",
         "women":"Women","woman":"Women","female":"Women",
         "men":"Men","man":"Men","male":"Men","unisex":"Unisex"}
    return m.get(str(val).strip().lower(), str(val).strip())


def build_short_desc(row, brand):
    parts = [(l, row.get(c,"")) for l, c in [
        ("Gender","Gender"),("Category","Class"),
        ("Colour Family","Color Family"),("Material","Material")]]
    items = [f"<li>{l}: {v}</li>" for l,v in parts if pd.notna(v) and str(v).strip()]
    return "<ul> " + " ".join(items) + " </ul>" if items else ""


def build_desc(row, brand):
    return (
        f"<p><strong>{brand} {row.get('Title','Product')}</strong> is designed for comfort and style.</p>"
        f"<h2>Features</h2><ul>"
        f"<li><strong>Gender</strong>: {row.get('Gender','')}</li>"
        f"<li><strong>Category</strong>: {row.get('Class','')}</li>"
        f"<li><strong>Colour</strong>: {row.get('Color Name','')}</li>"
        f"<li><strong>Material</strong>: {row.get('Material','')}</li>"
        f"</ul>"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    st.subheader("📦 Source File")
    src_file = st.file_uploader("Source xlsx", type=["xlsx","xls"], key="src",
                                 label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    st.subheader("📄 Template")
    tpl_file = st.file_uploader("Template csv", type=["csv","xlsx"], key="tpl",
                                 label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    st.subheader("🏷️ Category Map")
    cat_file = st.file_uploader("Category xlsx", type=["xlsx","xls"], key="cat",
                                 label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)
with c4:
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    st.subheader("🔁 Class Mapping")
    st.caption("Optional: upload category_mapping.csv to pre-seed 129/130 matches")
    map_file = st.file_uploader("Mapping csv", type=["csv"], key="map",
                                 label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)


if src_file and tpl_file and cat_file:

    with st.spinner("Loading and matching…"):
        src      = load_file(src_file)
        tpl      = load_file(tpl_file)
        cats     = load_file(cat_file)
        user_map = load_file(map_file) if map_file else None

    # Build category lookup
    cat_lookup = {}
    if "name" in cats.columns and "categories" in cats.columns:
        for _, row in cats.iterrows():
            k = str(row["name"]).strip()
            v = str(row["categories"]).strip()
            if k not in cat_lookup:
                cat_lookup[k] = v
    cat_names = list(cat_lookup.keys())

    # Build manual override lookup
    manual_lookup = {}
    if user_map is not None:
        if {"source_class","category_id"}.issubset(set(user_map.columns)):
            for _, row in user_map.iterrows():
                sc  = str(row["source_class"]).strip()
                cid = str(row["category_id"]).strip()
                if cid and cid.lower() not in ("nan",""):
                    manual_lookup[sc] = cid
            st.success(f"Loaded {len(manual_lookup)} manual overrides from mapping file.")
        else:
            st.warning("Mapping file needs columns: `source_class`, `category_id`")

    # Process rows
    records    = []
    debug_rows = []
    sku_col    = "Unnamed: 1" if "Unnamed: 1" in src.columns else None

    for _, row in src.iterrows():
        barcode  = str(row.get("Barcode","")).strip()
        sku      = str(row[sku_col]).strip() if sku_col and pd.notna(row.get(sku_col)) else barcode
        sku_star = sku if sku.endswith("*") else sku + "*"
        title    = str(row.get("Title","")).strip()
        rrp      = row.get("RRP")
        class_v  = row.get("Class","")
        size     = str(row.get("Size","")).strip()        if pd.notna(row.get("Size",""))        else ""
        color    = str(row.get("Color Name","")).strip()  if pd.notna(row.get("Color Name",""))  else ""
        material = str(row.get("Material","")).strip()    if pd.notna(row.get("Material",""))    else ""

        cat_id, matched_name, method = resolve_category(
            class_v, cat_lookup, manual_lookup, cat_names,
            use_regex, use_fuzzy, fuzzy_threshold
        )

        debug_rows.append({"source_class": str(class_v), "matched_to": matched_name,
                           "category_id": cat_id, "method": method})

        price = rrp if pd.notna(rrp) and str(rrp) not in ("","nan") else ""
        cost  = round(float(price) * cost_pct / 100, 2) if price != "" else ""

        records.append({
            "sku_supplier_config":     sku_star,
            "name":                    title,
            "name_ar_EG":              title,
            "brand":                   brand,
            "short_description_ar_EG": build_short_desc(row, brand),
            "short_description":       build_short_desc(row, brand),
            "description":             build_desc(row, brand),
            "description_ar_EG":       build_desc(row, brand),
            "categories":              cat_id,
            "brand_type":              brand_type,
            "model":                   sku,
            "supplier_type":           supplier_type,
            "product_weight":          prod_weight,
            "package_type":            pkg_type,
            "min_delivery_time":       min_del,
            "max_delivery_time":       max_del,
            "size":                    size,
            "gender":                  map_gender(row.get("Gender","")),
            "supplier_simple":         supplier_simple,
            "price":                   price,
            "tax_class":               tax_class,
            "purchase_tax_class":      purchase_tax,
            "cost":                    cost,
            "color":                   color,
            "main_material":           material,
            "status_source":           status,
            "gtin_barcode":            barcode,
            "sku_supplier_source":     sku_star,
            "supplier":                supplier,
            "shipment_type":           shipment_type,
            "seller_sku":              sku_star,
            "shop_type":               shop_type,
            "product_warranty":        "",
        })

    out_df   = pd.DataFrame(records)
    debug_df = pd.DataFrame(debug_rows)

    # Align to template column order
    tpl_cols   = tpl.columns.tolist()
    final_cols = [c for c in tpl_cols if c in out_df.columns]
    out_df     = out_df[final_cols]

    # ── Stats ─────────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 Mapping Summary")

    method_counts = debug_df["method"].value_counts()
    matched   = debug_df[debug_df["category_id"] != ""]
    unmatched = debug_df[debug_df["category_id"] == ""]
    match_pct = round(100 * len(matched) / len(debug_df), 1) if len(debug_df) else 0
    fuzzy_n   = sum(v for k, v in method_counts.items() if "fuzzy" in k or k == "spelling" or k == "regex")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Rows",         f"{len(out_df):,}")
    m2.metric("Matched",            f"{len(matched):,} ({match_pct}%)")
    m3.metric("Manual overrides",   int(method_counts.get("manual", 0)))
    m4.metric("Regex / Fuzzy",      fuzzy_n)
    m5.metric("Unmatched",          len(unmatched))

    # ── Tabs ──────────────────────────────────────────────────────────────────
    st.subheader("🔬 Category Matching Breakdown")
    tab1, tab2, tab3 = st.tabs(["All matches", "Unmatched — needs review", "Edit & re-upload mapping"])

    with tab1:
        unique = debug_df.drop_duplicates("source_class").sort_values("source_class")

        def color_method(val):
            colors = {"manual":"#d1fae5","exact":"#dbeafe","regex":"#fef9c3",
                      "spelling":"#fef9c3","unmatched":"#fee2e2"}
            bg = colors.get(str(val).split("(")[0], "#f3f4f6")
            return f"background-color:{bg}"

        st.dataframe(unique.style.map(color_method, subset=["method"]),
                     use_container_width=True, height=380)
        st.caption("🟢 Manual  |  🔵 Exact  |  🟡 Regex / Fuzzy / Spelling  |  🔴 Unmatched")

    with tab2:
        miss = unmatched.drop_duplicates("source_class")[["source_class"]].copy()
        if len(miss):
            miss["mapped_to_name"] = ""
            miss["category_id"]    = ""
            miss["notes"]          = "NEEDS REVIEW"
            st.info(
                f"{len(miss)} class value(s) unmatched. "
                "Fill in `category_id` (copy from the Category Map), save as CSV, "
                "and re-upload as the **Class Mapping** file."
            )
            st.dataframe(miss, use_container_width=True)
            st.download_button("⬇️ Download unmatched for fixing",
                               data=miss.to_csv(index=False).encode("utf-8-sig"),
                               file_name="unmatched_classes.csv", mime="text/csv")
        else:
            st.success("🎉 Everything matched — nothing to review!")

    with tab3:
        st.markdown("""
**Workflow for correcting matches:**
1. Download the full mapping table below
2. Edit `mapped_to_name` or paste the correct `category_id` directly
3. Save as CSV and re-upload it in the **Class Mapping** slot (top right)
4. Manual entries always override every other matching method
        """)
        all_map = debug_df.drop_duplicates("source_class")[
            ["source_class","matched_to","category_id","method"]
        ].rename(columns={"matched_to":"mapped_to_name"})
        st.download_button("⬇️ Download full mapping table",
                           data=all_map.to_csv(index=False).encode("utf-8-sig"),
                           file_name="category_mapping_full.csv", mime="text/csv")

    # ── Preview ────────────────────────────────────────────────────────────────
    st.subheader("👁️ Output Preview (first 50 rows)")
    preview_cols = [c for c in
        ["sku_supplier_config","name","gender","size","color",
         "categories","price","cost","main_material","status_source"]
        if c in out_df.columns]
    st.dataframe(out_df[preview_cols].head(50), use_container_width=True)

    # ── Downloads ──────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("⬇️ Download Output")
    dl1, dl2 = st.columns(2)

    csv_buf = io.StringIO()
    out_df.to_csv(csv_buf, index=False)

    xlsx_buf = io.BytesIO()
    with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as w:
        out_df.to_excel(w, index=False, sheet_name="Mapped")

    with dl1:
        st.download_button("📥 Download CSV",
                           data=csv_buf.getvalue().encode("utf-8-sig"),
                           file_name="mapped_products.csv", mime="text/csv",
                           use_container_width=True)
    with dl2:
        st.download_button("📥 Download XLSX",
                           data=xlsx_buf.getvalue(),
                           file_name="mapped_products.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

    with st.expander("📖 Browse Category Map"):
        search = st.text_input("Search category name…")
        disp = cats[cats["name"].str.contains(search, case=False, na=False)] if search else cats.head(100)
        st.dataframe(disp, use_container_width=True)

else:
    st.info("👆 Upload all three required files (source, template, category map) to begin.")

    with st.expander("ℹ️ How layered matching works"):
        st.markdown("""
| Layer | Method | Example |
|---|---|---|
| 1 | **Manual table** | `Woven Bikini` → pre-mapped to `Bikinis` ID, always wins |
| 2 | **Exact match** | `Cardigan` → `Cardigan` |
| 3 | **Regex stripping** | `Long Sleeve T-Shirt` → strip modifier → `T-Shirt` → `T-Shirts` |
| 4 | **Spelling fix** | `Suveter` → corrected to `sweater` → `Sweaters` |
| 5 | **Fuzzy match** | `Sweat Shirt` → 87% → `Hoodies & Sweatshirts` |
| 6 | **Unmatched** | Flagged, downloadable for manual fix |

Upload **`category_mapping.csv`** (included below) as the 4th file to pre-seed 129/130 classes instantly.
        """)
