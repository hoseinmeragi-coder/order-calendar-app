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

# استایل اختصاصی راست‌چین (RTL) و کارت‌های مدرن متریال

st.markdown("""

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
        credentials_dict["private_key"] = credentials_dict["private_key"].replace("\n", "\n")
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
        st.error(f"خطا در ذخیره الگوی دسته‌گل: {e}")
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
        st.error(f"خطا در حذف الگو: {e}")
        return False

@st.cache_data(ttl=120)
def load_pricing_catalog():
    """
    خواندن جدول آنالیز جامع و قیمت‌گذاری محصولات از گوگل شیت.
    پشتیبانی از اقلام عددی مستقیم (مثل پیپاکن) و اقلام مصرفی کسری/مقداری (مثل چسب، ساقه، رنگ و...)
    که به صورت نسبت مصرف یا بهای تمام‌شده واحد محاسبه می‌شوند.
    """
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
        current_category = "گل و متریال"

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

# ----------------- هدر و آمار کلیدی -----------------

st.title("🎛 داشبورد مدیریت، تقویم و آنالیز متریال (نسخه بهینه‌شده)")

total_orders = len(orders_list)
total_revenue = sum(o.get("total_price", 0) for o in orders_list)
pending_balance = sum(get_effective_remaining(o) for o in orders_list)

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(f"""
    کل سفارش‌ها
    {total_orders} عدد
    """, unsafe_allow_html=True)
with m2:
    st.markdown(f"""
    مجموع ارزش سفارش‌ها
    {total_revenue:,.0f} تومان
    """, unsafe_allow_html=True)
with m3:
    st.markdown(f"""
    مجموع مانده حساب‌ها
    {pending_balance:,.0f} تومان
    """, unsafe_allow_html=True)
with m4:
    st.markdown(f"""
    سقف ظرفیت روزانه
    {DAILY_CAPACITY_LIMIT} سفارش
    """, unsafe_allow_html=True)

st.markdown("---")

# تب‌های برنامه

tab_cards, tab_cal, tab_invoice = st.tabs([
    "👥 کارت‌های مشتریان و سفارش‌ها",
    "📅 تقویم شمسی ظرفیت و زمان‌بندی",
    "🧾 صدور فاکتور و آنالیز متریال"
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
                    f"📝 <b>توضیحات و جزئیات متریال:</b><br/>{desc_val if desc_val else '<i>بدون توضیحات</i>'}"
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
                st.checkbox("🎁 آماده‌سازی", value=_is_truthy(order.get("chk_pack", False)), key=k_pk, on_change=lambda oid=order['id'], k=k_pk: update_order_step(oid, "chk_pack", st.session_state[k]))
            with s4:
                st.checkbox("🚚 ارسال پست", value=_is_truthy(order.get("chk_post", False)), key=k_pt, on_change=lambda oid=order['id'], k=k_pt: update_order_step(oid, "chk_post", st.session_state[k]))
            st.markdown("</div>", unsafe_allow_html=True)

        with c_act:
            st.write("")
            if is_archived:
                if st.button("↩️ بازگردانی", key=f"restore_{prefix}_{order['id']}", use_container_width=True):
                    restore_archived_order(order["id"])
            if st.button("🗑️ حذف", key=f"del_{prefix}_{order['id']}", use_container_width=True):
                updated = [o for o in orders_list if str(o["id"]) != str(order["id"])]
                save_orders(updated)
                st.rerun()

# ----------------- تب ۱: کارت‌های مشتریان -----------------

with tab_cards:
    col_t2, col_t1 = st.columns([1, 3])
    with col_t1:
        st.subheader("📋 مدیریت پرونده‌های مشتریان")
    with col_t2:
        search_query = st.text_input("🔍 جستجو (نام، فاکتور، شهر، آیدی)...", "")

    filtered_orders = orders_list
    if search_query:
        filtered_orders = [
            o for o in orders_list 
            if search_query in str(o.get("customer_name", "")) 
            or search_query in str(o.get("invoice_no", ""))
            or search_query in str(o.get("destination_city", ""))
            or search_query in str(o.get("customer_id", ""))
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

        for d in sorted(date_groups.keys()):
            orders_in_date = date_groups[d]
            is_today = (d == today_str)
            today_tag = " — 🎯 تحویل امروز" if is_today else ""
            st.markdown(f"#### 📅 سفارش‌های تاریخ {d}{today_tag} — {len(orders_in_date)} سفارش")
            for idx, order in enumerate(orders_in_date):
                render_order_card(order, prefix=f"act_{d.replace('/', '_')}_{idx}", is_archived=False)

        if past_orders:
            with st.expander(f"📦 بایگانی سفارش‌های گذشته و تکمیل‌شده ({len(past_orders)} سفارش)"):
                for idx, order in enumerate(past_orders):
                    render_order_card(order, prefix=f"arch_{idx}", is_archived=True)
    else:
        st.info("هیچ سفارشی یافت نشد.")

# ----------------- تب ۲: تقویم شمسی -----------------

with tab_cal:
    if "cal_year" not in st.session_state:
        st.session_state.cal_year = today_jalali.year
    if "cal_month" not in st.session_state:
        st.session_state.cal_month = today_jalali.month

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
    days_in_month = 31 if current_month <= 6 else (30 if current_month <= 11 else (30 if jdatetime.date(current_year, 1, 1).isleap() else 29))

    orders_map = {}
    for o in orders_list:
        d = str(o.get("delivery_date", ""))
        if d not in orders_map:
            orders_map[d] = []
        orders_map[d].append(o)

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
                    if is_today: cell_classes.append("cell-today")
                    if is_full: cell_classes.append("cell-full")
                    elif has_orders: cell_classes.append("cell-available")

                    capacity_badge = f"<span style='color:{'#e53e3e' if is_full else '#38a169'}; font-size:0.75rem; font-weight:bold;'>({order_count}/{DAILY_CAPACITY_LIMIT})</span>" if has_orders else "<span style='color:#a0aec0; font-size:0.72rem;'>خالی</span>"

                    orders_html = ""
                    for item in day_orders[:3]:
                        item_rem = get_effective_remaining(item)
                        badge_class = "badge-paid" if item_rem == 0 else "badge-debt"
                        orders_html += f"<div class='order-badge {badge_class}'>📦 {item['customer_name']} ({item['destination_city']})</div>"
                    
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

# ----------------- تب ۳: صدور فاکتور و آنالیز متریال -----------------

with tab_invoice:
    st.subheader("🧾 صدور فاکتور و محاسبه هوشمند هزینه‌های متریال (پیپاکن، چسب، ساقه، رنگ و...)")

    catalog = load_pricing_catalog()
    saved_templates = load_templates()

    if not catalog:
        st.warning("⚠️ شیت قیمت‌گذاری در گوگل شیت یافت نشد یا خالی است.")
    else:
        with st.expander("💐 انتخاب دسته‌گل‌های ذخیره‌شده و الگوهای متریال آماده", expanded=bool(saved_templates)):
            if saved_templates:
                tpl_col1, tpl_col2, tpl_col3 = st.columns([3, 1.2, 0.8])
                with tpl_col1:
                    selected_tpl = st.selectbox("انتخاب الگو:", options=list(saved_templates.keys()), key="select_saved_tpl")
                sel_tpl_obj = saved_templates[selected_tpl]
                sel_tpl_items = sel_tpl_obj["items"] if isinstance(sel_tpl_obj, dict) else sel_tpl_obj
                sel_tpl_img = sel_tpl_obj.get("image", "") if isinstance(sel_tpl_obj, dict) else ""

                with tpl_col2:
                    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                    if st.button("📥 بارگذاری در فاکتور", use_container_width=True, type="primary"):
                        st.session_state.invoice_cart = copy.deepcopy(sel_tpl_items)
                        st.session_state.invoice_template_image = sel_tpl_img
                        st.success(f"الگوی «{selected_tpl}» بارگذاری شد.")
                        st.rerun()
                with tpl_col3:
                    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ حذف الگو", use_container_width=True):
                        if delete_template_item(selected_tpl):
                            st.warning("الگو حذف شد.")
                            st.rerun()

        st.markdown("#### ➕ افزودن متریال / اقلام به فاکتور و محاسبه هزینه")
        categories = ["همه دسته‌ها"] + list(dict.fromkeys([item["category"] for item in catalog if item.get("category")]))
        
        ic1, ic2, ic3, ic4 = st.columns([1.2, 2.2, 1.8, 1])
        with ic1:
            sel_cat = st.selectbox("دسته‌بندی متریال", categories, key="inv_cat")
        
        filtered_catalog = [item for item in catalog if sel_cat == "همه دسته‌ها" or item["category"] == sel_cat]
        product_names = [item["name"] for item in filtered_catalog]

        with ic2:
            sel_prod_name = st.selectbox("انتخاب اقلام متریال / مدل گل", product_names, key="inv_prod")
        
        selected_prod = next((item for item in filtered_catalog if item["name"] == sel_prod_name), None)

        sales_models = [
            "تک شاخه / کمتر از ۶ شاخه",
            "بیشتر از ۶ شاخه",
            "فروش عمده (بالای ۱۲ شاخه)",
            "محاسبه کسری / مصرف مقداری (چسب، ساقه، رنگ...)",
            "قیمت دستی / توافقی"
        ]
        with ic3:
            sel_model = st.selectbox("مدل محاسبه یا فروش", sales_models, key="inv_model")
        
        with ic4:
            sel_qty = st.number_input("تعداد / ضریب مصرف", min_value=0.1, value=1.0, step=0.1, key="inv_qty")

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
            elif sel_model == "محاسبه کسری / مصرف مقداری (چسب، ساقه، رنگ...)":
                default_unit_price = unit_cost if unit_cost > 0 else selected_prod.get("price_single", 0)

        ic_p1, ic_p2, ic_btn = st.columns([2, 2.2, 1.5])
        with ic_p1:
            if sel_model == "قیمت دستی / توافقی" or default_unit_price == 0:
                manual_price_str = st.text_input("قیمت واحد (تومان)", value=f"{default_unit_price:,}" if default_unit_price > 0 else "", key="inv_manual_p")
                final_unit_price = parse_int_price(manual_price_str)
            else:
                final_unit_price = default_unit_price
                st.markdown(f"<div style='background:#f0fff4; border:1px solid #c6f6d5; padding:10px 14px; border-radius:8px; margin-top:24px;'>💵 <b>مبلغ واحد مرجع:</b> {final_unit_price:,.0f} تومان</div>", unsafe_allow_html=True)

        with ic_p2:
            line_total = final_unit_price * sel_qty
            st.markdown(f"<div style='background:#ebf8ff; border:1px solid #bee3f8; padding:10px 14px; border-radius:8px; margin-top:24px;'>🧮 <b>جمع هزینه این ردیف:</b> {line_total:,.0f} تومان</div>", unsafe_allow_html=True)

        with ic_btn:
            st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
            if st.button("➕ افزودن به فاکتور", use_container_width=True, type="primary"):
                if selected_prod:
                    st.session_state.invoice_cart.append({
                        "category": selected_prod["category"],
                        "name": selected_prod["name"],
                        "sales_model": sel_model,
                        "qty": float(sel_qty),
                        "unit_price": int(final_unit_price),
                        "total_price": int(line_total),
                        "unit_cost": int(unit_cost),
                        "total_cost": int(unit_cost * sel_qty)
                    })
                    st.rerun()

        st.markdown("---")

        if st.session_state.invoice_cart:
            st.markdown("#### 🛒 اقلام متریال و سبد فاکتور جاری")
            for idx, item in enumerate(st.session_state.invoice_cart):
                r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns([2.4, 1.5, 1.1, 1.8, 0.6])
                with r_col1:
                    st.markdown(f"<div style='padding-top:8px;'><b>{idx + 1}. {item['name']}</b></div>", unsafe_allow_html=True)
                with r_col2:
                    st.markdown(f"<div style='padding-top:8px; font-size:0.85rem; color:#4a5568;'>{item.get('sales_model', '')}</div>", unsafe_allow_html=True)
                with r_col3:
                    st.markdown(f"<div style='padding-top:8px;'>مقدار: {item['qty']}</div>", unsafe_allow_html=True)
                with r_col4:
                    st.markdown(f"<div style='padding-top:8px;'>کل: <b>{item['total_price']:,.0f} تومان</b></div>", unsafe_allow_html=True)
                with r_col5:
                    if st.button("🗑️", key=f"del_inv_item_{idx}"):
                        st.session_state.invoice_cart.pop(idx)
                        st.rerun()

            items_subtotal = sum(i["total_price"] for i in st.session_state.invoice_cart)
            items_total_cost = sum(i["total_cost"] for i in st.session_state.invoice_cart)

            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                st.markdown(f"<div class='metric-card'><div class='metric-label'>جمع هزینه متریال</div><div class='metric-value'>{items_subtotal:,.0f} تومان</div></div>", unsafe_allow_html=True)
            with mc2:
                st.markdown(f"<div class='metric-card' style='border-color:#3182ce; background:#ebf8ff;'><div class='metric-label' style='color:#2b6cb0;'>بهای تمام‌شده کل</div><div class='metric-value' style='color:#2b6cb0;'>{items_total_cost:,.0f} تومان</div></div>", unsafe_allow_html=True)
            with mc3:
                st.markdown(f"<div class='metric-card' style='border-color:#38a169; background:#f0fff4;'><div class='metric-label' style='color:#2f855a;'>سود خالص تخمینی</div><div class='metric-value' style='color:#2f855a;'>{(items_subtotal - items_total_cost):,.0f} تومان</div></div>", unsafe_allow_html=True)
