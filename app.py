import streamlit as st
import pandas as pd
from datetime import datetime
import jdatetime
import gspread
from google.oauth2.service_account import Credentials
import base64
import io
import json
import copy
from PIL import Image

# تنظیمات اولیه صفحه
st.set_page_config(
    page_title="مدیریت سفارش‌ها و تقویم ظرفیت (شمسی ابری)",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# استایل اختصاصی راست‌‌چین (RTL) و کارت‌های مدرن + حل تداخل آیکون‌های Expander
st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');
    
    html, body, [class*="css"], div, p, span, h1, h2, h3, h4, h5, h6, input, select, textarea, button {
        font-family: 'Vazirmatn', sans-serif !important;
    }
    
    [data-testid="stIconMaterial"], .material-symbols-rounded, .material-symbols-outlined {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
        direction: ltr !important;
    }
    
    .stApp {
        direction: rtl;
        text-align: right;
    }

    .stButton>button {
        border-radius: 10px;
        transition: all 0.3s ease;
    }

    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 14px 16px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        text-align: center;
        margin-bottom: 10px;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #718096;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 1.25rem;
        font-weight: bold;
        color: #2d3748;
    }
    
    .order-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px 12px 0 0;
        padding: 18px 18px 12px 18px;
        border-right: 6px solid #3182ce;
        border-bottom: 1px dashed #e2e8f0;
    }
    .order-steps-container {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-top: none;
        border-radius: 0 0 12px 12px;
        border-right: 6px solid #3182ce;
        padding: 8px 16px 4px 16px;
        margin-bottom: 16px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03);
    }

    .calendar-cell {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 8px;
        min-height: 110px;
        margin-bottom: 8px;
        background-color: #ffffff;
        transition: all 0.2s ease;
    }
    .calendar-cell:hover {
        border-color: #3182ce;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    .cell-today {
        border: 2px solid #3182ce !important;
        background-color: #ebf8ff;
    }
    .cell-full {
        border-right: 5px solid #e53e3e !important;
        background-color: #fff5f5;
    }
    .cell-available {
        border-right: 5px solid #38a169 !important;
        background-color: #f0fff4;
    }
    .day-num {
        font-weight: bold;
        font-size: 1.05rem;
        margin-bottom: 4px;
        color: #2d3748;
    }
    .order-badge {
        font-size: 0.72rem;
        padding: 2px 6px;
        border-radius: 4px;
        margin-top: 3px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        display: block;
    }
    .badge-paid {
        background-color: #bee3f8;
        color: #2b6cb0;
    }
    .badge-debt {
        background-color: #feebc8;
        color: #c05621;
    }

    div[data-testid="stExpander"] {
        border: 1px solid #cbd5e1 !important;
        border-radius: 12px !important;
        background: #ffffff !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03) !important;
        margin-top: 15px !important;
        overflow: hidden;
    }
    div[data-testid="stExpander"] summary {
        direction: rtl !important;
        text-align: right !important;
        display: flex !important;
        flex-direction: row-reverse !important;
        justify-content: space-between !important;
        align-items: center !important;
        padding: 12px 18px !important;
        font-weight: bold !important;
        color: #334155 !important;
    }
    div[data-testid="stExpander"] summary svg {
        margin: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

DAILY_CAPACITY_LIMIT = 5

def parse_int_price(val):
    if not val or pd.isna(val):
        return 0
    clean_str = str(val).replace(",", "").replace("،", "").strip()
    try:
        return int(round(float(clean_str)))
    except Exception:
        return 0

def clean_phone_str(val):
    if not val or pd.isna(val):
        return ""
    val_str = str(val).split(".")[0].strip()
    return "" if val_str.lower() == "nan" else val_str

def _is_truthy(val):
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ["true", "1", "yes"]

def compress_image_to_base64(uploaded_file, max_size=(350, 350), quality=55):
    try:
        img = Image.open(uploaded_file)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception:
        return ""

# ----------------- ارتباط با Google Sheets -----------------
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials_dict = dict(st.secrets["connections"]["gsheets"])
    if "private_key" in credentials_dict:
        credentials_dict["private_key"] = credentials_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(creds)

def get_worksheet():
    gc = get_gspread_client()
    target = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    sh = gc.open_by_url(target) if target.startswith("http") else gc.open_by_key(target)
    try:
        return sh.worksheet("orders")
    except Exception:
        return sh.get_worksheet(0)

def get_pricing_worksheet():
    gc = get_gspread_client()
    target = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    sh = gc.open_by_url(target) if target.startswith("http") else gc.open_by_key(target)
    for sheet_name in ["آنالیز جامع", "pricing", "قیمت", "محصولات"]:
        try:
            return sh.worksheet(sheet_name)
        except Exception:
            continue
    worksheets = sh.worksheets()
    if len(worksheets) > 1:
        return worksheets[1]
    return None

def get_templates_worksheet():
    try:
        gc = get_gspread_client()
        target = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        sh = gc.open_by_url(target) if target.startswith("http") else gc.open_by_key(target)
        try:
            return sh.worksheet("templates")
        except Exception:
            ws = sh.add_worksheet(title="templates", rows="100", cols="5")
            ws.append_row(["template_name", "items_json", "template_image"])
            return ws
    except Exception:
        return None

def get_inventory_worksheet():
    try:
        gc = get_gspread_client()
        target = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        sh = gc.open_by_url(target) if target.startswith("http") else gc.open_by_key(target)
        try:
            return sh.worksheet("inventory")
        except Exception:
            ws = sh.add_worksheet(title="inventory", rows="100", cols="4")
            ws.append_row(["material_name", "unit", "current_stock", "min_threshold"])
            return ws
    except Exception:
        return None

@st.cache_data(ttl=30)
def load_inventory():
    try:
        ws = get_inventory_worksheet()
        if ws is None:
            return []
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return []
        inventory_items = []
        for row in vals[1:]:
            if not row or not row[0].strip():
                continue
            inventory_items.append({
                "material_name": str(row[0]).strip(),
                "unit": str(row[1]).strip() if len(row) > 1 else "عدد",
                "current_stock": float(row[2]) if len(row) > 2 and str(row[2]).replace(".", "").isdigit() else 0.0,
                "min_threshold": float(row[3]) if len(row) > 3 and str(row[3]).replace(".", "").isdigit() else 5.0
            })
        return inventory_items
    except Exception:
        return []

def update_inventory_stock(consumed_items):
    try:
        ws = get_inventory_worksheet()
        if ws is None:
            return False
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return False
        rows = vals[1:]
        stock_dict = {}
        for idx, row in enumerate(rows):
            if row and row[0].strip():
                name = row[0].strip()
                try:
                    curr = float(row[2])
                except:
                    curr = 0.0
                stock_dict[name] = {"row_index": idx + 2, "stock": curr}

        for item in consumed_items:
            m_name = item.get("name")
            m_qty = float(item.get("qty", 1))
            if m_name in stock_dict:
                new_val = max(0.0, stock_dict[m_name]["stock"] - m_qty)
                row_idx = stock_dict[m_name]["row_index"]
                ws.update(range_name=f"C{row_idx}", values=[[new_val]])

        st.cache_data.clear()
        return True
    except Exception as e:
        return False

@st.cache_data(ttl=60)
def load_templates():
    try:
        ws = get_templates_worksheet()
        if ws is None:
            return {}
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return {}
        templates = {}
        for row in vals[1:]:
            if not row or len(row) < 2:
                continue
            name = str(row[0]).strip()
            raw_items = str(row[1]).strip()
            img_b64 = str(row[2]).strip() if len(row) > 2 else ""
            if name and raw_items:
                try:
                    parsed = json.loads(raw_items)
                    if isinstance(parsed, dict) and "items" in parsed:
                        items_list = parsed.get("items", [])
                        if not img_b64:
                            img_b64 = parsed.get("image", "")
                    else:
                        items_list = parsed
                    templates[name] = {
                        "items": items_list,
                        "image": img_b64
                    }
                except Exception:
                    continue
        return templates
    except Exception:
        return {}

def save_template_item(template_name, items, image_b64=""):
    try:
        ws = get_templates_worksheet()
        if ws is None:
            return False
        vals = ws.get_all_values()
        row_to_update = None
        existing_img = ""
        for idx, row in enumerate(vals):
            if row and row[0].strip() == template_name.strip():
                row_to_update = idx + 1
                if len(row) > 2:
                    existing_img = row[2].strip()
                break
        
        final_img = image_b64 if image_b64 else existing_img
        json_str = json.dumps(items, ensure_ascii=False)
        if row_to_update:
            ws.update(range_name=f"B{row_to_update}:C{row_to_update}", values=[[json_str, final_img]])
        else:
            ws.append_row([template_name.strip(), json_str, final_img])
            
        st.cache_data.clear()
        return True
    except Exception as e:
        return False

def delete_template_item(template_name):
    try:
        ws = get_templates_worksheet()
        if ws is None:
            return False
        vals = ws.get_all_values()
        for idx, row in enumerate(vals):
            if row and row[0].strip() == template_name.strip():
                ws.delete_rows(idx + 1)
                st.cache_data.clear()
                return True
        return False
    except Exception as e:
        return False

@st.cache_data(ttl=120)
def load_pricing_catalog():
    try:
        ws = get_pricing_worksheet()
        if ws is None:
            return []
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return []

        header_idx = 0
        for idx, row in enumerate(vals):
            row_str = " ".join(str(c) for c in row)
            if "نام" in row_str and ("مدل" in row_str or "قیمت" in row_str or "تعداد" in row_str):
                header_idx = idx
                break

        headers = [str(h).strip() for h in vals[header_idx]]

        def find_col(keywords, default_idx):
            for i, h in enumerate(headers):
                if any(k in h for k in keywords):
                    return i
            return default_idx

        col_cat = 0
        col_name = find_col(["نام", "مدل گل", "شرح"], 1)
        col_base_unit = find_col(["قیمت واحد"], 3)
        col_cost = find_col(["بهای تمام‌شده کل", "بهای تمام شده کل"], 16)
        col_p12 = find_col(["بالای 12", "بالای ۱۲", "عمده"], 17)
        col_p6 = find_col(["بیشتر از ۶", "بیشتر از 6"], 18)
        col_p1 = find_col(["تک شاخه", "کمتر از 6", "کمتر از ۶"], 19)

        catalog = []
        current_category = "گل و شاخه گل"

        for row in vals[header_idx + 1:]:
            if not row or len(row) <= col_name:
                continue
            
            cat_cell = str(row[col_cat]).strip() if len(row) > col_cat else ""
            if cat_cell:
                current_category = cat_cell

            name_cell = str(row[col_name]).strip() if len(row) > col_name else ""
            if not name_cell or name_cell in ["نام / مدل گل", "nan"]:
                continue

            base_unit = parse_int_price(row[col_base_unit]) if len(row) > col_base_unit else 0
            cost_val = parse_int_price(row[col_cost]) if len(row) > col_cost else 0
            p12_val = parse_int_price(row[col_p12]) if len(row) > col_p12 else 0
            p6_val = parse_int_price(row[col_p6]) if len(row) > col_p6 else 0
            p1_val = parse_int_price(row[col_p1]) if len(row) > col_p1 else 0

            if p1_val == 0 and p6_val == 0 and p12_val == 0 and base_unit > 0:
                p1_val = base_unit
                p6_val = base_unit
                p12_val = base_unit
                if cost_val == 0:
                    cost_val = base_unit

            catalog.append({
                "category": current_category,
                "name": name_cell,
                "cost": cost_val,
                "price_single": p1_val,
                "price_mid": p6_val,
                "price_wholesale": p12_val
            })

        return catalog
    except Exception as e:
        return []

def save_orders(orders):
    try:
        ws = get_worksheet()
        if not orders:
            return
        df = pd.DataFrame(orders).fillna("").astype(str)
        all_data = [df.columns.tolist()] + df.values.tolist()
        ws.clear()
        ws.update(range_name="A1", values=all_data)
        st.cache_data.clear()
    except Exception as e:
        pass

@st.cache_data(ttl=60)
def load_orders():
    try:
        ws = get_worksheet()
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return []
        df = pd.DataFrame(vals[1:], columns=vals[0])
        orders = df.to_dict(orient="records")
        
        numeric_ids = []
        for o in orders:
            val = str(o.get("id", "")).strip()
            if val.isdigit():
                numeric_ids.append(int(val))
        current_max_id = max(numeric_ids) if numeric_ids else 0

        seen_ids = set()
        has_duplicates = False
        for o in orders:
            raw_id = str(o.get("id", "")).strip()
            if not raw_id or raw_id in seen_ids:
                current_max_id += 1
                o["id"] = current_max_id
                has_duplicates = True
            else:
                o["id"] = int(raw_id) if raw_id.isdigit() else raw_id
                seen_ids.add(str(o["id"]))

            o["phone"] = clean_phone_str(o.get("phone", ""))
            o["emergency_phone"] = clean_phone_str(o.get("emergency_phone", ""))
            o["postal_code"] = clean_phone_str(o.get("postal_code", ""))

            o["initial_payment"] = parse_int_price(o.get("initial_payment", 0))
            o["remaining_payment"] = parse_int_price(o.get("remaining_payment", 0))
            o["total_price"] = parse_int_price(o.get("total_price", 0)) or (o["initial_payment"] + o["remaining_payment"])
            if "order_created_at" not in o or not o["order_created_at"]:
                o["order_created_at"] = "1400/01/01 00:00"

            o["chk_deposit"] = _is_truthy(o.get("chk_deposit", False))
            o["chk_photo"] = _is_truthy(o.get("chk_photo", False))
            o["chk_settle"] = _is_truthy(o.get("chk_settle", False))
            o["chk_pack"] = _is_truthy(o.get("chk_pack", False))
            o["chk_post"] = _is_truthy(o.get("chk_post", False))
            o["order_image"] = str(o.get("order_image", ""))

        if has_duplicates:
            save_orders(orders)

        return orders
    except Exception as e:
        return []

orders_list = load_orders()

def get_next_id(orders):
    n_ids = [int(o["id"]) for o in orders if str(o.get("id", "")).isdigit()]
    return (max(n_ids) if n_ids else 0) + 1

def get_next_invoice_no(orders):
    max_inv = 1000
    for o in orders:
        inv = str(o.get("invoice_no", "")).strip()
        if inv.startswith("INV-") and inv[4:].isdigit():
            max_inv = max(max_inv, int(inv[4:]))
    return f"INV-{max_inv + 1}"

if "show_new_order_modal" not in st.session_state:
    st.session_state.show_new_order_modal = False

if "editing_order_id" not in st.session_state:
    st.session_state.editing_order_id = None

if "invoice_cart" not in st.session_state:
    st.session_state.invoice_cart = []

if "invoice_template_image" not in st.session_state:
    st.session_state.invoice_template_image = ""

today_jalali = jdatetime.date.today()

month_names = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

def get_effective_remaining(o):
    if _is_truthy(o.get("chk_settle", False)):
        return 0
    return o.get("remaining_payment", 0)

st.title("🎛 داشبورد مدیریت و تقویم شمسی سفارش‌ها (ابری)")

total_orders = len(orders_list)
total_revenue = sum(o.get("total_price", 0) for o in orders_list)
pending_balance = sum(get_effective_remaining(o) for o in orders_list)

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">کل سفارش‌ها</div>
        <div class="metric-value">{total_orders} عدد</div>
    </div>
    """, unsafe_allow_html=True)
with m2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">مجموع ارزش سفارش‌ها</div>
        <div class="metric-value">{total_revenue:,.0f} تومان</div>
    </div>
    """, unsafe_allow_html=True)
with m3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">مجموع مانده حساب‌ها</div>
        <div class="metric-value">{pending_balance:,.0f} تومان</div>
    </div>
    """, unsafe_allow_html=True)
with m4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">سقف ظرفیت روزانه</div>
        <div class="metric-value">{DAILY_CAPACITY_LIMIT} سفارش</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

col_btn, _ = st.columns([1.5, 4])
with col_btn:
    btn_text = "❌ بستن فرم ثبت سفارش" if st.session_state.show_new_order_modal else "✨ افزودن و ثبت سفارش جدید"
    if st.button(btn_text, use_container_width=True, type="primary"):
        st.session_state.show_new_order_modal = not st.session_state.show_new_order_modal
        st.session_state.editing_order_id = None
        st.rerun()

is_editing = st.session_state.editing_order_id is not None
if st.session_state.show_new_order_modal or is_editing:
    current_order = None
    if is_editing:
        current_order = next((o for o in orders_list if str(o["id"]) == str(st.session_state.editing_order_id)), None)

    st.markdown("---")
    title_box = "✏ ویرایش مشخصات سفارش" if is_editing else "📦 فرم ثبت سفارش مشتری جدید"
    st.subheader(title_box)

    with st.form("order_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            inv_default = current_order["invoice_no"] if is_editing else get_next_invoice_no(orders_list)
            f_invoice_no = st.text_input("شماره فاکتور", value=inv_default)
        with c2:
            c_name_default = current_order["customer_name"] if is_editing else ""
            f_customer_name = st.text_input("نام و نام خانوادگی مشتری", value=c_name_default, placeholder="مثلاً: علیرضا محمدی")
        with c3:
            phone_default = current_order.get("phone", "") if is_editing else ""
            f_phone = st.text_input("شماره تماس", value=phone_default, placeholder="مثلاً: 09123456789")
        with c4:
            emergency_phone_default = current_order.get("emergency_phone", "") if is_editing else ""
            f_emergency_phone = st.text_input("شماره تماس اضطراری", value=emergency_phone_default, placeholder="شماره تماس دوم یا معرف")

        c_info1, c_info2, c_info3 = st.columns([1.5, 1.5, 3])
        with c_info1:
            c_id_default = current_order.get("customer_id", "") if is_editing else ""
            f_customer_id = st.text_input("آیدی / نام کاربری مشتری", value=c_id_default, placeholder="@username یا شناسه")
        with c_info2:
            postal_code_default = current_order.get("postal_code", "") if is_editing else ""
            f_postal_code = st.text_input("کد پستی", value=postal_code_default, placeholder="کد پستی ۱۰ رقمی")
        with c_info3:
            address_default = current_order.get("address", "") if is_editing else ""
            f_address = st.text_input("آدرس پستی کامل", value=address_default, placeholder="استان، شهر، خیابان، کوچه، پلاک، واحد")

        c_prod, c_city, c_date = st.columns([1.5, 1.2, 2.3])
        with c_prod:
            prod_name_default = current_order.get("product_name", "") if is_editing else ""
            f_product_name = st.text_input("نام محصول / مدل", value=prod_name_default, placeholder="مثلاً: باکس گل رز")
        with c_city:
            city_default = current_order.get("destination_city", "") if is_editing else ""
            f_destination_city = st.text_input("شهر مقصد", value=city_default, placeholder="مثلاً: مشهد، تهران...")
        with c_date:
            st.markdown("<p style='font-weight:600; margin-bottom:5px;'>📅 تاریخ تحویل / ارسال (شمسی)</p>", unsafe_allow_html=True)
            cd_d, cd_m, cd_y = st.columns([1, 1.5, 1.2])
            
            d_def, m_def, y_def = today_jalali.day, today_jalali.month, today_jalali.year
            if is_editing and current_order.get("delivery_date"):
                try:
                    parts = current_order["delivery_date"].split("/")
                    y_def, m_def, d_def = int(parts[0]), int(parts[1]), int(parts[2])
                except Exception:
                    pass

            with cd_d:
                f_day = st.selectbox("روز", list(range(1, 32)), index=min(d_def - 1, 30))
            with cd_m:
                f_month_name = st.selectbox("ماه", month_names, index=m_def - 1)
                f_month = month_names.index(f_month_name) + 1
            with cd_y:
                f_year = st.selectbox("سال", [today_jalali.year - 1, today_jalali.year, today_jalali.year + 1], index=1)

            try:
                delivery_jdate = jdatetime.date(f_year, f_month, f_day)
                f_delivery_str = delivery_jdate.strftime("%Y/%m/%d")
            except ValueError:
                delivery_jdate = jdatetime.date(f_year, f_month, 29)
                f_delivery_str = delivery_jdate.strftime("%Y/%m/%d")

        cp1, cp2, cp3 = st.columns(3)
        with cp1:
            init_val_num = int(current_order["initial_payment"]) if is_editing else 0
            init_val_str = f"{init_val_num:,}" if init_val_num > 0 else ""
            f_init_raw = st.text_input("واریزی اول / پیش‌پرداخت (تومان)", value=init_val_str, placeholder="مثلاً: 500,000")
            parsed_init = parse_int_price(f_init_raw)
        with cp2:
            rem_val_num = int(current_order["remaining_payment"]) if is_editing else 0
            rem_val_str = f"{rem_val_num:,}" if rem_val_num > 0 else ""
            f_rem_raw = st.text_input("مانده تسویه (تومان)", value=rem_val_str, placeholder="مثلاً: 250,000")
            parsed_rem = parse_int_price(f_rem_raw)
        with cp3:
            track_val = current_order.get("tracking_code", "") if is_editing else ""
            if track_val == "ثبت نشده":
                track_val = ""
            f_track_code = st.text_input("کد رهگیری پستی (اختیاری)", value=track_val, placeholder="کد رهگیری...")

        desc_val = current_order.get("product_desc", "") if is_editing else ""
        f_product_desc = st.text_area("شرح محصول و جزئیات ساخت", value=desc_val, placeholder="ابعاد، رنگ، متریال...")

        f_uploaded_image = st.file_uploader("🖼️ آپلود عکس سفارش مشتری (اختیاری)", type=["png", "jpg", "jpeg", "webp"])

        col_sub, col_cancel = st.columns([1, 1])
        with col_sub:
            btn_submit_label = "💾 ذخیره تغییرات سفارش" if is_editing else "✅ تایید و ثبت نهایی سفارش"
            submitted = st.form_submit_button(btn_submit_label, use_container_width=True, type="primary")
        with col_cancel:
            cancelled = st.form_submit_button("انصراف", use_container_width=True)

        if cancelled:
            st.session_state.show_new_order_modal = False
            st.session_state.editing_order_id = None
            st.rerun()

        if submitted:
            f_init_pay = parse_int_price(f_init_raw)
            f_rem_pay = parse_int_price(f_rem_raw)
            now_jalali = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")
            
            img_b64 = ""
            if f_uploaded_image is not None:
                img_b64 = compress_image_to_base64(f_uploaded_image)
            elif is_editing and current_order:
                img_b64 = current_order.get("order_image", "")

            if is_editing:
                for o in orders_list:
                    if str(o["id"]) == str(current_order["id"]):
                        o.update({
                            "invoice_no": f_invoice_no,
                            "customer_id": f_customer_id,
                            "customer_name": f_customer_name,
                            "phone": f_phone,
                            "emergency_phone": f_emergency_phone,
                            "address": f_address,
                            "postal_code": f_postal_code,
                            "destination_city": f_destination_city,
                            "product_name": f_product_name,
                            "delivery_date": f_delivery_str,
                            "initial_payment": f_init_pay,
                            "remaining_payment": f_rem_pay,
                            "total_price": f_init_pay + f_rem_pay,
                            "tracking_code": f_track_code if f_track_code else "ثبت نشده",
                            "product_desc": f_product_desc,
                            "order_image": img_b64
                        })
                        break
                save_orders(orders_list)
                st.session_state.editing_order_id = None
                st.session_state.show_new_order_modal = False
                st.success("سفارش با موفقیت ویرایش شد!")
                st.rerun()
            else:
                new_id = get_next_id(orders_list)
                new_item = {
                    "id": new_id,
                    "invoice_no": f_invoice_no,
                    "customer_id": f_customer_id,
                    "customer_name": f_customer_name,
                    "phone": f_phone,
                    "emergency_phone": f_emergency_phone,
                    "address": f_address,
                    "postal_code": f_postal_code,
                    "destination_city": f_destination_city,
                    "product_name": f_product_name,
                    "delivery_date": f_delivery_str,
                    "order_created_at": now_jalali,
                    "initial_payment": f_init_pay,
                    "remaining_payment": f_rem_pay,
                    "total_price": f_init_pay + f_rem_pay,
                    "tracking_code": f_track_code if f_track_code else "ثبت نشده",
                    "product_desc": f_product_desc,
                    "order_image": img_b64,
                    "chk_deposit": False,
                    "chk_photo": False,
                    "chk_settle": False,
                    "chk_pack": False,
                    "chk_post": False
                }
                orders_list.append(new_item)
                save_orders(orders_list)
                st.session_state.show_new_order_modal = False
                st.success(f"سفارش فاکتور {f_invoice_no} ثبت شد!")
                st.rerun()

st.markdown("---")

tab_cards, tab_cal, tab_invoice, tab_stock = st.tabs([
    "👥 کارت‌های مشتریان و سفارش‌ها",
    "📅 تقویم شمسی ظرفیت و زمان‌بندی",
    "🧾 صدور فاکتور و محاسبه قیمت",
    "📦 مدیریت انبار و پایش موجودی"
])

def is_order_fully_checked(order):
    return (
        _is_truthy(order.get("chk_deposit", False)) and
        _is_truthy(order.get("chk_photo", False)) and
        _is_truthy(order.get("chk_settle", False)) and
        _is_truthy(order.get("chk_pack", False)) and
        _is_truthy(order.get("chk_post", False))
    )

def update_order_step(order_id, step_key, value):
    for o in orders_list:
        if str(o.get("id")) == str(order_id):
            o[step_key] = bool(value)
            break
    save_orders(orders_list)
    st.cache_data.clear()
    st.rerun()

def restore_archived_order(order_id):
    today_str = today_jalali.strftime("%Y/%m/%d")
    for o in orders_list:
        if str(o.get("id")) == str(order_id):
            o["chk_post"] = False
            if str(o.get("delivery_date", "")) < today_str:
                o["delivery_date"] = today_str
            break
    save_orders(orders_list)
    st.cache_data.clear()
    st.rerun()

def render_order_card(order, prefix="card", is_archived=False):
    with st.container():
        c_card, c_act = st.columns([4.2, 0.8])
        with c_card:
            prod_display = order.get("product_name") or "ثبت نشده"
            c_name = order.get("customer_name") or "بدون نام"
            c_id_tag = f" ({order.get('customer_id')})" if order.get("customer_id") else ""
            inv_no = order.get("invoice_no") or "-"
            city = order.get("destination_city") or "-"
            deliv_date = order.get("delivery_date") or "-"
            track_no = order.get("tracking_code") or "-"
            created_at = order.get("order_created_at") or "-"
            
            phone_val = str(order.get("phone", "")).strip()
            cid_val = str(order.get("customer_id", "")).strip()
            contact_display = phone_val if phone_val else (cid_val if cid_val else "-")
            
            em_val = str(order.get("emergency_phone", "")).strip()
            em_part = f"<span>🚨 <b>اضطراری:</b> {em_val}</span>" if em_val else ""

            post_val = str(order.get("postal_code", "")).strip()
            post_part = f"<span>📮 <b>کد پستی:</b> {post_val}</span>" if post_val else ""

            addr_val = str(order.get("address", "")).strip()
            addr_part = f"<div style='font-size:0.85rem; color:#4a5568; margin-top:6px;'>🏠 <b>آدرس:</b> {addr_val}</div>" if addr_val else ""

            init_p = order.get("initial_payment", 0)
            is_settled = _is_truthy(order.get("chk_settle", False))
            rem_p = 0 if is_settled else order.get("remaining_payment", 0)
            tot_p = order.get("total_price", 0)
            debt_color = "#38a169" if rem_p == 0 else "#e53e3e"

            desc_val = str(order.get("product_desc", "")).strip()
            img_val = str(order.get("order_image", "")).strip()
            has_img = bool(img_val and img_val.lower() != "nan")

            if has_img:
                bottom_section = (
                    f"<div style='display:flex; gap:14px; align-items:flex-start; margin-top:10px; background:#f8fafc; padding:10px; border-radius:8px; border:1px solid #edf2f7;'>"
                    f"<img src='data:image/jpeg;base64,{img_val}' style='width:120px; height:130px; min-width:120px; border-radius:8px; border:1px solid #cbd5e1; object-fit:contain; background:#ffffff;'/>"
                    f"<div style='flex:1; font-size:0.85rem; color:#4a5568; line-height:1.6;'>"
                    f"📝 <b>توضیحات و جزئیات ساخت:</b><br/>{desc_val if desc_val else '<i>بدون توضیحات</i>'}"
                    f"</div>"
                    f"</div>"
                )
            else:
                bottom_section = f"<div style='font-size:0.83rem; color:#718096; margin-top:6px;'>📝 <i>توضیحات:</i> {desc_val}</div>" if desc_val else ""

            card_html = (
                f"<div class='order-card'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
                f"<span style='font-weight:bold; font-size:1.15rem; color:#2d3748;'>👤 {c_name}{c_id_tag} <span style='font-size:0.85rem; color:#718096;'>({inv_no})</span></span>"
                f"</div>"
                f"<div style='display:flex; gap:20px; flex-wrap:wrap; font-size:0.9rem; color:#4a5568; margin-bottom:8px;'>"
                f"<span>🏷️ <b>محصول:</b> {prod_display}</span>"
                f"<span>📍 <b>مقصد:</b> {city}</span>"
                f"<span>📞 <b>تماس:</b> {contact_display}</span>"
                f"{em_part}"
                f"{post_part}"
                f"<span>📅 <b>تحویل:</b> {deliv_date}</span>"
                f"<span>⏰ <b>ثبت:</b> {created_at}</span>"
                f"<span>📦 <b>کد رهگیری:</b> {track_no}</span>"
                f"</div>"
                f"{addr_part}"
                f"<div style='display:flex; gap:25px; flex-wrap:wrap; font-size:0.88rem; background:#f7fafc; padding:8px 12px; border-radius:8px; margin-top:8px;'>"
                f"<span>💰 <b>پیش‌پرداخت:</b> {init_p:,.0f} تومان</span>"
                f"<span>⚖️ <b>مانده تسویه:</b> <b style='color:{debt_color};'>{rem_p:,.0f} تومان</b></span>"
                f"<span>💵 <b>جمع کل:</b> {tot_p:,.0f} تومان</span>"
                f"</div>"
                f"{bottom_section}"
                f"</div>"
            )
            st.markdown(card_html, unsafe_allow_html=True)

            st.markdown("<div class='order-steps-container'>", unsafe_allow_html=True)
            s0, s1, s2, s3, s4 = st.columns(5)
            
            k_d = f"d_{prefix}_{order['id']}"
            k_p = f"p_{prefix}_{order['id']}"
            k_s = f"s_{prefix}_{order['id']}"
            k_pk = f"pk_{prefix}_{order['id']}"
            k_pt = f"pt_{prefix}_{order['id']}"

            with s0:
                st.checkbox("💵 واریز بیعانه", value=_is_truthy(order.get("chk_deposit", False)), key=k_d, on_change=lambda oid=order['id'], k=k_d: update_order_step(oid, "chk_deposit", st.session_state[k]))
            with s1:
                st.checkbox("📷 ارسال عکس", value=_is_truthy(order.get("chk_photo", False)), key=k_p, on_change=lambda oid=order['id'], k=k_p: update_order_step(oid, "chk_photo", st.session_state[k]))
            with s2:
                st.checkbox("💳 تسویه", value=_is_truthy(order.get("chk_settle", False)), key=k_s, on_change=lambda oid=order['id'], k=k_s: update_order_step(oid, "chk_settle", st.session_state[k]))
            with s3:
                st.checkbox("🎁 بسته‌بندی", value=_is_truthy(order.get("chk_pack", False)), key=k_pk, on_change=lambda oid=order['id'], k=k_pk: update_order_step(oid, "chk_pack", st.session_state[k]))
            with s4:
                st.checkbox("🚚 تحویل پست", value=_is_truthy(order.get("chk_post", False)), key=k_pt, on_change=lambda oid=order['id'], k=k_pt: update_order_step(oid, "chk_post", st.session_state[k]))
            st.markdown("</div>", unsafe_allow_html=True)

        with c_act:
            st.write("")
            if is_archived:
                if st.button("↩️ بازگردانی", key=f"restore_{prefix}_{order['id']}", use_container_width=True):
                    restore_archived_order(order["id"])

            if st.button("✏️ ویرایش", key=f"edit_{prefix}_{order['id']}", use_container_width=True):
                st.session_state.editing_order_id = order["id"]
                st.session_state.show_new_order_modal = False
                st.rerun()

            if st.button("🗑️ حذف", key=f"del_{prefix}_{order['id']}", use_container_width=True):
                updated = [o for o in orders_list if str(o["id"]) != str(order["id"])]
                save_orders(updated)
                st.rerun()

with tab_cards:
    col_t2, col_t1 = st.columns([1, 3])
    with col_t1:
        st.subheader("📋 مدیریت پرونده‌های مشتریان")
    with col_t2:
        search_query = st.text_input("🔍 جستجو (نام، فاکتور، شهر، تماس)...", "")

    filtered_orders = orders_list
    if search_query:
        filtered_orders = [
            o for o in orders_list 
            if search_query in str(o.get("customer_name", "")) 
            or search_query in str(o.get("invoice_no", ""))
            or search_query in str(o.get("destination_city", ""))
            or search_query in str(o.get("phone", ""))
        ]

    if filtered_orders:
        sorted_orders = sorted(
            filtered_orders,
            key=lambda x: (str(x.get("delivery_date", "9999/99/99")), str(x.get("order_created_at", "9999/99/99 99:99")))
        )

        today_str = today_jalali.strftime("%Y/%m/%d")
        past_orders = [o for o in sorted_orders if str(o.get("delivery_date", "")) < today_str or is_order_fully_checked(o)]
        active_orders = [o for o in sorted_orders if str(o.get("delivery_date", "")) >= today_str and not is_order_fully_checked(o)]

        date_groups = {}
        for o in active_orders:
            d = str(o.get("delivery_date", "نامشخص"))
            if d not in date_groups:
                date_groups[d] = []
            date_groups[d].append(o)

        for d in sorted(list(date_groups.keys())):
            orders_in_date = date_groups[d]
            is_today = (d == today_str)
            today_tag = " — 🎯 تحویل امروز" if is_today else ""
            st.markdown(f"#### 📅 سفارش‌های تاریخ {d}{today_tag} — {len(orders_in_date)} سفارش")
            for idx, order in enumerate(orders_in_date):
                render_order_card(order, prefix=f"act_{d.replace('/', '_')}_{idx}", is_archived=False)

        if past_orders:
            with st.expander(f"📦 بایگانی سفارش‌های گذشته ({len(past_orders)} سفارش)"):
                for idx, order in enumerate(past_orders):
                    render_order_card(order, prefix=f"arch_{idx}", is_archived=True)

        st.markdown("---")
        df_export = pd.DataFrame(orders_list)
        csv_data = df_export.to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="📥 دریافت فایل CSV سفارش‌ها", data=csv_data, file_name="orders_data.csv", mime="text/csv")
    else:
        st.info("هیچ سفارشی یافت نشد.")

with tab_cal:
    if "cal_year" not in st.session_state:
        st.session_state.cal_year = today_jalali.year
    if "cal_month" not in st.session_state:
        st.session_state.cal_month = today_jalali.month

    cal_top_col1, cal_top_col2 = st.columns([2.5, 1.5])
    with cal_top_col2:
        cal_view_mode = st.radio("نوع نمایش تقویم:", ["نمای ماهانه (شبکه‌ای)", "نمای روزانه موبایلی"], horizontal=True)

    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    with col_nav1:
        if st.button("⬅ ماه قبل", use_container_width=True, key="prev_m"):
            if st.session_state.cal_month == 1:
                st.session_state.cal_month = 12
                st.session_state.cal_year -= 1
            else:
                st.session_state.cal_month -= 1
            st.rerun()
    with col_nav2:
        st.markdown(f"<h3 style='text-align: center; margin:0;'>{month_names[st.session_state.cal_month - 1]} {st.session_state.cal_year}</h3>", unsafe_allow_html=True)
    with col_nav3:
        if st.button("ماه بعد ➡️", use_container_width=True, key="next_m"):
            if st.session_state.cal_month == 12:
                st.session_state.cal_month = 1
                st.session_state.cal_year += 1
            else:
                st.session_state.cal_month += 1
            st.rerun()

    current_year = st.session_state.cal_year
    current_month = st.session_state.cal_month
    first_day_of_month = jdatetime.date(current_year, current_month, 1)
    start_weekday = first_day_of_month.weekday()
    
    if current_month <= 6:
        days_in_month = 31
    elif current_month <= 11:
        days_in_month = 30
    else:
        days_in_month = 30 if jdatetime.date(current_year, 1, 1).isleap() else 29

    orders_map = {}
    for o in orders_list:
        d = str(o.get("delivery_date", ""))
        if d not in orders_map:
            orders_map[d] = []
        orders_map[d].append(o)

    today_str = today_jalali.strftime("%Y/%m/%d")

    if cal_view_mode == "نمای روزانه موبایلی":
        found_any = False
        for day in range(1, days_in_month + 1):
            date_key = f"{current_year}/{current_month:02d}/{day:02d}"
            day_orders = orders_map.get(date_key, [])
            if day_orders:
                found_any = True
                st.markdown(f"**📌 {day} {month_names[current_month - 1]} {current_year}** — `{len(day_orders)}/{DAILY_CAPACITY_LIMIT} سفارش`")
                for item in day_orders:
                    item_rem = get_effective_remaining(item)
                    st.markdown(f"<div style='background:#f8fafc; border-right:4px solid #3182ce; padding:8px; border-radius:6px; margin-bottom:6px; font-size:0.85rem;'>📦 <b>{item.get('customer_name')}</b> | مقصد: {item.get('destination_city')} | مانده: {item_rem:,.0f} تومان</div>", unsafe_allow_html=True)
                st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
        if not found_any:
            st.caption("در این ماه سفارشی ثبت نشده است.")
    else:
        weekdays_fa = ["شنبه", "۱شنبه", "۲شنبه", "۳شنبه", "۴شنبه", "۵شنبه", "جمعه"]
        cols_header = st.columns(7)
        for idx, day_name in enumerate(weekdays_fa):
            cols_header[idx].markdown(f"<div style='text-align:center; font-weight:bold; background:#edf2f7; padding:6px; border-radius:6px;'>{day_name}</div>", unsafe_allow_html=True)

        day_counter = 1
        total_slots = start_weekday + days_in_month
        rows = (total_slots + 6) // 7

        for row in range(rows):
            cols = st.columns(7)
            for col_idx in range(7):
                current_slot = row * 7 + col_idx
                with cols[col_idx]:
                    if current_slot < start_weekday or day_counter > days_in_month:
                        st.markdown("<div style='min-height:110px;'></div>", unsafe_allow_html=True)
                    else:
                        date_key = f"{current_year}/{current_month:02d}/{day_counter:02d}"
                        day_orders = orders_map.get(date_key, [])
                        order_count = len(day_orders)
                        is_today = (current_year == today_jalali.year and current_month == today_jalali.month and day_counter == today_jalali.day)
                        is_full = order_count >= DAILY_CAPACITY_LIMIT

                        cell_classes = ["calendar-cell"]
                        if is_today:
                            cell_classes.append("cell-today")
                        if is_full:
                            cell_classes.append("cell-full")
                        elif order_count > 0:
                            cell_classes.append("cell-available")

                        capacity_badge = f"<span style='color:{'#e53e3e' if is_full else '#38a169'}; font-size:0.75rem; font-weight:bold;'>({order_count}/{DAILY_CAPACITY_LIMIT})</span>" if order_count > 0 else "<span style='color:#a0aec0; font-size:0.72rem;'>خالی</span>"

                        orders_html = ""
                        for item in day_orders[:3]:
                            item_rem = get_effective_remaining(item)
                            badge_class = "badge-paid" if item_rem == 0 else "badge-debt"
                            orders_html += f"<div class='order-badge {badge_class}'>📦 {item['customer_name']}</div>"

                        st.markdown(f"""
                        <div class="{' '.join(cell_classes)}">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span class="day-num">{day_counter}</span>
                                {capacity_badge}
                            </div>
                            {orders_html}
                        </div>
                        """, unsafe_allow_html=True)
                        day_counter += 1

with tab_invoice:
    st.subheader("🧾 صدور فاکتور مشتریان (متصل به شیت آنالیز جامع)")
    catalog = load_pricing_catalog()
    saved_templates = load_templates()

    if st.button("🔄 بروزرسانی قیمت‌ها و الگوها", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    with st.expander("💐 انتخاب دسته‌گل‌های ذخیره‌شده (الگوهای پیش‌فرض)", expanded=bool(saved_templates)):
        if saved_templates:
            tpl_col1, tpl_col2, tpl_col3 = st.columns([3, 1.2, 0.8])
            with tpl_col1:
                selected_tpl = st.selectbox("انتخاب دسته‌گل:", options=list(saved_templates.keys()), key="select_saved_tpl")
            sel_tpl_obj = saved_templates[selected_tpl]
            sel_tpl_items = sel_tpl_obj["items"] if isinstance(sel_tpl_obj, dict) else sel_tpl_obj
            sel_tpl_img = sel_tpl_obj.get("image", "") if isinstance(sel_tpl_obj, dict) else ""

            with tpl_col2:
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                if st.button("📥 بارگذاری در فاکتور", use_container_width=True, type="primary"):
                    st.session_state.invoice_cart = copy.deepcopy(sel_tpl_items)
                    st.session_state.invoice_template_image = sel_tpl_img
                    st.success("به فاکتور منتقل شد.")
                    st.rerun()
            with tpl_col3:
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                if st.button("🗑️ حذف الگو", use_container_width=True):
                    if delete_template_item(selected_tpl):
                        st.warning("حذف شد.")
                        st.rerun()
        else:
            st.info("هنوز الگویی ذخیره نشده است.")

    if not catalog:
        st.warning("⚠️ شیت قیمت‌گذاری در گوگل شیت یافت نشد یا خالی است.")
    else:
        st.markdown("#### ➕ افزودن ردیف به فاکتور")
        categories = ["همه دسته‌ها"] + list(dict.fromkeys([item["category"] for item in catalog if item.get("category")]))
        
        ic1, ic2, ic3, ic4 = st.columns([1.2, 2.2, 1.8, 1])
        with ic1:
            sel_cat = st.selectbox("دسته‌بندی", categories, key="inv_cat")
        filtered_catalog = [item for item in catalog if sel_cat == "همه دسته‌ها" or item["category"] == sel_cat]
        product_names = [item["name"] for item in filtered_catalog]

        with ic2:
            sel_prod_name = st.selectbox("انتخاب محصول", product_names, key="inv_prod")
        selected_prod = next((item for item in filtered_catalog if item["name"] == sel_prod_name), None)

        sales_models = ["تک شاخه / کمتر از ۶ شاخه", "بیشتر از ۶ شاخه", "فروش عمده (بالای ۱۲ شاخه)", "قیمت دستی / توافقی"]
        with ic3:
            sel_model = st.selectbox("مدل فروش", sales_models, key="inv_model")
        with ic4:
            sel_qty = st.number_input("تعداد", min_value=1, value=1, step=1, key="inv_qty")

        default_unit_price = 0
        unit_cost = 0
        if selected_prod:
            unit_cost = selected_prod.get("cost", 0)
            if sel_model == "تک شاخه / کمتر از ۶ شاخه":
                default_unit_price = selected_prod.get("price_single", 0)
            elif sel_model == "بیشتر از ۶ شاخه":
                default_unit_price = selected_prod.get("price_mid", 0)
            elif sel_model == "فروش عمده (بالای ۱۲ شاخه)":
                default_unit_price = selected_prod.get("price_wholesale", 0)

        ic_p1, ic_p2, ic_btn = st.columns([2, 2.2, 1.5])
        with ic_p1:
            if sel_model == "قیمت دستی / توافقی" or default_unit_price == 0:
                manual_price_str = st.text_input("قیمت واحد (تومان)", value="", key="inv_manual_p")
                final_unit_price = parse_int_price(manual_price_str)
            else:
                final_unit_price = default_unit_price

        with ic_p2:
            line_total = final_unit_price * sel_qty

        with ic_btn:
            st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
            if st.button("➕ افزودن به فاکتور", use_container_width=True, type="primary"):
                if selected_prod and final_unit_price > 0:
                    st.session_state.invoice_cart.append({
                        "category": selected_prod["category"],
                        "name": selected_prod["name"],
                        "sales_model": sel_model,
                        "qty": int(sel_qty),
                        "unit_price": int(final_unit_price),
                        "total_price": int(line_total),
                        "unit_cost": int(unit_cost),
                        "total_cost": int(unit_cost * sel_qty),
                        "price_single": selected_prod.get("price_single", final_unit_price),
                        "price_mid": selected_prod.get("price_mid", final_unit_price),
                        "price_wholesale": selected_prod.get("price_wholesale", final_unit_price)
                    })
                    st.rerun()

        if st.session_state.invoice_cart:
            st.markdown("#### 🛒 لیست اقلام فاکتور جاری")
            for idx, item in enumerate(st.session_state.invoice_cart):
                r1, r2, r3, r4, r5 = st.columns([2.4, 1.5, 1.1, 1.8, 0.6])
                with r1:
                    st.write(f"{idx + 1}. {item['name']}")
                with r2:
                    st.write(item.get('sales_model', ''))
                with r3:
                    new_qty = st.number_input("تعداد", min_value=1, value=int(item["qty"]), key=f"c_q_{idx}", label_visibility="collapsed")
                    if new_qty != item["qty"]:
                        st.session_state.invoice_cart[idx]["qty"] = int(new_qty)
                        st.session_state.invoice_cart[idx]["total_price"] = int(new_qty) * int(item["unit_price"])
                        st.session_state.invoice_cart[idx]["total_cost"] = int(new_qty) * int(item.get("unit_cost", 0))
                        st.rerun()
                with r4:
                    st.write(f"{item['total_price']:,.0f} تومان")
                with r5:
                    if st.button("🗑️", key=f"del_i_{idx}"):
                        st.session_state.invoice_cart.pop(idx)
                        st.rerun()

            items_subtotal = sum(i["total_price"] for i in st.session_state.invoice_cart)
            items_total_cost = sum(i["total_cost"] for i in st.session_state.invoice_cart)

            c_adj1, c_adj2 = st.columns(2)
            with c_adj1:
                inv_shipping = parse_int_price(st.text_input("📦 هزینه ارسال (تومان)", value="0", key="inv_ship"))
            with c_adj2:
                inv_discount = parse_int_price(st.text_input("🎁 تخفیف (تومان)", value="0", key="inv_disc"))

            grand_total = max(0, items_subtotal + inv_shipping - inv_discount)
            
            st.markdown(f"**مبلغ قابل پرداخت نهایی: {grand_total:,.0f} تومان**")

            if st.button("✅ ثبت فاکتور در سفارش‌ها و کسر از انبار", use_container_width=True, type="primary"):
                new_id = get_next_id(orders_list)
                new_inv_no = get_next_invoice_no(orders_list)
                now_j = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")

                new_order = {
                    "id": new_id,
                    "invoice_no": new_inv_no,
                    "customer_name": "مشتری فاکتور",
                    "total_price": grand_total,
                    "delivery_date": today_jalali.strftime("%Y/%m/%d"),
                    "order_created_at": now_j,
                    "product_name": "دسته‌گل فاکتور شده",
                    "initial_payment": 0,
                    "remaining_payment": grand_total,
                    "order_image": st.session_state.get("invoice_template_image", ""),
                }
                orders_list.append(new_order)
                save_orders(orders_list)
                
                # کسر خودکار متریال از انبار
                update_inventory_stock(st.session_state.invoice_cart)
                
                st.session_state.invoice_cart = []
                st.success("سفارش ثبت و موجودی انبار به‌روزرسانی شد!")
                st.rerun()

with tab_stock:
    st.subheader("📦 مدیریت انبار متریال و پایش موجودی")
    inventory_data = load_inventory()
    
    if inventory_data:
        low_stock_items = [i for i in inventory_data if i["current_stock"] <= i["min_threshold"]]
        if low_stock_items:
            st.warning(f"🚨 هشدار: {len(low_stock_items)} قلم از متریال‌های انبار به اتمام نزدیک شده‌اند!")
            for alert_item in low_stock_items:
                st.markdown(f"- ⚠️ **{alert_item['material_name']}**: موجودی فعلی `{alert_item['current_stock']} {alert_item['unit']}`")
        
        st.markdown("#### 📊 لیست کامل موجودی انبار")
        st.dataframe(pd.DataFrame(inventory_data), use_container_width=True)
        
        with st.expander("➕ افزودن متریال جدید به انبار"):
            with st.form("add_stock_form"):
                sc1, sc2, sc3, sc4 = st.columns(4)
                with sc1:
                    new_mat_name = st.text_input("نام متریال")
                with sc2:
                    new_mat_unit = st.text_input("واحد", value="عدد")
                with sc3:
                    new_mat_stock = st.number_input("موجودی اولیه", min_value=0.0, value=10.0)
                with sc4:
                    new_mat_min = st.number_input("حداقل هشدار", min_value=0.0, value=3.0)
                
                if st.form_submit_button("💾 ذخیره در انبار", type="primary") and new_mat_name.strip():
                    ws = get_inventory_worksheet()
                    if ws:
                        ws.append_row([new_mat_name.strip(), new_mat_unit, new_mat_stock, new_mat_min])
                        st.cache_data.clear()
                        st.success("متریال افزوده شد!")
                        st.rerun()
    else:
        st.info("هنوز اطلاعاتی در شیت انبار ثبت نشده است.")
        if st.button("➕ ایجاد ساختار اولیه انبار در گوگل شیت"):
            ws = get_inventory_worksheet()
            if ws:
                ws.append_row(["گل رز هلندی", "شاخه", 50.0, 10.0])
                ws.append_row(["روبان ساتن", "متر", 30.0, 5.0])
                st.cache_data.clear()
                st.success("ساختار انبار ایجاد شد!")
                st.rerun()
