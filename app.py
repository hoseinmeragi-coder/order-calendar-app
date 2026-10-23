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

استایل اختصاصی راست‌‌چین (RTL) و کارت‌های مدرن + حل تداخل آیکون‌های Expander

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

----------------- ارتباط با Google Sheets -----------------

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

def get_inventory_worksheet():
"""دریافت یا ساخت شیت انبار در گوگل شیت"""
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
"""بارگذاری موجودی انبار از گوگل شیت"""
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
            "current_stock": float(row[2]) if len(row) > 2 and str(row[2]).replace(".", "").replace("-", "").isdigit() else 0.0,
            "min_threshold": float(row[3]) if len(row) > 3 and str(row[3]).replace(".", "").isdigit() else 5.0
        })
    return inventory_items
except Exception:
    return []


def update_inventory_stock(consumed_items):
"""کسر خودکار متریال مصرف‌شده از انبار پس از ثبت سفارش"""
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

----------------- هدر و آمار کلیدی -----------------

st.title("🎛 داشبورد مدیریت، تقویم و انبارداری (ابری)")

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
        f_emergency_phone = st.text_input("شماره تماس اضطراری", value=emergency_phone_default, placeholder="شماره تماس دوم")

    c_info1, c_info2, c_info3 = st.columns([1.5, 1.5, 3])
    with c_info1:
        c_id_default = current_order.get("customer_id", "") if is_editing else ""
        f_customer_id = st.text_input("آیدی / نام کاربری مشتری", value=c_id_default, placeholder="@username")
    with c_info2:
        postal_code_default = current_order.get("postal_code", "") if is_editing else ""
        f_postal_code = st.text_input("کد پستی", value=postal_code_default, placeholder="کد پستی ۱۰ رقمی")
    with c_info3:
        address_default = current_order.get("address", "") if is_editing else ""
        f_address = st.text_input("آدرس پستی کامل", value=address_default, placeholder="استان، شهر، خیابان...")

    c_prod, c_city, c_date = st.columns([1.5, 1.2, 2.3])
    with c_prod:
        prod_name_default = current_order.get("product_name", "") if is_editing else ""
        f_product_name = st.text_input("نام محصول / مدل", value=prod_name_default, placeholder="مثلاً: باکس گل رز")
    with c_city:
        city_default = current_order.get("destination_city", "") if is_editing else ""
        f_destination_city = st.text_input("شهر مقصد", value=city_default, placeholder="مثلاً: تهران...")
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
        f_init_raw = st.text_input("واریزی اول / پیش‌پرداخت (تومان)", value=init_val_str)
        parsed_init = parse_int_price(f_init_raw)
    with cp2:
        rem_val_num = int(current_order["remaining_payment"]) if is_editing else 0
        rem_val_str = f"{rem_val_num:,}" if rem_val_num > 0 else ""
        f_rem_raw = st.text_input("مانده تسویه (تومان)", value=rem_val_str)
        parsed_rem = parse_int_price(f_rem_raw)
    with cp3:
        track_val = current_order.get("tracking_code", "") if is_editing else ""
        if track_val == "ثبت نشده":
            track_val = ""
        f_track_code = st.text_input("کد رهگیری پستی (اختیاری)", value=track_val)

    desc_val = current_order.get("product_desc", "") if is_editing else ""
    f_product_desc = st.text_area("شرح محصول و جزئیات ساخت", value=desc_val)
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

----------------- تب‌های برنامه (چهار تب کامل) -----------------

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
            st.checkbox("📷 ارسال عکس برای تسویه", value=_is_truthy(order.get("chk_photo", False)), key=k_p, on_change=lambda oid=order['id'], k=k_p: update_order_step(oid, "chk_photo", st.session_state[k]))
        with s2:
            st.checkbox("💳 تسویه", value=_is_truthy(order.get("chk_settle", False)), key=k_s, on_change=lambda oid=order['id'], k=k_s: update_order_step(oid, "chk_settle", st.session_state[k]))
        with s3:
            st.checkbox("🎁 آماده‌سازی بسته", value=_is_truthy(order.get("chk_pack", False)), key=k_pk, on_change=lambda oid=order['id'], k=k_pk: update_order_step(oid, "chk_pack", st.session_state[k]))
        with s4:
            st.checkbox("🚚 تحویل به پست", value=_is_truthy(order.get("chk_post", False)), key=k_pt, on_change=lambda oid=order['id'], k=k_pt: update_order_step(oid, "chk_post", st.session_state[k]))
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


--- تب ۱: کارت‌های مشتریان ---

with tab_cards:
col_t2, col_t1 = st.columns([1, 3])
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

    past_orders = [o for o in sorted_orders if str(o.get("delivery_date", "")) < today_str or is_order_fully_checked(o)]
    active_orders = [o for o in sorted_orders if str(o.get("delivery_date", "")) >= today_str and not is_order_fully_checked(o)]

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
        st.markdown(f"#### 📅 سفارش‌های تاریخ {d}{today_tag} — {len(orders_in_date)} سفارش")
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


--- تب ۲: تقویم شمسی ---

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
    d = str(o.get("delivery_date", ""))
    if d not in orders_map:
        orders_map[d] = []
    orders_map[d].append(o)

today_str = today_jalali.strftime("%Y/%m/%d")

if cal_view_mode == "نمای روزانه موبایلی (لیست سفارش‌ها)":
    st.info("💡 این نما برای مرور آسان روی گوشی طراحی شده است.")
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
                item_rem = get_effective_remaining(item)
                item_cid = f" ({item.get('customer_id')})" if item.get("customer_id") else ""
                is_item_archived = (str(item.get("delivery_date", "")) < today_str) or is_order_fully_checked(item)
                strike_style = "text-decoration: line-through; opacity: 0.65;" if is_item_archived else ""
                
                st.markdown(f"""
                <div style='background:#f8fafc; border-right:4px solid #3182ce; padding:8px 12px; border-radius:6px; margin-bottom:6px; font-size:0.85rem; {strike_style}'>
                    📦 <b>{item.get('customer_name')}{item_cid}</b> | مقصد: {item.get('destination_city')} | مانده: {item_rem:,.0f} تومان
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
                        item_rem = get_effective_remaining(item)
                        badge_class = "badge-paid" if item_rem == 0 else "badge-debt"
                        p_title = item.get('product_name') or item.get('product_desc') or ''
                        item_cid = f" ({item.get('customer_id')})" if item.get("customer_id") else ""
                        is_item_archived = (str(item.get("delivery_date", "")) < today_str) or is_order_fully_checked(item)
                        strike_style = "text-decoration: line-through; opacity: 0.65;" if is_item_archived else ""

                        orders_html += f"<div class='order-badge {badge_class}' style='{strike_style}' title='{p_title}'>📦 {item['customer_name']}{item_cid} ({item['destination_city']})</div>"
                    
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


--- تب ۳: صدور فاکتور و محاسبه قیمت ---

with tab_invoice:
st.subheader("🧾 صدور فاکتور مشتریان (متصل به شیت آنالیز جامع)")

catalog = load_pricing_catalog()
saved_templates = load_templates()

col_reload, _ = st.columns([1.5, 4.5])
with col_reload:
    if st.button("🔄 بروزرسانی قیمت‌ها و الگوها", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with st.expander("💐 انتخاب دسته‌گل‌های ذخیره‌شده (الگوهای پیش‌فرض)", expanded=bool(saved_templates)):
    if saved_templates:
        tpl_col1, tpl_col2, tpl_col3 = st.columns([3, 1.2, 0.8])
        with tpl_col1:
            selected_tpl = st.selectbox("انتخاب دسته‌گل از پیش ساخته شده:", options=list(saved_templates.keys()), key="select_saved_tpl")
        
        sel_tpl_obj = saved_templates[selected_tpl]
        sel_tpl_items = sel_tpl_obj["items"] if isinstance(sel_tpl_obj, dict) else sel_tpl_obj
        sel_tpl_img = sel_tpl_obj.get("image", "") if isinstance(sel_tpl_obj, dict) else ""

        with tpl_col2:
            st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
            if st.button("📥 بارگذاری در فاکتور", use_container_width=True, type="primary"):
                st.session_state.invoice_cart = copy.deepcopy(sel_tpl_items)
                st.session_state.invoice_template_image = sel_tpl_img
                st.success(f"اقلام دسته‌گل «{selected_tpl}» به فاکتور منتقل شد.")
                st.rerun()
        with tpl_col3:
            st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
            if st.button("🗑️ حذف الگو", use_container_width=True):
                if delete_template_item(selected_tpl):
                    st.warning(f"الگوی «{selected_tpl}» حذف شد.")
                    st.rerun()

        st.markdown("<hr style='margin:12px 0;'>", unsafe_allow_html=True)
        max_tpl_price = max([sum(int(i.get("total_price", 0)) for i in (t_data["items"] if isinstance(t_data, dict) else t_data)) for t_data in saved_templates.values()] + [10000000])
        price_filter_range = st.slider("💵 فیلتر بازه قیمت دسته‌گل‌های آماده (تومان):", min_value=0, max_value=int(max_tpl_price), value=(0, int(max_tpl_price)), step=50000, key="tpl_price_filter")
        
        st.markdown("<div style='font-size:0.9rem; font-weight:bold; color:#4a5568; margin-bottom:10px; margin-top:10px;'>🖼️ کاتالوگ تصویری دسته‌گل‌های آماده:</div>", unsafe_allow_html=True)
        
        filtered_tpl_entries = []
        for t_name, t_data in saved_templates.items():
            t_items = t_data["items"] if isinstance(t_data, dict) else t_data
            t_sum = sum(int(i.get("total_price", 0)) for i in t_items)
            if price_filter_range[0] <= t_sum <= price_filter_range[1]:
                filtered_tpl_entries.append((t_name, t_data))

        if filtered_tpl_entries:
            for row_start in range(0, len(filtered_tpl_entries), 4):
                g_cols = st.columns(4)
                for c_idx, (t_name, t_data) in enumerate(filtered_tpl_entries[row_start:row_start + 4]):
                    t_items = t_data["items"] if isinstance(t_data, dict) else t_data
                    t_img = t_data.get("image", "") if isinstance(t_data, dict) else ""
                    t_sum = sum(int(i.get("total_price", 0)) for i in t_items)
                    items_preview = "، ".join([f"{i.get('qty', 1)}×{i.get('name', '')}" for i in t_items[:3]])
                    if len(t_items) > 3:
                        items_preview += " و..."

                    with g_cols[c_idx]:
                        if t_img and t_img.lower() != "nan":
                            img_tag = f"<img src='data:image/jpeg;base64,{t_img}' style='width:100%; height:140px; object-fit:contain; border-radius:8px; border:1px solid #cbd5e1; margin-bottom:8px; background:#ffffff;'/>"
                        else:
                            img_tag = "<div style='width:100%; height:140px; display:flex; align-items:center; justify-content:center; background:#f1f5f9; border-radius:8px; border:1px dashed #cbd5e1; margin-bottom:8px; color:#94a3b8; font-size:2.2rem;'>💐</div>"
                        
                        st.markdown(
                            f"<div style='border:1px solid #e2e8f0; border-radius:10px; padding:10px; background:#ffffff; text-align:center; margin-bottom:6px;'>"
                            f"{img_tag}"
                            f"<div style='font-weight:bold; font-size:0.92rem; color:#2d3748; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>{t_name}</div>"
                            f"<div style='font-size:0.75rem; color:#718096; height:34px; overflow:hidden; margin-top:4px;'>{items_preview}</div>"
                            f"<div style='font-size:0.82rem; color:#3182ce; font-weight:bold; margin-top:4px;'>{t_sum:,.0f} تومان</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                        if st.button(f"✅ انتخاب «{t_name}»", key=f"visual_sel_{row_start}_{c_idx}", use_container_width=True):
                            st.session_state.invoice_cart = copy.deepcopy(t_items)
                            st.session_state.invoice_template_image = t_img
                            st.success(f"دسته‌گل «{t_name}» بارگذاری شد.")
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
        sel_cat = st.selectbox("دسته‌بندی محصول", categories, key="inv_cat")
    
    filtered_catalog = [item for item in catalog if sel_cat == "همه دسته‌ها" or item["category"] == sel_cat]
    product_names = [item["name"] for item in filtered_catalog]

    with ic2:
        sel_prod_name = st.selectbox("انتخاب محصول / مدل گل", product_names, key="inv_prod")
    
    selected_prod = next((item for item in filtered_catalog if item["name"] == sel_prod_name), None)

    sales_models = [
        "تک شاخه / کمتر از ۶ شاخه",
        "بیشتر از ۶ شاخه",
        "فروش عمده (بالای ۱۲ شاخه)",
        "قیمت دستی / توافقی"
    ]
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
            manual_price_str = st.text_input("قیمت واحد (تومان)", value=f"{default_unit_price:,}" if default_unit_price > 0 else "", key="inv_manual_p")
            final_unit_price = parse_int_price(manual_price_str)
        else:
            final_unit_price = default_unit_price
            st.markdown(f"<div style='background:#f0fff4; border:1px solid #c6f6d5; padding:10px 14px; border-radius:8px; margin-top:24px;'>💵 <b>قیمت واحد مصوب:</b> {final_unit_price:,.0f} تومان</div>", unsafe_allow_html=True)

    with ic_p2:
        line_total = final_unit_price * sel_qty
        if selected_prod:
            st.markdown(f"<div style='background:#ebf8ff; border:1px solid #bee3f8; padding:10px 14px; border-radius:8px; margin-top:24px;'>🧮 <b>جمع این ردیف:</b> {line_total:,.0f} تومان</div>", unsafe_allow_html=True)

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
            else:
                st.error("لطفاً قیمت واحد معتبر وارد کنید.")

    st.markdown("---")

    if st.session_state.invoice_cart:
        hdr_col1, hdr_col2 = st.columns([4, 1.2])
        with hdr_col1:
            st.markdown("#### 🛒 لیست اقلام فاکتور جاری")
        with hdr_col2:
            if st.button("🔄 ریست سبد", key="reset_cart_top", use_container_width=True):
                st.session_state.invoice_cart = []
                st.session_state.invoice_template_image = ""
                st.rerun()

        for idx, item in enumerate(st.session_state.invoice_cart):
            r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns([2.4, 1.5, 1.1, 1.8, 0.6])
            with r_col1:
                st.markdown(f"<div style='padding-top:8px;'><b>{idx + 1}. {item['name']}</b></div>", unsafe_allow_html=True)
            with r_col2:
                st.markdown(f"<div style='padding-top:8px; font-size:0.85rem;'>{item.get('sales_model', '')}</div>", unsafe_allow_html=True)
            with r_col3:
                new_qty = st.number_input("تعداد", min_value=1, value=int(item["qty"]), step=1, key=f"cart_qty_{idx}_{item['name']}", label_visibility="collapsed")
                if new_qty != item["qty"]:
                    st.session_state.invoice_cart[idx]["qty"] = int(new_qty)
                    st.session_state.invoice_cart[idx]["total_price"] = int(new_qty) * int(item["unit_price"])
                    st.session_state.invoice_cart[idx]["total_cost"] = int(new_qty) * int(item.get("unit_cost", 0))
                    st.rerun()
            with r_col4:
                st.markdown(f"<div style='padding-top:8px;'>کل: <b>{item['total_price']:,.0f} تومان</b></div>", unsafe_allow_html=True)
            with r_col5:
                if st.button("🗑️", key=f"del_inv_item_{idx}"):
                    st.session_state.invoice_cart.pop(idx)
                    st.rerun()

        with st.expander("💾 ذخیره این دسته‌گل در حافظه الگوها"):
            save_c1, save_c2, save_c3 = st.columns([2.2, 2, 1])
            with save_c1:
                new_tpl_name = st.text_input("نام دسته‌گل / مدل:", placeholder="مثلاً: دسته گل رز و نرگس")
            with save_c2:
                new_tpl_img_file = st.file_uploader("🖼️ عکس (اختیاری)", type=["png", "jpg", "jpeg", "webp"], key="tpl_img_uploader")
            with save_c3:
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                if st.button("💾 ذخیره الگو", use_container_width=True):
                    if new_tpl_name.strip():
                        tpl_img_b64 = ""
                        if new_tpl_img_file is not None:
                            tpl_img_b64 = compress_image_to_base64(new_tpl_img_file)
                        elif st.session_state.get("invoice_template_image"):
                            tpl_img_b64 = st.session_state.invoice_template_image
                        if save_template_item(new_tpl_name.strip(), st.session_state.invoice_cart, tpl_img_b64):
                            st.success("الگو با موفقیت ذخیره شد!")
                            st.rerun()
                    else:
                        st.warning("نام الگو را وارد کنید.")

        st.markdown("---")
        global_pricing_mode = st.radio("سطح قیمت:", ["حالت پیش‌فرض / انتخاب‌شده در ردیف‌ها", "تک شاخه / کمتر از ۶ شاخه", "بیشتر از ۶ شاخه", "فروش عمده (بالای ۱۲ شاخه)"], horizontal=True, label_visibility="collapsed")

        calculated_items = []
        for item in st.session_state.invoice_cart:
            cat_prod = next((p for p in catalog if p["name"] == item["name"]), None)
            p_single = item.get("price_single") or (cat_prod.get("price_single") if cat_prod else item["unit_price"])
            p_mid = item.get("price_mid") or (cat_prod.get("price_mid") if cat_prod else item["unit_price"])
            p_wholesale = item.get("price_wholesale") or (cat_prod.get("price_wholesale") if cat_prod else item["unit_price"])

            effective_unit_p = item["unit_price"]
            effective_model_label = item.get("sales_model", "پیش‌فرض")

            if global_pricing_mode == "تک شاخه / کمتر از ۶ شاخه":
                effective_unit_p = p_single
            elif global_pricing_mode == "بیشتر از ۶ شاخه":
                effective_unit_p = p_mid
            elif global_pricing_mode == "فروش عمده (بالای ۱۲ شاخه)":
                effective_unit_p = p_wholesale

            effective_total_p = effective_unit_p * item["qty"]
            unit_c = item.get("unit_cost", 0)
            if not unit_c and cat_prod:
                unit_c = cat_prod.get("cost", 0)

            calculated_items.append({
                "name": item["name"],
                "qty": item["qty"],
                "sales_model": effective_model_label,
                "unit_price": effective_unit_p,
                "total_price": effective_total_p,
                "unit_cost": unit_c,
                "total_cost": unit_c * item["qty"]
            })

        c_adj1, c_adj2, c_adj3, c_adj4 = st.columns([1.4, 1.2, 1.4, 1.2])
        with c_adj1:
            inv_shipping_raw = st.text_input("📦 هزینه ارسال (تومان)", value="0", key="inv_ship")
            inv_shipping = parse_int_price(inv_shipping_raw)
        with c_adj2:
            inv_disc_pct = st.number_input("📊 تخفیف درصدی (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
        with c_adj3:
            inv_discount_raw = st.text_input("🎁 تخفیف ثابت (تومان)", value="0", key="inv_disc")
            inv_discount_fixed = parse_int_price(inv_discount_raw)
        with c_adj4:
            st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
            round_prices = st.checkbox("✨ رند به هزار", value=True)

        items_subtotal = sum(i["total_price"] for i in calculated_items)
        items_total_cost = sum(i["total_cost"] for i in calculated_items)
        if round_prices:
            items_subtotal = int(round(items_subtotal, -3))

        inv_discount_pct_amount = int(round(items_subtotal * (inv_disc_pct / 100.0)))
        if round_prices and inv_discount_pct_amount > 0:
            inv_discount_pct_amount = int(round(inv_discount_pct_amount, -3))

        inv_discount_total = inv_discount_pct_amount + inv_discount_fixed
        grand_total = max(0, items_subtotal + inv_shipping - inv_discount_total)
        estimated_profit = grand_total - items_total_cost - inv_shipping

        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>جمع اقلام</div><div class='metric-value'>{items_subtotal:,.0f} تومان</div></div>", unsafe_allow_html=True)
        with mc2:
            st.markdown(f"<div class='metric-card' style='border-color:#3182ce; background:#ebf8ff;'><div class='metric-label' style='color:#2b6cb0;'>مبلغ قابل پرداخت</div><div class='metric-value' style='color:#2b6cb0;'>{grand_total:,.0f} تومان</div></div>", unsafe_allow_html=True)
        with mc3:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>بهای تمام‌شده</div><div class='metric-value'>{items_total_cost:,.0f} تومان</div></div>", unsafe_allow_html=True)
        with mc4:
            st.markdown(f"<div class='metric-card' style='border-color:#38a169; background:#f0fff4;'><div class='metric-label' style='color:#2f855a;'>سود خالص</div><div class='metric-value' style='color:#2f855a;'>{estimated_profit:,.0f} تومان</div></div>", unsafe_allow_html=True)

        st.markdown("#### 📤 ثبت فاکتور و کسر خودکار انبار")
        col_out1, col_out2 = st.columns([2.5, 2.5])

        with col_out1:
            inv_cust_name_default = st.session_state.get("inv_reg_cname", "")
            inv_cust_name = st.text_input("نام مشتری", value=inv_cust_name_default, key="inv_c_name")
            inv_deposit_raw = st.text_input("مبلغ بیعانه دریافتی (تومان)", value="0", key="inv_dep")
            inv_deposit = parse_int_price(inv_deposit_raw)
            inv_rem = max(0, grand_total - inv_deposit)

            lines_text = []
            for idx, item in enumerate(calculated_items):
                u_p = int(round(item['unit_price'], -3)) if round_prices else item['unit_price']
                t_p = int(round(item['total_price'], -3)) if round_prices else item['total_price']
                lines_text.append(f"🔸 {idx+1}. {item['name']} ({item['qty']} عدد) = {t_p:,.0f} تومان")

            invoice_text = f"🧾 پیش‌فاکتور سفارش\n👤 مشتری: {inv_cust_name}\n📅 تاریخ: {today_jalali.strftime('%Y/%m/%d')}\n" + "────────────────────\n" + "\n".join(lines_text) + "\n" + "────────────────────\n" + f"✅ مبلغ کل: {grand_total:,.0f} تومان\n"
            st.text_area("📋 متن فاکتور:", value=invoice_text, height=220)

        with col_out2:
            st.markdown("##### 🚀 تبدیل به سفارش و کسر انبار")
            reg_cust_name = st.text_input("نام و نام خانوادگی مشتری", value=inv_cust_name, key="inv_reg_cname")
            reg_phone = st.text_input("شماره تماس", key="inv_reg_phone")
            reg_em_phone = st.text_input("تماس اضطراری", key="inv_reg_em")
            
            rc_id_col, rc_post_col = st.columns(2)
            with rc_id_col:
                reg_username = st.text_input("آیدی", key="inv_reg_uname")
            with rc_post_col:
                reg_postal = st.text_input("کد پستی", key="inv_reg_postal")
            
            reg_address = st.text_input("آدرس", key="inv_reg_addr")
            reg_city = st.text_input("شهر مقصد", key="inv_reg_city")
            
            st.markdown("<p style='font-weight:600; margin-bottom:5px; font-size:0.9rem;'>📅 تاریخ تحویل</p>", unsafe_allow_html=True)
            rc_d, rc_m, rc_y = st.columns([1, 1.5, 1.2])
            with rc_d:
                reg_day = st.selectbox("روز", list(range(1, 32)), index=min(today_jalali.day - 1, 30), key="inv_d")
            with rc_m:
                reg_m_name = st.selectbox("ماه", month_names, index=today_jalali.month - 1, key="inv_m")
                reg_month = month_names.index(reg_m_name) + 1
            with rc_y:
                reg_year = st.selectbox("سال", [today_jalali.year - 1, today_jalali.year, today_jalali.year + 1], index=1, key="inv_y")

            if st.button("✅ ثبت فاکتور، ایجاد سفارش و کسر انبار", use_container_width=True, type="primary"):
                try:
                    deliv_j = jdatetime.date(reg_year, reg_month, reg_day).strftime("%Y/%m/%d")
                except ValueError:
                    deliv_j = jdatetime.date(reg_year, reg_month, 29).strftime("%Y/%m/%d")

                summary_title = " + ".join([f"{i['qty']}×{i['name']}" for i in calculated_items[:2]])
                detailed_desc = " | ".join([f"{i['name']} ({i['qty']} عدد)" for i in calculated_items])

                new_id = get_next_id(orders_list)
                new_inv_no = get_next_invoice_no(orders_list)
                now_j = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")

                new_order = {
                    "id": new_id,
                    "invoice_no": new_inv_no,
                    "customer_id": reg_username,
                    "customer_name": reg_cust_name if reg_cust_name else "مشتری",
                    "phone": reg_phone,
                    "emergency_phone": reg_em_phone,
                    "address": reg_address,
                    "postal_code": reg_postal,
                    "destination_city": reg_city if reg_city else "-",
                    "product_name": summary_title,
                    "delivery_date": deliv_j,
                    "order_created_at": now_j,
                    "initial_payment": inv_deposit,
                    "remaining_payment": inv_rem,
                    "total_price": grand_total,
                    "tracking_code": "ثبت نشده",
                    "product_desc": detailed_desc,
                    "order_image": st.session_state.get("invoice_template_image", ""),
                    "chk_deposit": bool(inv_deposit > 0),
                    "chk_photo": False,
                    "chk_settle": bool(inv_rem == 0 and grand_total > 0),
                    "chk_pack": False,
                    "chk_post": False
                }
                orders_list.append(new_order)
                save_orders(orders_list)
                
                # 🔥 کسر خودکار موجودی از انبار گوگل شیت
                update_inventory_stock(calculated_items)

                st.session_state.invoice_cart = []
                st.session_state.invoice_template_image = ""
                st.success("فاکتور ثبت شد و موجودی متریال‌ها از انبار کسر گردید!")
                st.rerun()


--- تب ۴: مدیریت انبار و پایش موجودی ---

with tab_stock:
st.subheader("📦 مدیریت انبار متریال و هشدار اتمام موجودی")

inventory_data = load_inventory()

if inventory_data:
    low_stock_items = [i for i in inventory_data if i["current_stock"] <= i["min_threshold"]]
    
    if low_stock_items:
        st.warning(f"🚨 هشدار: {len(low_stock_items)} قلم از متریال‌های انبار به اتمام نزدیک شده یا تمام شده‌اند!")
        for alert_item in low_stock_items:
            st.markdown(f"- ⚠️ **{alert_item['material_name']}**: موجودی فعلی `{alert_item['current_stock']} {alert_item['unit']}`")
    
    st.markdown("---")
    st.markdown("#### 📊 لیست کامل موجودی انبار")
    df_inv = pd.DataFrame(inventory_data)
    st.dataframe(df_inv, use_container_width=True)
    
    with st.expander("➕ افزودن متریال جدید یا ویرایش موجودی انبار"):
        with st.form("add_stock_form"):
            sc1, sc2, sc3, sc4 = st.columns(4)
            with sc1:
                new_mat_name = st.text_input("نام متریال / اقلام")
            with sc2:
                new_mat_unit = st.text_input("واحد (شاخه، متر، عدد)", value="عدد")
            with sc3:
                new_mat_stock = st.number_input("موجودی اولیه", min_value=0.0, value=10.0, step=1.0)
            with sc4:
                new_mat_min = st.number_input("حداقل هشدار", min_value=0.0, value=3.0, step=1.0)
            
            submitted_stock = st.form_submit_button("💾 ذخیره در انبار گوگل شیت", type="primary")
            if submitted_stock and new_mat_name.strip():
                ws = get_inventory_worksheet()
                if ws:
                    ws.append_row([new_mat_name.strip(), new_mat_unit, new_mat_stock, new_mat_min])
                    st.cache_data.clear()
                    st.success(f"متریال «{new_mat_name}» به انبار اضافه شد!")
                    st.rerun()
else:
    st.info("هنوز اطلاعاتی در شیت انبار ثبت نشده است. ساختار پیش‌فرض را ایجاد کنید:")
    if st.button("➕ ایجاد خودکار ساختار انبار در گوگل شیت"):
        ws = get_inventory_worksheet()
        if ws:
            ws.append_row(["گل رز هلندی", "شاخه", 50.0, 10.0])
            ws.append_row(["روبان ساتن", "متر", 30.0, 5.0])
            st.cache_data.clear()
            st.success("ساختار انبار ایجاد شد!")
            st.rerun()
