import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Defacto Product Mapper", page_icon="🗂️", layout="wide")

# ── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #f7f8fa; }
.block-container { padding-top: 2rem; }
.stButton>button { background:#1e3a5f; color:white; border-radius:8px;
                   padding:.45rem 1.4rem; font-weight:600; border:none; }
.stButton>button:hover { background:#2a4f82; }
.upload-card { background:white; border-radius:12px; padding:1.2rem 1.5rem;
               box-shadow:0 1px 4px rgba(0,0,0,.08); margin-bottom:1rem; }
.metric-box  { background:white; border-radius:10px; padding:1rem 1.4rem;
               box-shadow:0 1px 4px rgba(0,0,0,.08); text-align:center; }
.tag-miss { color:#b91c1c; font-weight:600; }
.tag-ok   { color:#166534; font-weight:600; }
</style>
""", unsafe_allow_html=True)

st.title("🗂️ Defacto → Template Mapper")
st.caption("Upload your source product file, the output template, and the category map to generate a ready-to-import CSV.")

# ── Sidebar: fixed-value overrides ───────────────────────────────────────────
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
    cost_pct        = st.slider("Cost = Price × %", 50, 100, 80,
                                 help="Estimated cost as % of RRP when cost is not in source")

# ── File uploads ──────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    st.subheader("📦 Source File")
    st.caption("The supplier product export (.xlsx)")
    src_file = st.file_uploader("Source file", type=["xlsx","xls"], key="src",
                                 label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    st.subheader("📄 Output Template")
    st.caption("The target template (.csv) that defines required columns")
    tpl_file = st.file_uploader("Template", type=["csv","xlsx"], key="tpl",
                                 label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

with col3:
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    st.subheader("🏷️ Category Map")
    st.caption("Lookup table: name → category ID (.xlsx)")
    cat_file = st.file_uploader("Category map", type=["xlsx","xls"], key="cat",
                                 label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

# ── Helper ────────────────────────────────────────────────────────────────────
def load_file(f):
    if f is None:
        return None
    name = f.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(f)
    return pd.read_excel(f)


def build_short_description(row):
    parts = []
    for label, col in [("Gender", "Gender"), ("Category", "Class"),
                       ("Colour Family", "Color Family"), ("Material", "Material")]:
        val = row.get(col, "")
        if pd.notna(val) and str(val).strip():
            parts.append(f"<li>{label}: {val}</li>")
    return "<ul> " + " ".join(parts) + " </ul>" if parts else ""


def build_description(row):
    title   = row.get("Title", "Product")
    gender  = row.get("Gender", "")
    cls     = row.get("Class", "")
    color   = row.get("Color Name", "")
    mat     = row.get("Material", "")
    desc = (
        f"<p><strong>{brand} {title}</strong> is designed for comfort and style.</p>"
        f"<h2>Features</h2><ul>"
        f"<li><strong>Gender</strong>: {gender}</li>"
        f"<li><strong>Category</strong>: {cls}</li>"
        f"<li><strong>Colour</strong>: {color}</li>"
        f"<li><strong>Material</strong>: {mat}</li>"
        f"</ul>"
    )
    return desc


def map_gender(val):
    if pd.isna(val):
        return ""
    v = str(val).strip().lower()
    mapping = {
        "girl": "Girls", "girls": "Girls",
        "boy": "Boys",  "boys":  "Boys",
        "baby girl": "Baby Girls", "babygirl": "Baby Girls",
        "baby boy":  "Baby Boys",  "babyboy":  "Baby Boys",
        "women": "Women", "woman": "Women", "female": "Women",
        "men": "Men", "man": "Men", "male": "Men",
        "unisex": "Unisex",
    }
    return mapping.get(v, str(val).strip())


# ── Main logic ────────────────────────────────────────────────────────────────
if src_file and tpl_file and cat_file:

    with st.spinner("Loading files…"):
        src = load_file(src_file)
        tpl = load_file(tpl_file)
        cats = load_file(cat_file)

    # ── Show column detection ──────────────────────────────────────────────
    with st.expander("🔍 Detected Columns", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Source columns**"); st.write(src.columns.tolist())
        with c2:
            st.write("**Template columns**"); st.write(tpl.columns.tolist())
        with c3:
            st.write("**Category map columns**"); st.write(cats.columns.tolist())

    # ── Build category lookup (name → categories value) ───────────────────
    # cats.xlsx: columns: name, category, categories
    cat_name_col = "name"
    cat_id_col   = "categories"
    cat_lookup = {}
    if cat_name_col in cats.columns and cat_id_col in cats.columns:
        for _, row in cats.iterrows():
            key = str(row[cat_name_col]).strip().lower()
            val = str(row[cat_id_col]).strip()
            if key not in cat_lookup:        # keep first match
                cat_lookup[key] = val

    # ── Identify source columns ────────────────────────────────────────────
    # The source file sometimes has "Unnamed: 1" as the full SKU string
    sku_col = "Unnamed: 1" if "Unnamed: 1" in src.columns else None

    def get_sku(row):
        """Return the full SKU string, fallback to barcode."""
        if sku_col and pd.notna(row.get(sku_col, None)):
            return str(row[sku_col]).strip()
        return str(row.get("Barcode", "")).strip()

    def lookup_category(class_val):
        if pd.isna(class_val):
            return ""
        return cat_lookup.get(str(class_val).strip().lower(), "")

    # ── Map rows ───────────────────────────────────────────────────────────
    records = []
    missing_cats = set()

    for _, row in src.iterrows():
        barcode  = str(row.get("Barcode", "")).strip()
        sku      = get_sku(row)
        sku_star = sku + "*" if not sku.endswith("*") else sku
        title    = str(row.get("Title", "")).strip()
        rrp      = row.get("RRP", None)
        cat_raw  = row.get("Class", "")
        cat_id   = lookup_category(cat_raw)
        if not cat_id:
            missing_cats.add(str(cat_raw))
        short_d  = build_short_description(row)
        desc     = build_description(row)
        gender   = map_gender(row.get("Gender", ""))
        size     = str(row.get("Size", "")).strip() if pd.notna(row.get("Size","")) else ""
        color    = str(row.get("Color Name","")).strip() if pd.notna(row.get("Color Name","")) else ""
        material = str(row.get("Material","")).strip() if pd.notna(row.get("Material","")) else ""

        # Images
        img_cols = [c for c in src.columns if "web image link" in c.lower()]
        images = [str(row[c]).strip() for c in img_cols
                  if pd.notna(row.get(c)) and str(row[c]).strip() not in ("","nan")]

        records.append({
            "sku_supplier_config":  sku_star,
            "name":                 title,
            "name_ar_EG":           title,
            "brand":                brand,
            "short_description_ar_EG": short_d,
            "short_description":    short_d,
            "description":          desc,
            "description_ar_EG":    desc,
            "categories":           cat_id,
            "brand_type":           brand_type,
            "model":                sku,
            "supplier_type":        supplier_type,
            "product_weight":       prod_weight,
            "package_type":         pkg_type,
            "min_delivery_time":    min_del,
            "max_delivery_time":    max_del,
            "size":                 size,
            "gender":               gender,
            "supplier_simple":      supplier_simple,
            "price":                rrp,
            "tax_class":            tax_class,
            "purchase_tax_class":   purchase_tax,
            "cost":                 round(float(rrp) * cost_pct / 100, 2) if rrp and str(rrp) not in ("","nan") else "",
            "color":                color,
            "main_material":        material,
            "status_source":        status,
            "gtin_barcode":         barcode,
            "sku_supplier_source":  sku_star,
            "supplier":             supplier,
            "shipment_type":        shipment_type,
            "seller_sku":           sku_star,
            "shop_type":            shop_type,
            "product_warranty":     "",
        })

    out_df = pd.DataFrame(records)

    # Keep only columns that exist in the template
    tpl_cols = tpl.columns.tolist()
    final_cols = [c for c in tpl_cols if c in out_df.columns]
    extra_cols = [c for c in out_df.columns if c not in tpl_cols]
    out_df = out_df[final_cols]  # order matches template

    # ── Stats ──────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Mapping Summary")
    m1, m2, m3, m4 = st.columns(4)
    mapped_cats = out_df[out_df["categories"].str.strip() != ""].shape[0] if "categories" in out_df.columns else 0
    with m1:
        st.metric("Total Rows", f"{len(out_df):,}")
    with m2:
        st.metric("Template Columns", f"{len(final_cols)}")
    with m3:
        st.metric("Rows with Category", f"{mapped_cats:,}")
    with m4:
        pct = round(100 * mapped_cats / len(out_df), 1) if len(out_df) else 0
        st.metric("Category Match %", f"{pct}%")

    # ── Missing categories warning ─────────────────────────────────────────
    if missing_cats:
        with st.expander(f"⚠️ {len(missing_cats)} Class value(s) not found in category map", expanded=False):
            st.info("These 'Class' values from the source had no match in the category map. "
                    "Their 'categories' column will be empty. You can add them manually or update the category map.")
            st.dataframe(pd.DataFrame(sorted(missing_cats), columns=["Unmatched Class Values"]),
                         use_container_width=True)

    # ── Preview ────────────────────────────────────────────────────────────
    st.subheader("👁️ Preview (first 50 rows)")
    preview_cols = ["sku_supplier_config","name","gender","size","color",
                    "categories","price","cost","main_material","status_source"]
    preview_cols = [c for c in preview_cols if c in out_df.columns]
    st.dataframe(out_df[preview_cols].head(50), use_container_width=True)

    # ── Download ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("⬇️ Download")
    col_a, col_b = st.columns(2)

    csv_buf = io.StringIO()
    out_df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue().encode("utf-8-sig")   # utf-8-sig for Excel compat

    xlsx_buf = io.BytesIO()
    with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
        out_df.to_excel(writer, index=False, sheet_name="Mapped")
    xlsx_bytes = xlsx_buf.getvalue()

    with col_a:
        st.download_button("📥 Download CSV",  data=csv_bytes,
                           file_name="mapped_products.csv",
                           mime="text/csv", use_container_width=True)
    with col_b:
        st.download_button("📥 Download XLSX", data=xlsx_bytes,
                           file_name="mapped_products.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

    # ── Category map explorer ──────────────────────────────────────────────
    with st.expander("📖 Browse Category Map", expanded=False):
        search = st.text_input("Search category name…")
        disp = cats[cats[cat_name_col].str.contains(search, case=False, na=False)] if search else cats.head(100)
        st.dataframe(disp, use_container_width=True)

else:
    st.info("👆 Please upload all three files above to begin mapping.")

    with st.expander("ℹ️ How the mapping works"):
        st.markdown("""
| Source Column | → | Template Column | Notes |
|---|---|---|---|
| `Barcode` | → | `gtin_barcode`, `sku_supplier_config`, `sku_supplier_source`, `seller_sku` | `*` appended to SKU fields |
| `Title` | → | `name`, `name_ar_EG` | |
| `RRP` | → | `price` | |
| `Color Name` | → | `color` | |
| `Material` | → | `main_material` | |
| `Size` | → | `size` | |
| `Gender` | → | `gender` | Normalised to standard labels |
| `Class` | → | `categories` | Looked up in category map file |
| `Unnamed: 1` | → | `model` | Full SKU string |
| `Web Image Link 1–5` | — | *(not in template)* | Available if template is extended |

**Descriptions** are auto-generated from product attributes.  
**Cost** is estimated as a % of RRP (configurable in the sidebar).  
**Fixed values** (brand, supplier, tax class, etc.) are set in the sidebar.
        """)
