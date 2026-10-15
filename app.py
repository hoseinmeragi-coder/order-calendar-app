import json

def get_templates_worksheet():
    """دریافت یا ساخت شیت مربوط به الگوهای ذخیره‌شده دسته‌گل"""
    try:
        gc = get_gspread_client()
        target = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        sh = gc.open_by_url(target) if target.startswith("http") else gc.open_by_key(target)
        try:
            return sh.worksheet("templates")
        except Exception:
            ws = sh.add_worksheet(title="templates", rows="100", cols="5")
            ws.append_row(["template_name", "items_json"])
            return ws
    except Exception:
        return None

@st.cache_data(ttl=60)
def load_templates():
    """خواندن الگوهای دسته‌گل از شیت templates"""
    try:
        ws = get_templates_worksheet()
        if ws is None:
            return {}
        records = ws.get_all_records()
        templates = {}
        for r in records:
            name = str(r.get("template_name", "")).strip()
            raw_items = r.get("items_json", "")
            if name and raw_items:
                try:
                    templates[name] = json.loads(raw_items)
                except Exception:
                    continue
        return templates
    except Exception:
        return {}

def save_template_item(template_name, items):
    """ذخیره یا بروزرسانی یک الگوی دسته‌گل در شیت templates"""
    try:
        ws = get_templates_worksheet()
        if ws is None:
            return False
        vals = ws.get_all_values()
        row_to_update = None
        for idx, row in enumerate(vals):
            if row and row[0].strip() == template_name.strip():
                row_to_update = idx + 1
                break
        
        json_str = json.dumps(items, ensure_ascii=False)
        if row_to_update:
            ws.update(range_name=f"B{row_to_update}", values=[[json_str]])
        else:
            ws.append_row([template_name.strip(), json_str])
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"خطا در ذخیره الگوی دسته‌گل: {e}")
        return False

def delete_template_item(template_name):
    """حذف الگوی دسته‌گل از شیت"""
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
