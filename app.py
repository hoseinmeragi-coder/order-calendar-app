import streamlit as st
import pandas as pd
from datetime import datetime
import jdatetime
import gspread
from google.oauth2.service_account import Credentials
import base64
import io
from PIL import Image

# تنظیمات اولیه صفحه
st.set_page_config(
    page_title="مدیریت سفارش‌ها و تقویم ظرفیت (شمسی ابری)",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# استایل اختصاصی فوق‌پیشرفته و مدرن (Modern Clean UI)
st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');

    :root {
        --primary: #4f46e5;
        --primary-light: #eef2ff;
        --primary-hover: #4338ca;
        --surface: #ffffff;
        --bg-app: #f8fafc;
        --border-color: #e2e8f0;
        --border-subtle: #f1f5f9;
        --text-main: #0f172a;
        --text-muted: #64748b;
        --success-bg: #ecfdf5;
        --success-text: #047857;
        --danger-bg: #fef2f2;
        --danger-text: #b91c1c;
        --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.05);
        --shadow-md: 0 4px 14px -2px rgba(0, 0, 0, 0.06);
        --shadow-lg: 0 10px 25px -3px rgba(0, 0, 0, 0.08);
        --radius-lg: 16px;
        --radius-md: 12px;
        --radius-sm: 8px;
    }

    html, body, [class*="css"], div, p, span, h1, h2, h3, h4, h5, h6, input, select, textarea, button {
        font-family: 'Vazirmatn', -apple-system, BlinkMacSystemFont, sans-serif !important;
        letter-spacing: -0.01em;
    }

    .stApp {
        background-color: var(--bg-app);
        direction: rtl;
        text-align: right;
    }

    /* هدر اصلی اپلیکیشن */
    h1 {
        font-size: 1.75rem !important;
        font-weight: 800 !important;
        color: var(--text-main) !important;
        margin-bottom: 1.5rem !important;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    [data-testid="stIconMaterial"], .material-symbols-rounded, .material-symbols-outlined {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
        direction: ltr !important;
    }

    /* ورودی‌ها و المان‌های فرم */
    .stTextInput input, .stTextArea textarea, .stSelectbox select, div[data-baseweb="select"] {
        border-radius: var(--radius-md) !important;
        border: 1px solid var(--border-color) !important;
        background-color: #ffffff !important;
        box-shadow: var(--shadow-sm) !important;
        transition: all 0.2s ease-in-out !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.12) !important;
    }

    /* دکمه‌ها */
    .stButton>button {
        border-radius: var(--radius-md) !important;
        font-weight: 600 !important;
        padding: 0.55rem 1.25rem !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: var(--shadow-sm) !important;
        border: 1px solid transparent !important;
    }
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: var(--shadow-md) !important;
    }
    .stButton>button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5 0%, #3730a3 100%) !important;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25) !important;
    }

    /* کارت‌های شاخص آمار (KPI Bento Cards) */
    .metric-card {
        background: #ffffff;
        border: 1px solid rgba(226, 232, 240, 0.8);
        border-radius: var(--radius-lg);
        padding: 18px 20px;
        box-shadow: var(--shadow-md);
        text-align: right;
        position: relative;
        overflow: hidden;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-lg);
    }
    .metric-card::before {
        content: "";
        position: absolute;
        top: 0;
        right: 0;
        width: 100%;
        height: 4px;
        background: linear-gradient(90deg, #4f46e5, #06b6d4);
    }
    .metric-label {
        font-size: 0.85rem;
        font-weight: 600;
        color: var(--text-muted);
        margin-bottom: 8px;
    }
    .metric-value {
        font-size: 1.45rem;
        font-weight: 800;
        color: var(--text-main);
        letter-spacing: -0.02em;
    }

    /* کارت سفارش اصلی */
    .order-card {
        background: #ffffff;
        border: 1px solid var(--border-color);
        border-radius: var(--radius-lg) var(--radius-lg) 0 0;
        padding: 22px 24px 16px 24px;
        border-right: 5px solid var(--primary);
        box-shadow: var(--shadow-sm);
        transition: border-color 0.2s ease;
    }
    .order-card:hover {
        border-color: #cbd5e1;
    }
    .order-steps-container {
        background: #fbfcfe;
        border: 1px solid var(--border-color);
        border-top: none;
        border-radius: 0 0 var(--radius-lg) var(--radius-lg);
        border-right: 5px solid var(--primary);
        padding: 12px 24px 8px 24px;
        margin-bottom: 22px;
        box-shadow: var(--shadow-sm);
    }

    /* المان‌های تقویم ماهانه */
    .calendar-cell {
        border: 1px solid var(--border-color);
        border-radius: var(--radius-md);
        padding: 10px;
        min-height: 120px;
        margin-bottom: 10px;
        background: #ffffff;
        box-shadow: var(--shadow-sm);
        transition: all 0.25s ease;
        position: relative;
    }
    .calendar-cell:hover {
        border-color: #94a3b8;
        transform: translateY(-2px);
        box-shadow: var(--shadow-md);
    }
    .cell-today {
        border: 2px solid #4f46e5 !important;
        background: #fdfdfe !important;
        box-shadow: 0 0 12px rgba(79, 70, 229, 0.12) !important;
    }
    .cell-full {
        border-right: 4px solid #ef4444 !important;
        background: #fffafa !important;
    }
    .cell-available {
        border-right: 4px solid #10b981 !important;
        background: #f8fdfa !important;
    }
    .day-num {
        font-weight: 700;
        font-size: 1.1rem;
        color: var(--text-main);
    }
    .order-badge {
        font-size: 0.74rem;
        font-weight: 500;
        padding: 3px 8px;
        border-radius: 6px;
        margin-top: 5px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        display: block;
        transition: transform 0.15s ease;
    }
    .order-badge:hover {
        transform: scale(0.98);
    }
    .badge-paid {
        background-color: var(--success-bg);
        color: var(--success-text);
        border: 1px solid rgba(16, 185, 129, 0.15);
    }
    .badge-debt {
        background-color: #fff7ed;
        color: #c2410c;
        border: 1px solid rgba(234, 88, 12, 0.15);
    }

    /* تب‌ها */
    div[data-baseweb="tab-list"] {
        gap: 8px !important;
        border-bottom: 2px solid var(--border-color) !important;
        padding-bottom: 4px !important;
        margin-bottom: 20px !important;
    }
    div[data-baseweb="tab"] {
        padding: 10px 18px !important;
        border-radius: var(--radius-md) var(--radius-md) 0 0 !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        color: var(--text-muted) !important;
    }
    div[aria-selected="true"] {
        color: var(--primary) !important;
        border-bottom-color: var(--primary) !important;
    }

    /* اکوردیون (Expander) */
    div[data-testid="stExpander"] {
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius-lg) !important;
        background: #ffffff !important;
        box-shadow: var(--shadow-sm) !important;
        margin-top: 18px !important;
        overflow: hidden;
    }
    div[data-testid="stExpander"] summary {
        direction: rtl !important;
        text-align: right !important;
        display: flex !important;
        flex-direction: row-reverse !important;
        justify-content: space-between !important;
        align-items: center !important;
        padding: 14px 20px !important;
        font-weight: 700 !important;
        color: var(--text-main) !important;
        background: #f8fafc !important;
    }

    @media (max-width: 768px) {
        .calendar-cell {
            min-height: 90px;
            padding: 6px;
        }
        .day-num {
            font-size: 0.92rem;
        }
        .order-badge {
            font-size: 0.68rem;
            padding: 2px 4px;
        }
        .order-card {
            padding: 16px;
        }
    }
</style>
""", unsafe_allow_html=True)

DAILY_CAPACITY_LIMIT = 5

def parse_int_price(val):
    if not val or pd.isna(val):
        return 0
    clean_str = str(val).replace(",", "").replace("،", "").strip()
    try:
        return int(float(clean_str))
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
    """کوچک کردن حجم تصویر تا کمتر از ۳۰ کیلوبایت جهت همخوانی با محدودیت سلول گوگل شیت"""
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

def save_orders(orders):
    try:
        ws = get_worksheet()
        if not orders:
            return  # جلوگیری از خالی شدن تصادفی کل شیت
        
        df = pd.DataFrame(orders).fillna("").astype(str)
        all_data = [df.columns.tolist()] + df.values.tolist()
        
        ws.clear()
        ws.update(range_name="A1", values=all_data)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"خطا در همگام‌سازی ابری: {e}")

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
        st.warning(f"عدم امکان خواندن اطلاعات شیت: {e}")
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

today_jalali = jdatetime.date.today()

month_names = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

def get_effective_remaining(o):
    if _is_truthy(o.get("chk_settle", False)):
        return 0
    return o.get("remaining_payment", 0)

# ----------------- هدر و آمار کلیدی -----------------
st.title("🎛️ داشبورد جامع سفارش‌ها و تقویم ظرفیت")

total_orders = len(orders_list)
total_revenue = sum(o.get("total_price", 0) for o in orders_list)
pending_balance = sum(get_effective_remaining(o) for o in orders_list)

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">📦 کل سفارش‌ها</div>
        <div class="metric-value">{total_orders} <span style="font-size:0.9rem; font-weight:400; color:#64748b;">عدد</span></div>
    </div>
    """, unsafe_allow_html=True)
with m2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">💳 مجموع ارزش سفارش‌ها</div>
        <div class="metric-value">{total_revenue:,.0f} <span style="font-size:0.85rem; font-weight:400; color:#64748b;">تومان</span></div>
    </div>
    """, unsafe_allow_html=True)
with m3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">⏳ مجموع مانده حساب‌ها</div>
        <div class="metric-value">{pending_balance:,.0f} <span style="font-size:0.85rem; font-weight:400; color:#64748b;">تومان</span></div>
    </div>
    """, unsafe_allow_html=True)
with m4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">📊 سقف ظرفیت روزانه</div>
        <div class="metric-value">{DAILY_CAPACITY_LIMIT} <span style="font-size:0.85rem; font-weight:400; color:#64748b;">سفارش</span></div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# ----------------- دکمه ثبت سفارش جدید -----------------
col_btn, _ = st.columns([1.5, 4])
with col_btn:
    btn_text = "❌ بستن فرم ثبت سفارش" if st.session_state.show_new_order_modal else "✨ افزودن و ثبت سفارش جدید"
    if st.button(btn_text, use_container_width=True, type="primary"):
        st.session_state.show_new_order_modal = not st.session_state.show_new_order_modal
        st.session_state.editing_order_id = None
        st.rerun()

# ----------------- بخش ثبت / ویرایش سفارش -----------------
is_editing = st.session_state.editing_order_id is not None
if st.session_state.show_new_order_modal or is_editing:
    current_order = None
    if is_editing:
        current_order = next((o for o in orders_list if str(o["id"]) == str(st.session_state.editing_order_id)), None)

    st.markdown("---")
    title_box = "✏️ ویرایش مشخصات سفارش" if is_editing else "📦 فرم ثبت سفارش مشتری جدید"
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
            st.markdown("<p style='font-weight:600; font-size:0.9rem; margin-bottom:5px; color:#334155;'>📅 تاریخ تحویل / ارسال (شمسی)</p>", unsafe_allow_html=True)
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
            if parsed_init > 0:
                st.caption(f"🔎 تفکیک‌شده: **{parsed_init:,}** تومان")

        with cp2:
            rem_val_num = int(current_order["remaining_payment"]) if is_editing else 0
            rem_val_str = f"{rem_val_num:,}" if rem_val_num > 0 else ""
            f_rem_raw = st.text_input("مانده تسویه (تومان)", value=rem_val_str, placeholder="مثلاً: 250,000")
            parsed_rem = parse_int_price(f_rem_raw)
            if parsed_rem > 0:
                st.caption(f"🔎 تفکیک‌شده: **{parsed_rem:,}** تومان")

        with cp3:
            track_val = current_order.get("tracking_code", "") if is_editing else ""
            if track_val == "ثبت نشده":
                track_val = ""
            f_track_code = st.text_input("کد رهگیری پستی (اختیاری)", value=track_val, placeholder="کد رهگیری ۲۴ رقمی...")

        desc_val = current_order.get("product_desc", "") if is_editing else ""
        f_product_desc = st.text_area("شرح محصول و جزئیات ساخت", value=desc_val, placeholder="ابعاد، رنگ، متریال، نحوه بسته‌بندی...")

        # آپلود تصویر سفارش
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
            
            # فشرده‌سازی و تبدیل تصویر به Base64
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
                st.success("سفارش با موفقیت در فضای ابری ویرایش شد!")
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
                st.success(f"سفارش فاکتور {f_invoice_no} در فضای ابری ثبت شد!")
                st.rerun()

st.markdown("---")

# ----------------- تب‌های برنامه -----------------
tab_cards, tab_cal = st.tabs(["👥 کارت‌های مشتریان و سفارش‌ها", "📅 تقویم شمسی ظرفیت و زمان‌بندی"])

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
            em_part = f"<span style='background:#fee2e2; color:#991b1b; padding:2px 8px; border-radius:6px;'>🚨 <b>اضطراری:</b> {em_val}</span>" if em_val else ""

            post_val = str(order.get("postal_code", "")).strip()
            post_part = f"<span>📮 <b>کد پستی:</b> {post_val}</span>" if post_val else ""

            addr_val = str(order.get("address", "")).strip()
            addr_part = f"<div style='font-size:0.87rem; color:#475569; margin-top:8px; line-height:1.6;'>🏠 <b>آدرس:</b> {addr_val}</div>" if addr_val else ""

            init_p = order.get("initial_payment", 0)
            
            is_settled = _is_truthy(order.get("chk_settle", False))
            rem_p = 0 if is_settled else order.get("remaining_payment", 0)
            tot_p = order.get("total_price", 0)
            debt_color = "#10b981" if rem_p == 0 else "#ef4444"

            desc_val = str(order.get("product_desc", "")).strip()

            # تصویر و قرارگیری توضیحات در کنار تصویر
            img_val = str(order.get("order_image", "")).strip()
            has_img = bool(img_val and img_val.lower() != "nan")

            if has_img:
                bottom_section = (
                    f"<div style='display:flex; gap:16px; align-items:flex-start; margin-top:12px; background:#f8fafc; padding:12px; border-radius:12px; border:1px solid #e2e8f0;'>"
                    f"<img src='data:image/jpeg;base64,{img_val}' style='width:120px; height:120px; min-width:120px; border-radius:10px; border:1px solid #cbd5e1; object-fit:cover; box-shadow:0 2px 6px rgba(0,0,0,0.06);'/>"
                    f"<div style='flex:1; font-size:0.87rem; color:#334155; line-height:1.7;'>"
                    f"<span style='font-weight:700; color:#1e293b;'>📝 توضیحات و جزئیات ساخت:</span><br/>{desc_val if desc_val else '<i>بدون توضیحات اضافی</i>'}"
                    f"</div>"
                    f"</div>"
                )
            else:
                bottom_section = f"<div style='font-size:0.85rem; color:#64748b; margin-top:8px;'>📝 <i>توضیحات:</i> {desc_val}</div>" if desc_val else ""

            card_html = (
                f"<div class='order-card'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;'>"
                f"<span style='font-weight:800; font-size:1.15rem; color:#0f172a;'>👤 {c_name}{c_id_tag} <span style='font-size:0.82rem; font-weight:600; background:#f1f5f9; color:#475569; padding:2px 8px; border-radius:6px; margin-right:6px;'>{inv_no}</span></span>"
                f"</div>"
                f"<div style='display:flex; gap:18px; flex-wrap:wrap; font-size:0.88rem; color:#475569; margin-bottom:8px;'>"
                f"<span>🏷️ <b>محصول:</b> <span style='color:#0f172a;'>{prod_display}</span></span>"
                f"<span>📍 <b>مقصد:</b> {city}</span>"
                f"<span>📞 <b>تماس:</b> {contact_display}</span>"
                f"{em_part}"
                f"{post_part}"
                f"<span>📅 <b>تحویل:</b> {deliv_date}</span>"
                f"<span>⏰ <b>ثبت:</b> {created_at}</span>"
                f"<span>📦 <b>کد رهگیری:</b> {track_no}</span>"
                f"</div>"
                f"{addr_part}"
                f"<div style='display:flex; gap:20px; flex-wrap:wrap; font-size:0.88rem; background:#f8fafc; padding:10px 14px; border-radius:10px; margin-top:10px; border:1px solid #f1f5f9;'>"
                f"<span>💰 <b>پیش‌پرداخت:</b> {init_p:,.0f} تومان</span>"
                f"<span>⚖️ <b>مانده تسویه:</b> <b style='color:{debt_color}; font-size:0.95rem;'>{rem_p:,.0f} تومان</b></span>"
                f"<span>💵 <b>جمع کل:</b> <b style='color:#0f172a;'>{tot_p:,.0f} تومان</b></span>"
                f"</div>"
                f"{bottom_section}"
                f"</div>"
            )
            st.markdown(card_html, unsafe_allow_html=True)

            # چک‌لیست مراحل سفارش
            st.markdown("<div class='order-steps-container'>", unsafe_allow_html=True)
            s0, s1, s2, s3, s4 = st.columns(5)
            
            k_d = f"d_{prefix}_{order['id']}"
            k_p = f"p_{prefix}_{order['id']}"
            k_s = f"s_{prefix}_{order['id']}"
            k_pk = f"pk_{prefix}_{order['id']}"
            k_pt = f"pt_{prefix}_{order['id']}"

            with s0:
                st.checkbox(
                    "💵 واریز بیعانه",
                    value=_is_truthy(order.get("chk_deposit", False)),
                    key=k_d,
                    on_change=lambda oid=order['id'], k=k_d: update_order_step(oid, "chk_deposit", st.session_state[k])
                )
            with s1:
                st.checkbox(
                    "📷 ارسال عکس برای تسویه",
                    value=_is_truthy(order.get("chk_photo", False)),
                    key=k_p,
                    on_change=lambda oid=order['id'], k=k_p: update_order_step(oid, "chk_photo", st.session_state[k])
                )
            with s2:
                st.checkbox(
                    "💳 تسویه",
                    value=_is_truthy(order.get("chk_settle", False)),
                    key=k_s,
                    on_change=lambda oid=order['id'], k=k_s: update_order_step(oid, "chk_settle", st.session_state[k])
                )
            with s3:
                st.checkbox(
                    "🎁 آماده‌سازی بسته",
                    value=_is_truthy(order.get("chk_pack", False)),
                    key=k_pk,
                    on_change=lambda oid=order['id'], k=k_pk: update_order_step(oid, "chk_pack", st.session_state[k])
                )
            with s4:
                st.checkbox(
                    "🚚 تحویل به پست",
                    value=_is_truthy(order.get("chk_post", False)),
                    key=k_pt,
                    on_change=lambda oid=order['id'], k=k_pt: update_order_step(oid, "chk_post", st.session_state[k])
                )
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

# ----------------- تب ۱: کارت‌های مشتریان -----------------
with tab_cards:
    col_t2, col_t1 = st.columns([1.2, 2.8])
    with col_t1:
        st.subheader("📋 مدیریت پرونده‌های مشتریان")
    with col_t2:
        search_query = st.text_input("🔍 جستجو (نام، فاکتور، شهر، آیدی، تماس)...", "")

    filtered_orders = orders_list
    if search_query:
        filtered_orders = [
            o for o in orders_list 
            if search_query in str(o.get("customer_name", "")) 
            or search_query in str(o.get("invoice_no", ""))
            or search_query in str(o.get("destination_city", ""))
            or search_query in str(o.get("customer_id", ""))
            or search_query in str(o.get("phone", ""))
            or search_query in str(o.get("emergency_phone", ""))
            or search_query in str(o.get("postal_code", ""))
            or search_query in str(o.get("address", ""))
            or search_query in str(o.get("product_name", ""))
        ]

    if filtered_orders:
        sorted_orders = sorted(
            filtered_orders,
            key=lambda x: (str(x.get("delivery_date", "9999/99/99")), str(x.get("order_created_at", "9999/99/99 99:99")))
        )

        today_str = today_jalali.strftime("%Y/%m/%d")

        past_orders = [
            o for o in sorted_orders 
            if str(o.get("delivery_date", "")) < today_str or is_order_fully_checked(o)
        ]
        
        active_orders = [
            o for o in sorted_orders 
            if str(o.get("delivery_date", "")) >= today_str and not is_order_fully_checked(o)
        ]

        date_groups = {}
        for o in active_orders:
            d = str(o.get("delivery_date", "نامشخص"))
            if d not in date_groups:
                date_groups[d] = []
            date_groups[d].append(o)

        active_dates = sorted(list(date_groups.keys()))

        for d in active_dates:
            orders_in_date = date_groups[d]
            is_today = (d == today_str)
            today_tag = " — 🎯 تحویل امروز" if is_today else ""
            st.markdown(f"#### 📅 سفارش‌های تاریخ {d}{today_tag} — `{len(orders_in_date)} سفارش`")
            for idx, order in enumerate(orders_in_date):
                render_order_card(order, prefix=f"act_{d.replace('/', '_')}_{idx}", is_archived=False)

        if past_orders:
            with st.expander(f"📦 بایگانی سفارش‌های گذشته و تکمیل‌شده ({len(past_orders)} سفارش)"):
                for idx, order in enumerate(past_orders):
                    render_order_card(order, prefix=f"arch_{idx}", is_archived=True)

        st.markdown("---")
        df_export = pd.DataFrame(orders_list)
        csv_data = df_export.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 دریافت فایل اکسل / CSV سفارش‌ها",
            data=csv_data,
            file_name="orders_data.csv",
            mime="text/csv"
        )
    else:
        st.info("هیچ سفارشی یافت نشد.")

# ----------------- تب ۲: تقویم شمسی -----------------
with tab_cal:
    if "cal_year" not in st.session_state:
        st.session_state.cal_year = today_jalali.year
    if "cal_month" not in st.session_state:
        st.session_state.cal_month = today_jalali.month

    cal_top_col1, cal_top_col2 = st.columns([2.5, 1.5])
    with cal_top_col2:
        cal_view_mode = st.radio("نوع نمایش تقویم:", ["نمای ماهانه (شبکه‌ای)", "نمای روزانه موبایلی (لیست سفارش‌ها)"], horizontal=True)

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
        st.markdown(f"<h3 style='text-align: center; margin:0; font-weight:800; color:#1e293b;'>{month_names[st.session_state.cal_month - 1]} {st.session_state.cal_year}</h3>", unsafe_allow_html=True)

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

    if cal_view_mode == "نمای روزانه موبایلی (لیست سفارش‌ها)":
        st.info("💡 این نما برای مرور آسان روی نمایشگر گوشی بدون نیاز به چرخش صفحه طراحی شده است.")
        found_any = False
        for day in range(1, days_in_month + 1):
            date_key = f"{current_year}/{current_month:02d}/{day:02d}"
            day_orders = orders_map.get(date_key, [])
            if day_orders:
                found_any = True
                is_today = (current_year == today_jalali.year and current_month == today_jalali.month and day == today_jalali.day)
                today_tag = " <span style='color:#4f46e5; font-size:0.85rem; font-weight:700;'>(امروز)</span>" if is_today else ""
                st.markdown(f"**📌 {day} {month_names[current_month - 1]} {current_year}** {today_tag} — `{len(day_orders)}/{DAILY_CAPACITY_LIMIT} سفارش`", unsafe_allow_html=True)
                for item in day_orders:
                    item_rem = get_effective_remaining(item)
                    badge_class = "badge-paid" if item_rem == 0 else "badge-debt"
                    item_cid = f" ({item.get('customer_id')})" if item.get("customer_id") else ""
                    
                    is_item_archived = (str(item.get("delivery_date", "")) < today_str) or is_order_fully_checked(item)
                    strike_style = "text-decoration: line-through; opacity: 0.65;" if is_item_archived else ""
                    
                    st.markdown(f"""
                    <div style='background:#ffffff; border:1px solid #e2e8f0; border-right:4px solid #4f46e5; padding:10px 14px; border-radius:10px; margin-bottom:8px; font-size:0.88rem; box-shadow:0 1px 3px rgba(0,0,0,0.03); {strike_style}'>
                        📦 <b>{item.get('customer_name')}{item_cid}</b> | مقصد: {item.get('destination_city')} | مانده: {item_rem:,.0f} تومان
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("<hr style='margin:12px 0; border:0; border-top:1px solid #f1f5f9;'>", unsafe_allow_html=True)
        if not found_any:
            st.caption("در این ماه هیچ سفارشی ثبت نشده است.")

    else:
        weekdays_fa = ["شنبه", "۱شنبه", "۲شنبه", "۳شنبه", "۴شنبه", "۵شنبه", "جمعه"]
        cols_header = st.columns(7)
        for idx, day_name in enumerate(weekdays_fa):
            cols_header[idx].markdown(f"<div style='text-align:center; font-weight:700; color:#475569; background:#f1f5f9; padding:8px 4px; border-radius:8px; font-size:0.88rem;'>{day_name}</div>", unsafe_allow_html=True)

        day_counter = 1
        total_slots = start_weekday + days_in_month
        rows = (total_slots + 6) // 7

        for row in range(rows):
            cols = st.columns(7)
            for col_idx in range(7):
                current_slot = row * 7 + col_idx
                with cols[col_idx]:
                    if current_slot < start_weekday or day_counter > days_in_month:
                        st.markdown("<div style='min-height:120px;'></div>", unsafe_allow_html=True)
                    else:
                        date_key = f"{current_year}/{current_month:02d}/{day_counter:02d}"
                        day_orders = orders_map.get(date_key, [])
                        order_count = len(day_orders)
                        
                        is_today = (current_year == today_jalali.year and current_month == today_jalali.month and day_counter == today_jalali.day)
                        is_full = order_count >= DAILY_CAPACITY_LIMIT
                        has_orders = order_count > 0

                        cell_classes = ["calendar-cell"]
                        if is_today:
                            cell_classes.append("cell-today")
                        if is_full:
                            cell_classes.append("cell-full")
                        elif has_orders:
                            cell_classes.append("cell-available")

                        capacity_badge = ""
                        if is_full:
                            capacity_badge = f"<span style='color:#ef4444; font-size:0.75rem; font-weight:800;'>🚨 ({order_count}/{DAILY_CAPACITY_LIMIT})</span>"
                        elif has_orders:
                            capacity_badge = f"<span style='color:#10b981; font-size:0.75rem; font-weight:700;'>🟢 ({order_count}/{DAILY_CAPACITY_LIMIT})</span>"
                        else:
                            capacity_badge = "<span style='color:#94a3b8; font-size:0.72rem;'>خالی</span>"

                        orders_html = ""
                        for item in day_orders[:3]:
                            item_rem = get_effective_remaining(item)
                            badge_class = "badge-paid" if item_rem == 0 else "badge-debt"
                            p_title = item.get('product_name') or item.get('product_desc') or ''
                            item_cid = f" ({item.get('customer_id')})" if item.get("customer_id") else ""
                            
                            is_item_archived = (str(item.get("delivery_date", "")) < today_str) or is_order_fully_checked(item)
                            strike_style = "text-decoration: line-through; opacity: 0.65;" if is_item_archived else ""

                            orders_html += f"<div class='order-badge {badge_class}' style='{strike_style}' title='{p_title}'>📦 {item['customer_name']}{item_cid} ({item['destination_city']})</div>"
                        
                        if len(day_orders) > 3:
                            orders_html += f"<div style='font-size:0.7rem; color:#64748b; font-weight:600; margin-top:2px;'>+ {len(day_orders)-3} سفارش دیگر...</div>"

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
