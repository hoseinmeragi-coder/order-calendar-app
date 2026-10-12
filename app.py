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
    
    /* استثنا کردن آیکون‌های پیش‌فرض استریم‌لیت جهت عدم نمایش نام کد آیکون */
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

    /* کارت‌های خلاصه آمار بالا */
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

    @media (max-width: 768px) {
        .calendar-cell {
            min-height: 85px;
            padding: 4px;
        }
        .day-num {
            font-size: 0.9rem;
        }
        .order-badge {
            font-size: 0.65rem;
            padding: 1px 3px;
        }
        .order-card {
            padding: 12px;
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
        
        # انجام به‌روزرسانی سلول‌ها بدون clear اولیه جهت ایمنی داده‌ها
        ws.clear()[cite: 1]
        ws.update(range_name="A1", values=all_data)[cite: 1]
        st.cache_data.clear()
    except Exception as e:
        st.error(f"خطا در همگام‌سازی ابری: {e}")

@st.cache_data(ttl=60)
def load_orders():
    try:
        ws = get_worksheet()
        vals = ws.get_all_values()[cite: 1]
        if not vals or len(vals) < 2:
            return []
        df = pd.DataFrame(vals[1:], columns=vals[0])[cite: 1]
        orders = df.to_dict(orient="records")[cite: 1]
        
        numeric_ids = []
        for o in orders:
            val = str(o.get("id", "")).strip()[cite: 1]
            if val.isdigit():
                numeric_ids.append(int(val))[cite: 1]
        current_max_id = max(numeric_ids) if numeric_ids else 0[cite: 1]

        seen_ids = set()
        has_duplicates = False
        for o in orders:
            raw_id = str(o.get("id", "")).strip()[cite: 1]
            if not raw_id or raw_id in seen_ids:
                current_max_id += 1[cite: 1]
                o["id"] = current_max_id[cite: 1]
                has_duplicates = True[cite: 1]
            else:
                o["id"] = int(raw_id) if raw_id.isdigit() else raw_id[cite: 1]
                seen_ids.add(str(o["id"]))[cite: 1]

            o["phone"] = clean_phone_str(o.get("phone", ""))[cite: 1]
            o["emergency_phone"] = clean_phone_str(o.get("emergency_phone", ""))[cite: 1]
            o["postal_code"] = clean_phone_str(o.get("postal_code", ""))[cite: 1]

            o["initial_payment"] = parse_int_price(o.get("initial_payment", 0))[cite: 1]
            o["remaining_payment"] = parse_int_price(o.get("remaining_payment", 0))[cite: 1]
            o["total_price"] = parse_int_price(o.get("total_price", 0)) or (o["initial_payment"] + o["remaining_payment"])[cite: 1]
            if "order_created_at" not in o or not o["order_created_at"]:
                o["order_created_at"] = "1400/01/01 00:00"[cite: 1]

            o["chk_deposit"] = _is_truthy(o.get("chk_deposit", False))[cite: 1]
            o["chk_photo"] = _is_truthy(o.get("chk_photo", False))[cite: 1]
            o["chk_settle"] = _is_truthy(o.get("chk_settle", False))[cite: 1]
            o["chk_pack"] = _is_truthy(o.get("chk_pack", False))[cite: 1]
            o["chk_post"] = _is_truthy(o.get("chk_post", False))[cite: 1]
            o["order_image"] = str(o.get("order_image", ""))

        if has_duplicates:
            save_orders(orders)[cite: 1]

        return orders
    except Exception as e:
        st.warning(f"عدم امکان خواندن اطلاعات شیت: {e}")
        return []

orders_list = load_orders()[cite: 1]

def get_next_id(orders):
    n_ids = [int(o["id"]) for o in orders if str(o.get("id", "")).isdigit()][cite: 1]
    return (max(n_ids) if n_ids else 0) + 1[cite: 1]

def get_next_invoice_no(orders):
    max_inv = 1000[cite: 1]
    for o in orders:
        inv = str(o.get("invoice_no", "")).strip()[cite: 1]
        if inv.startswith("INV-") and inv[4:].isdigit():[cite: 1]
            max_inv = max(max_inv, int(inv[4:]))[cite: 1]
    return f"INV-{max_inv + 1}"[cite: 1]

if "show_new_order_modal" not in st.session_state:
    st.session_state.show_new_order_modal = False[cite: 1]

if "editing_order_id" not in st.session_state:
    st.session_state.editing_order_id = None[cite: 1]

today_jalali = jdatetime.date.today()[cite: 1]

month_names = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
][cite: 1]

def get_effective_remaining(o):
    if _is_truthy(o.get("chk_settle", False)):[cite: 1]
        return 0[cite: 1]
    return o.get("remaining_payment", 0)[cite: 1]

# ----------------- هدر و آمار کلیدی -----------------
st.title("🎛 داشبورد مدیریت و تقویم شمسی سفارش‌ها (ابری)")[cite: 1]

total_orders = len(orders_list)[cite: 1]
total_revenue = sum(o.get("total_price", 0) for o in orders_list)[cite: 1]
pending_balance = sum(get_effective_remaining(o) for o in orders_list)[cite: 1]

m1, m2, m3, m4 = st.columns(4)[cite: 1]
with m1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">کل سفارش‌ها</div>
        <div class="metric-value">{total_orders} عدد</div>
    </div>
    """, unsafe_allow_html=True)[cite: 1]
with m2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">مجموع ارزش سفارش‌ها</div>
        <div class="metric-value">{total_revenue:,.0f} تومان</div>
    </div>
    """, unsafe_allow_html=True)[cite: 1]
with m3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">مجموع مانده حساب‌ها</div>
        <div class="metric-value">{pending_balance:,.0f} تومان</div>
    </div>
    """, unsafe_allow_html=True)[cite: 1]
with m4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">سقف ظرفیت روزانه</div>
        <div class="metric-value">{DAILY_CAPACITY_LIMIT} سفارش</div>
    </div>
    """, unsafe_allow_html=True)[cite: 1]

st.markdown("---")[cite: 1]

# ----------------- دکمه ثبت سفارش جدید -----------------
col_btn, _ = st.columns([1.5, 4])[cite: 1]
with col_btn:
    btn_text = "❌ بستن فرم ثبت سفارش" if st.session_state.show_new_order_modal else "✨ افزودن و ثبت سفارش جدید"[cite: 1]
    if st.button(btn_text, use_container_width=True, type="primary"):[cite: 1]
        st.session_state.show_new_order_modal = not st.session_state.show_new_order_modal[cite: 1]
        st.session_state.editing_order_id = None[cite: 1]
        st.rerun()[cite: 1]

# ----------------- بخش ثبت / ویرایش سفارش -----------------
is_editing = st.session_state.editing_order_id is not None[cite: 1]
if st.session_state.show_new_order_modal or is_editing:
    current_order = None[cite: 1]
    if is_editing:
        current_order = next((o for o in orders_list if str(o["id"]) == str(st.session_state.editing_order_id)), None)[cite: 1]

    st.markdown("---")[cite: 1]
    title_box = "✏ ویرایش مشخصات سفارش" if is_editing else "📦 فرم ثبت سفارش مشتری جدید"[cite: 1]
    st.subheader(title_box)[cite: 1]

    with st.form("order_form", clear_on_submit=False):[cite: 1]
        c1, c2, c3, c4 = st.columns(4)[cite: 1]
        with c1:
            inv_default = current_order["invoice_no"] if is_editing else get_next_invoice_no(orders_list)[cite: 1]
            f_invoice_no = st.text_input("شماره فاکتور", value=inv_default)[cite: 1]
        with c2:
            c_name_default = current_order["customer_name"] if is_editing else ""[cite: 1]
            f_customer_name = st.text_input("نام و نام خانوادگی مشتری", value=c_name_default, placeholder="مثلاً: علیرضا محمدی")[cite: 1]
        with c3:
            phone_default = current_order.get("phone", "") if is_editing else ""[cite: 1]
            f_phone = st.text_input("شماره تماس", value=phone_default, placeholder="مثلاً: 09123456789")[cite: 1]
        with c4:
            emergency_phone_default = current_order.get("emergency_phone", "") if is_editing else ""[cite: 1]
            f_emergency_phone = st.text_input("شماره تماس اضطراری", value=emergency_phone_default, placeholder="شماره تماس دوم یا معرف")[cite: 1]

        c_info1, c_info2, c_info3 = st.columns([1.5, 1.5, 3])[cite: 1]
        with c_info1:
            c_id_default = current_order.get("customer_id", "") if is_editing else ""[cite: 1]
            f_customer_id = st.text_input("آیدی / نام کاربری مشتری", value=c_id_default, placeholder="@username یا شناسه")[cite: 1]
        with c_info2:
            postal_code_default = current_order.get("postal_code", "") if is_editing else ""[cite: 1]
            f_postal_code = st.text_input("کد پستی", value=postal_code_default, placeholder="کد پستی ۱۰ رقمی")[cite: 1]
        with c_info3:
            address_default = current_order.get("address", "") if is_editing else ""[cite: 1]
            f_address = st.text_input("آدرس پستی کامل", value=address_default, placeholder="استان، شهر، خیابان، کوچه، پلاک، واحد")[cite: 1]

        c_prod, c_city, c_date = st.columns([1.5, 1.2, 2.3])[cite: 1]
        
        with c_prod:
            prod_name_default = current_order.get("product_name", "") if is_editing else ""[cite: 1]
            f_product_name = st.text_input("نام محصول / مدل", value=prod_name_default, placeholder="مثلاً: باکس گل رز")

        with c_city:
            city_default = current_order.get("destination_city", "") if is_editing else ""[cite: 1]
            f_destination_city = st.text_input("شهر مقصد", value=city_default, placeholder="مثلاً: مشهد، تهران...")[cite: 1]

        with c_date:
            st.markdown("<p style='font-weight:600; margin-bottom:5px;'>📅 تاریخ تحویل / ارسال (شمسی)</p>", unsafe_allow_html=True)[cite: 1]
            cd_d, cd_m, cd_y = st.columns([1, 1.5, 1.2])[cite: 1]
            
            d_def, m_def, y_def = today_jalali.day, today_jalali.month, today_jalali.year[cite: 1]
            if is_editing and current_order.get("delivery_date"):[cite: 1]
                try:
                    parts = current_order["delivery_date"].split("/")[cite: 1]
                    y_def, m_def, d_def = int(parts[0]), int(parts[1]), int(parts[2])[cite: 1]
                except Exception:
                    pass

            with cd_d:
                f_day = st.selectbox("روز", list(range(1, 32)), index=min(d_def - 1, 30))[cite: 1]
            with cd_m:
                f_month_name = st.selectbox("ماه", month_names, index=m_def - 1)[cite: 1]
                f_month = month_names.index(f_month_name) + 1[cite: 1]
            with cd_y:
                f_year = st.selectbox("سال", [today_jalali.year - 1, today_jalali.year, today_jalali.year + 1], index=1)[cite: 1]

            try:
                delivery_jdate = jdatetime.date(f_year, f_month, f_day)[cite: 1]
                f_delivery_str = delivery_jdate.strftime("%Y/%m/%d")[cite: 1]
            except ValueError:
                delivery_jdate = jdatetime.date(f_year, f_month, 29)[cite: 1]
                f_delivery_str = delivery_jdate.strftime("%Y/%m/%d")[cite: 1]

        cp1, cp2, cp3 = st.columns(3)[cite: 1]
        with cp1:
            init_val_num = int(current_order["initial_payment"]) if is_editing else 0[cite: 1]
            init_val_str = f"{init_val_num:,}" if init_val_num > 0 else ""[cite: 1]
            f_init_raw = st.text_input("واریزی اول / پیش‌پرداخت (تومان)", value=init_val_str, placeholder="مثلاً: 500,000")[cite: 1]
            parsed_init = parse_int_price(f_init_raw)[cite: 1]
            if parsed_init > 0:
                st.caption(f"🔎 تفکیک‌شده: **{parsed_init:,}** تومان")[cite: 1]

        with cp2:
            rem_val_num = int(current_order["remaining_payment"]) if is_editing else 0[cite: 1]
            rem_val_str = f"{rem_val_num:,}" if rem_val_num > 0 else ""[cite: 1]
            f_rem_raw = st.text_input("مانده تسویه (تومان)", value=rem_val_str, placeholder="مثلاً: 250,000")[cite: 1]
            parsed_rem = parse_int_price(f_rem_raw)[cite: 1]
            if parsed_rem > 0:
                st.caption(f"🔎 تفکیک‌شده: **{parsed_rem:,}** تومان")[cite: 1]

        with cp3:
            track_val = current_order.get("tracking_code", "") if is_editing else ""[cite: 1]
            if track_val == "ثبت نشده":[cite: 1]
                track_val = ""[cite: 1]
            f_track_code = st.text_input("کد رهگیری پستی (اختیاری)", value=track_val, placeholder="کد رهگیری ۲۴ رقمی...")[cite: 1]

        desc_val = current_order.get("product_desc", "") if is_editing else ""[cite: 1]
        f_product_desc = st.text_area("شرح محصول و جزئیات ساخت", value=desc_val, placeholder="ابعاد، رنگ، متریال، نحوه بسته‌بندی...")[cite: 1]

        # آپلود تصویر سفارش
        f_uploaded_image = st.file_uploader("🖼️ آپلود عکس سفارش مشتری (اختیاری)", type=["png", "jpg", "jpeg", "webp"])

        col_sub, col_cancel = st.columns([1, 1])[cite: 1]
        with col_sub:
            btn_submit_label = "💾 ذخیره تغییرات سفارش" if is_editing else "✅ تایید و ثبت نهایی سفارش"[cite: 1]
            submitted = st.form_submit_button(btn_submit_label, use_container_width=True, type="primary")[cite: 1]
        with col_cancel:
            cancelled = st.form_submit_button("انصراف", use_container_width=True)[cite: 1]

        if cancelled:
            st.session_state.show_new_order_modal = False[cite: 1]
            st.session_state.editing_order_id = None[cite: 1]
            st.rerun()[cite: 1]

        if submitted:
            f_init_pay = parse_int_price(f_init_raw)[cite: 1]
            f_rem_pay = parse_int_price(f_rem_raw)[cite: 1]
            now_jalali = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")[cite: 1]
            
            # فشرده‌سازی و تبدیل تصویر به Base64
            img_b64 = ""
            if f_uploaded_image is not None:
                img_b64 = compress_image_to_base64(f_uploaded_image)
            elif is_editing and current_order:
                img_b64 = current_order.get("order_image", "")

            if is_editing:
                for o in orders_list:
                    if str(o["id"]) == str(current_order["id"]):[cite: 1]
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
                        })[cite: 1]
                        break
                save_orders(orders_list)[cite: 1]
                st.session_state.editing_order_id = None[cite: 1]
                st.session_state.show_new_order_modal = False[cite: 1]
                st.success("سفارش با موفقیت در فضای ابری ویرایش شد!")[cite: 1]
                st.rerun()[cite: 1]
            else:
                new_id = get_next_id(orders_list)[cite: 1]
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
                }[cite: 1]
                orders_list.append(new_item)[cite: 1]
                save_orders(orders_list)[cite: 1]
                st.session_state.show_new_order_modal = False[cite: 1]
                st.success(f"سفارش فاکتور {f_invoice_no} در فضای ابری ثبت شد!")[cite: 1]
                st.rerun()[cite: 1]

st.markdown("---")[cite: 1]

# ----------------- تب‌های برنامه -----------------
tab_cards, tab_cal = st.tabs(["👥 کارت‌های مشتریان و سفارش‌ها", "📅 تقویم شمسی ظرفیت و زمان‌بندی"])[cite: 1]

def is_order_fully_checked(order):
    return (
        _is_truthy(order.get("chk_deposit", False)) and
        _is_truthy(order.get("chk_photo", False)) and
        _is_truthy(order.get("chk_settle", False)) and
        _is_truthy(order.get("chk_pack", False)) and
        _is_truthy(order.get("chk_post", False))
    )[cite: 1]

def update_order_step(order_id, step_key, value):
    for o in orders_list:
        if str(o.get("id")) == str(order_id):[cite: 1]
            o[step_key] = bool(value)[cite: 1]
            break
    save_orders(orders_list)[cite: 1]
    st.cache_data.clear()[cite: 1]
    st.rerun()[cite: 1]

def restore_archived_order(order_id):
    today_str = today_jalali.strftime("%Y/%m/%d")[cite: 1]
    for o in orders_list:
        if str(o.get("id")) == str(order_id):[cite: 1]
            o["chk_post"] = False[cite: 1]
            if str(o.get("delivery_date", "")) < today_str:[cite: 1]
                o["delivery_date"] = today_str[cite: 1]
            break
    save_orders(orders_list)[cite: 1]
    st.cache_data.clear()[cite: 1]
    st.rerun()[cite: 1]

def render_order_card(order, prefix="card", is_archived=False):
    with st.container():[cite: 1]
        c_card, c_act = st.columns([4.2, 0.8])[cite: 1]
        with c_card:
            prod_display = order.get("product_name") or "ثبت نشده"[cite: 1]
            c_name = order.get("customer_name") or "بدون نام"[cite: 1]
            c_id_tag = f" ({order.get('customer_id')})" if order.get("customer_id") else ""[cite: 1]
            inv_no = order.get("invoice_no") or "-"[cite: 1]
            city = order.get("destination_city") or "-"[cite: 1]
            deliv_date = order.get("delivery_date") or "-"[cite: 1]
            track_no = order.get("tracking_code") or "-"[cite: 1]
            created_at = order.get("order_created_at") or "-"[cite: 1]
            
            phone_val = str(order.get("phone", "")).strip()[cite: 1]
            cid_val = str(order.get("customer_id", "")).strip()[cite: 1]
            contact_display = phone_val if phone_val else (cid_val if cid_val else "-")[cite: 1]
            
            em_val = str(order.get("emergency_phone", "")).strip()[cite: 1]
            em_part = f"<span>🚨 <b>اضطراری:</b> {em_val}</span>" if em_val else ""[cite: 1]

            post_val = str(order.get("postal_code", "")).strip()[cite: 1]
            post_part = f"<span>📮 <b>کد پستی:</b> {post_val}</span>" if post_val else ""[cite: 1]

            addr_val = str(order.get("address", "")).strip()[cite: 1]
            addr_part = f"<div style='font-size:0.85rem; color:#4a5568; margin-top:6px;'>🏠 <b>آدرس:</b> {addr_val}</div>" if addr_val else ""[cite: 1]

            init_p = order.get("initial_payment", 0)[cite: 1]
            
            is_settled = _is_truthy(order.get("chk_settle", False))[cite: 1]
            rem_p = 0 if is_settled else order.get("remaining_payment", 0)[cite: 1]
            tot_p = order.get("total_price", 0)[cite: 1]
            debt_color = "#38a169" if rem_p == 0 else "#e53e3e"[cite: 1]

            desc_val = str(order.get("product_desc", "")).strip()[cite: 1]
            desc_part = f"<div style='font-size:0.83rem; color:#718096; margin-top:6px;'>📝 <i>توضیحات:</i> {desc_val}</div>" if desc_val else ""[cite: 1]

            # تصویر فشرده سفارش
            img_val = str(order.get("order_image", "")).strip()
            img_html = ""
            if img_val and img_val.lower() != "nan":
                img_html = f"<div style='margin-top:10px;'><img src='data:image/jpeg;base64,{img_val}' style='max-width:160px; max-height:160px; border-radius:8px; border:1px solid #cbd5e1; object-fit:cover;'/></div>"

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
                f"{desc_part}"
                f"{img_html}"
                f"</div>"
            )
            st.markdown(card_html, unsafe_allow_html=True)[cite: 1]

            # چک‌لیست مراحل سفارش
            st.markdown("<div class='order-steps-container'>", unsafe_allow_html=True)[cite: 1]
            s0, s1, s2, s3, s4 = st.columns(5)[cite: 1]
            
            k_d = f"d_{prefix}_{order['id']}"[cite: 1]
            k_p = f"p_{prefix}_{order['id']}"[cite: 1]
            k_s = f"s_{prefix}_{order['id']}"[cite: 1]
            k_pk = f"pk_{prefix}_{order['id']}"[cite: 1]
            k_pt = f"pt_{prefix}_{order['id']}"[cite: 1]

            with s0:
                st.checkbox(
                    "💵 واریز بیعانه",
                    value=_is_truthy(order.get("chk_deposit", False)),
                    key=k_d,
                    on_change=lambda oid=order['id'], k=k_d: update_order_step(oid, "chk_deposit", st.session_state[k])
                )[cite: 1]
            with s1:
                st.checkbox(
                    "📷 ارسال عکس برای تسویه",
                    value=_is_truthy(order.get("chk_photo", False)),
                    key=k_p,
                    on_change=lambda oid=order['id'], k=k_p: update_order_step(oid, "chk_photo", st.session_state[k])
                )[cite: 1]
            with s2:
                st.checkbox(
                    "💳 تسویه",
                    value=_is_truthy(order.get("chk_settle", False)),
                    key=k_s,
                    on_change=lambda oid=order['id'], k=k_s: update_order_step(oid, "chk_settle", st.session_state[k])
                )[cite: 1]
            with s3:
                st.checkbox(
                    "🎁 آماده‌سازی بسته",
                    value=_is_truthy(order.get("chk_pack", False)),
                    key=k_pk,
                    on_change=lambda oid=order['id'], k=k_pk: update_order_step(oid, "chk_pack", st.session_state[k])
                )[cite: 1]
            with s4:
                st.checkbox(
                    "🚚 تحویل به پست",
                    value=_is_truthy(order.get("chk_post", False)),
                    key=k_pt,
                    on_change=lambda oid=order['id'], k=k_pt: update_order_step(oid, "chk_post", st.session_state[k])
                )[cite: 1]
            st.markdown("</div>", unsafe_allow_html=True)[cite: 1]

        with c_act:
            st.write("")[cite: 1]
            if is_archived:
                if st.button("↩️ بازگردانی", key=f"restore_{prefix}_{order['id']}", use_container_width=True):[cite: 1]
                    restore_archived_order(order["id"])[cite: 1]

            if st.button("✏️ ویرایش", key=f"edit_{prefix}_{order['id']}", use_container_width=True):[cite: 1]
                st.session_state.editing_order_id = order["id"][cite: 1]
                st.session_state.show_new_order_modal = False[cite: 1]
                st.rerun()[cite: 1]

            if st.button("🗑️ حذف", key=f"del_{prefix}_{order['id']}", use_container_width=True):[cite: 1]
                updated = [o for o in orders_list if str(o["id"]) != str(order["id"])][cite: 1]
                save_orders(updated)[cite: 1]
                st.rerun()[cite: 1]

# ----------------- تب ۱: کارت‌های مشتریان -----------------
with tab_cards:[cite: 1]
    col_t2, col_t1 = st.columns([1, 3])[cite: 1]
    with col_t1:
        st.subheader("📋 مدیریت پرونده‌های مشتریان")[cite: 1]
    with col_t2:
        search_query = st.text_input("🔍 جستجو (نام، فاکتور، شهر، آیدی، تماس)...", "")[cite: 1]

    filtered_orders = orders_list[cite: 1]
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
        ][cite: 1]

    if filtered_orders:
        sorted_orders = sorted(
            filtered_orders,
            key=lambda x: (str(x.get("delivery_date", "9999/99/99")), str(x.get("order_created_at", "9999/99/99 99:99")))
        )[cite: 1]

        today_str = today_jalali.strftime("%Y/%m/%d")[cite: 1]

        past_orders = [
            o for o in sorted_orders 
            if str(o.get("delivery_date", "")) < today_str or is_order_fully_checked(o)
        ][cite: 1]
        
        active_orders = [
            o for o in sorted_orders 
            if str(o.get("delivery_date", "")) >= today_str and not is_order_fully_checked(o)
        ][cite: 1]

        date_groups = {}
        for o in active_orders:
            d = str(o.get("delivery_date", "نامشخص"))[cite: 1]
            if d not in date_groups:[cite: 1]
                date_groups[d] = [][cite: 1]
            date_groups[d].append(o)[cite: 1]

        active_dates = sorted(list(date_groups.keys()))[cite: 1]

        for d in active_dates:
            orders_in_date = date_groups[d][cite: 1]
            is_today = (d == today_str)[cite: 1]
            today_tag = " — 🎯 تحویل امروز" if is_today else ""[cite: 1]
            st.markdown(f"#### 📅 سفارش‌های تاریخ {d}{today_tag} — {len(orders_in_date)} سفارش")[cite: 1]
            for idx, order in enumerate(orders_in_date):[cite: 1]
                render_order_card(order, prefix=f"act_{d.replace('/', '_')}_{idx}", is_archived=False)[cite: 1]

        if past_orders:
            with st.expander(f"📦 بایگانی سفارش‌های گذشته و تکمیل‌شده ({len(past_orders)} سفارش)"):[cite: 1]
                for idx, order in enumerate(past_orders):[cite: 1]
                    render_order_card(order, prefix=f"arch_{idx}", is_archived=True)[cite: 1]

        st.markdown("---")[cite: 1]
        df_export = pd.DataFrame(orders_list)[cite: 1]
        csv_data = df_export.to_csv(index=False).encode('utf-8-sig')[cite: 1]
        st.download_button(
            label="📥 دریافت فایل اکسل / CSV سفارش‌ها",
            data=csv_data,
            file_name="orders_data.csv",
            mime="text/csv"
        )[cite: 1]
    else:
        st.info("هیچ سفارشی یافت نشد.")[cite: 1]

# ----------------- تب ۲: تقویم شمسی -----------------
with tab_cal:[cite: 1]
    if "cal_year" not in st.session_state:
        st.session_state.cal_year = today_jalali.year[cite: 1]
    if "cal_month" not in st.session_state:
        st.session_state.cal_month = today_jalali.month[cite: 1]

    cal_top_col1, cal_top_col2 = st.columns([2.5, 1.5])[cite: 1]
    with cal_top_col2:
        cal_view_mode = st.radio("نوع نمایش تقویم:", ["نمای ماهانه (شبکه‌ای)", "نمای روزانه موبایلی (لیست سفارش‌ها)"], horizontal=True)[cite: 1]

    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])[cite: 1]
    
    with col_nav1:
        if st.button("⬅ ماه قبل", use_container_width=True, key="prev_m"):[cite: 1]
            if st.session_state.cal_month == 1:[cite: 1]
                st.session_state.cal_month = 12[cite: 1]
                st.session_state.cal_year -= 1[cite: 1]
            else:
                st.session_state.cal_month -= 1[cite: 1]
            st.rerun()[cite: 1]

    with col_nav2:
        st.markdown(f"<h3 style='text-align: center; margin:0;'>{month_names[st.session_state.cal_month - 1]} {st.session_state.cal_year}</h3>", unsafe_allow_html=True)[cite: 1]

    with col_nav3:
        if st.button("ماه بعد ➡️", use_container_width=True, key="next_m"):[cite: 1]
            if st.session_state.cal_month == 12:[cite: 1]
                st.session_state.cal_month = 1[cite: 1]
                st.session_state.cal_year += 1[cite: 1]
            else:
                st.session_state.cal_month += 1[cite: 1]
            st.rerun()[cite: 1]

    current_year = st.session_state.cal_year[cite: 1]
    current_month = st.session_state.cal_month[cite: 1]
    
    first_day_of_month = jdatetime.date(current_year, current_month, 1)[cite: 1]
    start_weekday = first_day_of_month.weekday()[cite: 1]
    
    if current_month <= 6:[cite: 1]
        days_in_month = 31[cite: 1]
    elif current_month <= 11:[cite: 1]
        days_in_month = 30[cite: 1]
    else:
        days_in_month = 30 if jdatetime.date(current_year, 1, 1).isleap() else 29[cite: 1]

    orders_map = {}[cite: 1]
    for o in orders_list:[cite: 1]
        d = str(o.get("delivery_date", ""))[cite: 1]
        if d not in orders_map:[cite: 1]
            orders_map[d] = [][cite: 1]
        orders_map[d].append(o)[cite: 1]

    today_str = today_jalali.strftime("%Y/%m/%d")[cite: 1]

    if cal_view_mode == "نمای روزانه موبایلی (لیست سفارش‌ها)":[cite: 1]
        st.info("💡 این نما برای مرور آسان روی نمایشگر گوشی بدون نیاز به چرخش صفحه طراحی شده است.")[cite: 1]
        found_any = False[cite: 1]
        for day in range(1, days_in_month + 1):[cite: 1]
            date_key = f"{current_year}/{current_month:02d}/{day:02d}"[cite: 1]
            day_orders = orders_map.get(date_key, [])[cite: 1]
            if day_orders:[cite: 1]
                found_any = True[cite: 1]
                is_today = (current_year == today_jalali.year and current_month == today_jalali.month and day == today_jalali.day)[cite: 1]
                today_tag = " <span style='color:#3182ce; font-size:0.85rem;'>(امروز)</span>" if is_today else ""[cite: 1]
                st.markdown(f"**📌 {day} {month_names[current_month - 1]} {current_year}** {today_tag} — `{len(day_orders)}/{DAILY_CAPACITY_LIMIT} سفارش`", unsafe_allow_html=True)[cite: 1]
                for item in day_orders:[cite: 1]
                    item_rem = get_effective_remaining(item)[cite: 1]
                    badge_class = "badge-paid" if item_rem == 0 else "badge-debt"[cite: 1]
                    item_cid = f" ({item.get('customer_id')})" if item.get("customer_id") else ""[cite: 1]
                    
                    is_item_archived = (str(item.get("delivery_date", "")) < today_str) or is_order_fully_checked(item)[cite: 1]
                    strike_style = "text-decoration: line-through; opacity: 0.65;" if is_item_archived else ""[cite: 1]
                    
                    st.markdown(f"""
                    <div style='background:#f8fafc; border-right:4px solid #3182ce; padding:8px 12px; border-radius:6px; margin-bottom:6px; font-size:0.85rem; {strike_style}'>
                        📦 <b>{item.get('customer_name')}{item_cid}</b> | مقصد: {item.get('destination_city')} | مانده: {item_rem:,.0f} تومان
                    </div>
                    """, unsafe_allow_html=True)[cite: 1]
                st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)[cite: 1]
        if not found_any:[cite: 1]
            st.caption("در این ماه هیچ سفارشی ثبت نشده است.")[cite: 1]

    else:
        weekdays_fa = ["شنبه", "۱شنبه", "۲شنبه", "۳شنبه", "۴شنبه", "۵شنبه", "جمعه"][cite: 1]
        cols_header = st.columns(7)[cite: 1]
        for idx, day_name in enumerate(weekdays_fa):[cite: 1]
            cols_header[idx].markdown(f"<div style='text-align:center; font-weight:bold; background:#edf2f7; padding:6px; border-radius:6px;'>{day_name}</div>", unsafe_allow_html=True)[cite: 1]

        day_counter = 1[cite: 1]
        total_slots = start_weekday + days_in_month[cite: 1]
        rows = (total_slots + 6) // 7[cite: 1]

        for row in range(rows):[cite: 1]
            cols = st.columns(7)[cite: 1]
            for col_idx in range(7):[cite: 1]
                current_slot = row * 7 + col_idx[cite: 1]
                with cols[col_idx]:[cite: 1]
                    if current_slot < start_weekday or day_counter > days_in_month:[cite: 1]
                        st.markdown("<div style='min-height:110px;'></div>", unsafe_allow_html=True)[cite: 1]
                    else:
                        date_key = f"{current_year}/{current_month:02d}/{day_counter:02d}"[cite: 1]
                        day_orders = orders_map.get(date_key, [])[cite: 1]
                        order_count = len(day_orders)[cite: 1]
                        
                        is_today = (current_year == today_jalali.year and current_month == today_jalali.month and day_counter == today_jalali.day)[cite: 1]
                        is_full = order_count >= DAILY_CAPACITY_LIMIT[cite: 1]
                        has_orders = order_count > 0[cite: 1]

                        cell_classes = ["calendar-cell"][cite: 1]
                        if is_today:[cite: 1]
                            cell_classes.append("cell-today")[cite: 1]
                        if is_full:[cite: 1]
                            cell_classes.append("cell-full")[cite: 1]
                        elif has_orders:[cite: 1]
                            cell_classes.append("cell-available")[cite: 1]

                        capacity_badge = ""[cite: 1]
                        if is_full:[cite: 1]
                            capacity_badge = f"<span style='color:#e53e3e; font-size:0.75rem; font-weight:bold;'>🚨 ({order_count}/{DAILY_CAPACITY_LIMIT})</span>"[cite: 1]
                        elif has_orders:[cite: 1]
                            capacity_badge = f"<span style='color:#38a169; font-size:0.75rem;'>🟢 ({order_count}/{DAILY_CAPACITY_LIMIT})</span>"[cite: 1]
                        else:
                            capacity_badge = "<span style='color:#a0aec0; font-size:0.72rem;'>خالی</span>"[cite: 1]

                        orders_html = ""[cite: 1]
                        for item in day_orders[:3]:[cite: 1]
                            item_rem = get_effective_remaining(item)[cite: 1]
                            badge_class = "badge-paid" if item_rem == 0 else "badge-debt"[cite: 1]
                            p_title = item.get('product_name') or item.get('product_desc') or ''[cite: 1]
                            item_cid = f" ({item.get('customer_id')})" if item.get("customer_id") else ""[cite: 1]
                            
                            is_item_archived = (str(item.get("delivery_date", "")) < today_str) or is_order_fully_checked(item)[cite: 1]
                            strike_style = "text-decoration: line-through; opacity: 0.65;" if is_item_archived else ""[cite: 1]

                            orders_html += f"<div class='order-badge {badge_class}' style='{strike_style}' title='{p_title}'>📦 {item['customer_name']}{item_cid} ({item['destination_city']})</div>"[cite: 1]
                        
                        if len(day_orders) > 3:[cite: 1]
                            orders_html += f"<div style='font-size:0.7rem; color:#718096;'>+ {len(day_orders)-3} مورد دیگر...</div>"[cite: 1]

                        st.markdown(f"""
                        <div class="{' '.join(cell_classes)}">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span class="day-num">{day_counter}</span>
                                {capacity_badge}
                            </div>
                            {orders_html}
                        </div>
                        """, unsafe_allow_html=True)[cite: 1]
                        
                        day_counter += 1[cite: 1]
