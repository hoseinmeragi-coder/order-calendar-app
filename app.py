import streamlit as st
import pandas as pd
from datetime import datetime
import jdatetime
import gspread
from google.oauth2.service_account import Credentials

# تنظیمات اولیه صفحه
st.set_page_config(
    page_title="🌸🌙Moonflo",
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

    /* کارت‌های خلاصه آمار بالا - سازگار با وب‌کیت و مرورگرها */
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
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 16px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03);
        border-right: 6px solid #3182ce;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .order-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.08);
    }
    .badge-status {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .status-completed { background: #c6f6d5; color: #22543d; }
    .status-processing { background: #feebc8; color: #7b341e; }
    .status-pending { background: #edf2f7; color: #4a5568; }
    .status-sent { background: #bee3f8; color: #2a4365; }

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

    /* اصلاح اختصاصی باکس کشویی سفارش‌های گذشته و تفکیک آیکون از متن */
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
    if not val:
        return 0
    clean_str = str(val).replace(",", "").replace("،", "").strip()
    try:
        return int(float(clean_str))
    except Exception:
        return 0

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

@st.cache_data(ttl=60)
def load_orders():
    try:
        ws = get_worksheet()
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return []
        df = pd.DataFrame(vals[1:], columns=vals[0])
        orders = df.to_dict(orient="records")
        for o in orders:
            o["id"] = int(o["id"]) if str(o.get("id", "")).isdigit() else o.get("id", "")
            o["initial_payment"] = parse_int_price(o.get("initial_payment", 0))
            o["remaining_payment"] = parse_int_price(o.get("remaining_payment", 0))
            o["total_price"] = parse_int_price(o.get("total_price", 0)) or (o["initial_payment"] + o["remaining_payment"])
            if "order_created_at" not in o or not o["order_created_at"]:
                o["order_created_at"] = "1400/01/01 00:00"
        return orders
    except Exception:
        return []

def save_orders(orders):
    try:
        ws = get_worksheet()
        if not orders:
            ws.clear()
            st.cache_data.clear()
            return
        df = pd.DataFrame(orders).fillna("").astype(str)
        all_data = [df.columns.tolist()] + df.values.tolist()
        ws.clear()
        ws.update(range_name="A1", values=all_data)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"خطا در همگام‌سازی ابری: {e}")

orders_list = load_orders()

if "show_new_order_modal" not in st.session_state:
    st.session_state.show_new_order_modal = False

if "editing_order_id" not in st.session_state:
    st.session_state.editing_order_id = None

today_jalali = jdatetime.date.today()

month_names = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

# ----------------- هدر و آمار کلیدی -----------------
st.title("🌸🌙Moonflo")

total_orders = len(orders_list)
total_revenue = sum(o.get("total_price", 0) for o in orders_list)
pending_balance = sum(o.get("remaining_payment", 0) for o in orders_list)

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
    title_box = "✏️️ ویرایش مشخصات سفارش" if is_editing else "📦 فرم ثبت سفارش مشتری جدید"
    st.subheader(title_box)

    with st.form("order_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            inv_default = current_order["invoice_no"] if is_editing else f"INV-{len(orders_list)+1001}"
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

        c_prod, c_city, c_date, c_stat = st.columns([1.5, 1, 2, 1.2])
        
        with c_prod:
            prod_name_default = current_order.get("product_name", "") if is_editing else ""
            f_product_name = st.text_input("نام محصول / مدل", value=prod_name_default, placeholder="مثلاً: باکس گل هیدروپونیک رز")

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

        with c_stat:
            statuses = ["در انتظار تایید", "در حال آماده‌سازی", "تکمیل شده", "ارسال شده"]
            stat_idx = statuses.index(current_order["status"]) if is_editing and current_order.get("status") in statuses else 0
            f_status = st.selectbox("وضعیت سفارش", statuses, index=stat_idx)

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
                            "status": f_status
                        })
                save_orders(orders_list)
                st.session_state.editing_order_id = None
                st.session_state.show_new_order_modal = False
                st.success("سفارش با موفقیت در فضای ابری ویرایش شد!")
                st.rerun()
            else:
                new_id = len(orders_list) + 1
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
                    "status": f_status
                }
                orders_list.append(new_item)
                save_orders(orders_list)
                st.session_state.show_new_order_modal = False
                st.success(f"سفارش فاکتور {f_invoice_no} در فضای ابری ثبت شد!")
                st.rerun()

st.markdown("---")

# ----------------- تب‌های برنامه -----------------
tab_cards, tab_cal = st.tabs(["👥 کارت‌های مشتریان و سفارش‌ها", "📅 تقویم شمسی ظرفیت و زمان‌بندی"])

# ----------------- تابع رندر کارت سفارش -----------------
def render_order_card(order):
    status_style = {
        "در انتظار تایید": "status-pending",
        "در حال آماده‌سازی": "status-processing",
        "تکمیل شده": "status-completed",
        "ارسال شده": "status-sent"
    }.get(order.get("status", "در انتظار تایید"), "status-pending")

    with st.container():
        c_card, c_act = st.columns([4.2, 0.8])
        with c_card:
            prod_display = order.get("product_name") or "ثبت نشده"
            c_name = order.get("customer_name") or "بدون نام"
            c_id_tag = f" ({order.get('customer_id')})" if order.get("customer_id") else ""
            inv_no = order.get("invoice_no") or "-"
            c_status = order.get("status") or "نامشخص"
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
            rem_p = order.get("remaining_payment", 0)
            tot_p = order.get("total_price", 0)
            debt_color = "#e53e3e" if rem_p > 0 else "#38a169"

            desc_val = str(order.get("product_desc", "")).strip()
            desc_part = f"<div style='font-size:0.83rem; color:#718096; margin-top:6px;'>📝 <i>توضیحات:</i> {desc_val}</div>" if desc_val else ""

            card_html = (
                f"<div class='order-card'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
                f"<span style='font-weight:bold; font-size:1.15rem; color:#2d3748;'>👤 {c_name}{c_id_tag} <span style='font-size:0.85rem; color:#718096;'>({inv_no})</span></span>"
                f"<span class='badge-status {status_style}'>{c_status}</span>"
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
                f"</div>"
            )
            st.markdown(card_html, unsafe_allow_html=True)

        with c_act:
            st.write("")
            if st.button("✏️ ویرایش", key=f"edit_{order['id']}", use_container_width=True):
                st.session_state.editing_order_id = order["id"]
                st.session_state.show_new_order_modal = False
                st.rerun()

            if st.button("🗑️ حذف", key=f"del_{order['id']}", use_container_width=True):
                updated = [o for o in orders_list if str(o["id"]) != str(order["id"])]
                save_orders(updated)
                st.rerun()

# ----------------- تب ۱: کارت‌های مشتریان -----------------
with tab_cards:
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.subheader("📋 مدیریت پرونده‌های مشتریان")
    with col_t2:
        search_query = st.text_input("🔍 جستجو (نام، فاکتور، شهر، آیدی، تماس)...", "")

    filtered_orders = orders_list
    if search_query:
        filtered_orders = [
            o for o in orders_list 
            if search_query in o.get("customer_name", "") 
            or search_query in o.get("invoice_no", "")
            or search_query in o.get("destination_city", "")
            or search_query in o.get("customer_id", "")
            or search_query in o.get("phone", "")
            or search_query in o.get("emergency_phone", "")
            or search_query in o.get("postal_code", "")
            or search_query in o.get("address", "")
            or search_query in o.get("product_name", "")
        ]

    if filtered_orders:
        sorted_orders = sorted(
            filtered_orders,
            key=lambda x: (x.get("delivery_date", "9999/99/99"), x.get("order_created_at", "9999/99/99 99:99"))
        )

        today_str = today_jalali.strftime("%Y/%m/%d")
        tomorrow_str = (today_jalali + jdatetime.timedelta(days=1)).strftime("%Y/%m/%d")

        today_orders = [o for o in sorted_orders if o.get("delivery_date") == today_str]
        tomorrow_orders = [o for o in sorted_orders if o.get("delivery_date") == tomorrow_str]
        upcoming_orders = [o for o in sorted_orders if o.get("delivery_date", "") > tomorrow_str]
        past_orders = [o for o in sorted_orders if o.get("delivery_date", "") < today_str]

        # بخش ۱: سفارش‌های فردا
        if tomorrow_orders:
            st.markdown(f"#### ⚡ سفارش‌های فردا ({tomorrow_str}) — {len(tomorrow_orders)} سفارش")
            for order in tomorrow_orders:
                render_order_card(order)

        # بخش ۲: سفارش‌های امروز
        if today_orders:
            st.markdown(f"#### 🎯 تحویل‌های امروز ({today_str}) — {len(today_orders)} سفارش")
            for order in today_orders:
                render_order_card(order)

        # بخش ۳: سفارش‌های پیش‌رو
        if upcoming_orders:
            st.markdown(f"#### 📅 سفارش‌های پیش‌رو و آتی — {len(upcoming_orders)} سفارش")
            for order in upcoming_orders:
                render_order_card(order)

        # بخش ۴: سفارش‌های گذشته
        if past_orders:
            with st.expander(f"📦 بایگانی سفارش‌های گذشته و تحویل‌شده ({len(past_orders)} سفارش)"):
                for order in past_orders:
                    render_order_card(order)

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
        d = o.get("delivery_date", "")
        if d not in orders_map:
            orders_map[d] = []
        orders_map[d].append(o)

    if cal_view_mode == "نمای روزانه موبایلی (لیست سفارش‌ها)":
        st.info("💡 این نما برای مرور آسان روی نمایشگر گوشی بدون نیاز به چرخش صفحه طراحی شده است.")
        found_any = False
        for day in range(1, days_in_month + 1):
            date_key = f"{current_year}/{current_month:02d}/{day:02d}"
            day_orders = orders_map.get(date_key, [])
            if day_orders:
                found_any = True
                is_today = (current_year == today_jalali.year and current_month == today_jalali.month and day == today_jalali.day)
                today_tag = " <span style='color:#3182ce; font-size:0.85rem;'>(امروز)</span>" if is_today else ""
                st.markdown(f"**📌 {day} {month_names[current_month - 1]} {current_year}** {today_tag} — `{len(day_orders)}/{DAILY_CAPACITY_LIMIT} سفارش`", unsafe_allow_html=True)
                for item in day_orders:
                    badge_class = "badge-paid" if item.get("remaining_payment", 0) == 0 else "badge-debt"
                    item_cid = f" ({item.get('customer_id')})" if item.get("customer_id") else ""
                    st.markdown(f"""
                    <div style='background:#f8fafc; border-right:4px solid #3182ce; padding:8px 12px; border-radius:6px; margin-bottom:6px; font-size:0.85rem;'>
                        📦 <b>{item.get('customer_name')}{item_cid}</b> | مقصد: {item.get('destination_city')} | مانده: {item.get('remaining_payment', 0):,.0f} تومان
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
        if not found_any:
            st.caption("در این ماه هیچ سفارشی ثبت نشده است.")

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
                            capacity_badge = f"<span style='color:#e53e3e; font-size:0.75rem; font-weight:bold;'>🚨 ({order_count}/{DAILY_CAPACITY_LIMIT})</span>"
                        elif has_orders:
                            capacity_badge = f"<span style='color:#38a169; font-size:0.75rem;'>🟢 ({order_count}/{DAILY_CAPACITY_LIMIT})</span>"
                        else:
                            capacity_badge = "<span style='color:#a0aec0; font-size:0.72rem;'>خالی</span>"

                        orders_html = ""
                        for item in day_orders[:3]:
                            badge_class = "badge-paid" if item.get("remaining_payment", 0) == 0 else "badge-debt"
                            p_title = item.get('product_name') or item.get('product_desc') or ''
                            item_cid = f" ({item.get('customer_id')})" if item.get("customer_id") else ""
                            orders_html += f"<div class='order-badge {badge_class}' title='{p_title}'>📦 {item['customer_name']}{item_cid} ({item['destination_city']})</div>"
                        
                        if len(day_orders) > 3:
                            orders_html += f"<div style='font-size:0.7rem; color:#718096;'>+ {len(day_orders)-3} مورد دیگر...</div>"

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
