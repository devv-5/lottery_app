import frappe
from frappe import _
from datetime import datetime, timedelta
from frappe.query_builder import DocType
from frappe.utils import now_datetime, nowdate, get_datetime, time_diff_in_seconds, to_timedelta, cint
import random
import calendar

# =====================================================
# 🔹 FORMATTING HELPERS (Moved from Frontend)
# =====================================================
def format_number(num, empty_val="N/A"):
    """Pad numbers with a leading zero if single digit, handle empty states."""
    if num is None or str(num).strip() == "":
        return empty_val
    if str(num).strip() == "--":
        return "--"
    try:
        return f"{int(num):02d}"
    except (ValueError, TypeError):
        return str(num)

def format_time_12h(time_str):
    """Convert HH:MM:SS to 12-hour AM/PM format."""
    if not time_str:
        return "--:--:--"
    try:
        # Assuming normalize_time_format gives us HH:MM:SS
        time_obj = datetime.strptime(time_str, "%H:%M:%S")
        return time_obj.strftime("%I:%M %p").lstrip("0").replace(" 0", " ") 
    except Exception:
        return time_str

# =====================================================
# 🔹 Core Public API
# =====================================================
@frappe.whitelist(allow_guest=True)
def get_lottery_entries(date=None):
    validated_date = validate_date(date)
    now = now_datetime()

    entries = fetch_lottery_entries_for_date(validated_date, now)
    last_entry = fetch_last_lucky_number(now)
    jodi_entries = get_36_jodi() or []

    frappe.log_error("Fetched", {"entries": entries, "last_entry": last_entry, "jodi_entries": jodi_entries})
    return {"entries": entries, "last_entry": last_entry, "jodi_entries": jodi_entries}

# =====================================================
# 🔹 Validation
# =====================================================
def validate_date(date_str):
    if not date_str:
        return nowdate()
    try:
        if isinstance(date_str, datetime):
            return date_str.date()
        if hasattr(date_str, 'date'):
            return date_str.date()
        return datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except ValueError:
        frappe.throw(_("Invalid date format. Please use YYYY-MM-DD"))

# =====================================================
# 🔹 Fetch Entries for Selected Date
# =====================================================
def fetch_lottery_entries_for_date(date, now):
    Lottery = DocType("Lottery")
    LotteryEntry = DocType("Lottery Entry")
    entries = []

    try:
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d").date()
        
        # 1. Fetch Current Records (Joined with Parent to check auto_generate setting)
        current_records = (
            frappe.qb.from_(LotteryEntry)
            .inner_join(Lottery).on(LotteryEntry.parent == Lottery.name)
            .select(
                LotteryEntry.time_slot, 
                LotteryEntry.lucky_number, 
                LotteryEntry.date,
                LotteryEntry.auto_generated_number,
                Lottery.auto_generate_number.as_("parent_auto_gen")
            )
            .where((LotteryEntry.date == date) & (LotteryEntry.docstatus == 1))
            .orderby(LotteryEntry.time_slot)
            .run(as_dict=True)
        )

        # 2. Fetch Previous Records
        previous_date = date - timedelta(days=1)
        previous_records = (
            frappe.qb.from_(LotteryEntry)
            .inner_join(Lottery).on(LotteryEntry.parent == Lottery.name)
            .select(
                LotteryEntry.time_slot, 
                LotteryEntry.lucky_number,
                LotteryEntry.auto_generated_number,
                Lottery.auto_generate_number.as_("parent_auto_gen")
            )
            .where((LotteryEntry.date == previous_date) & (LotteryEntry.docstatus == 1))
            .run(as_dict=True)
        )

        previous_dict = {}
        for rec in previous_records:
            time_str = normalize_time_format(rec.time_slot)
            if time_str:
                # Resolve the previous number using the fallback logic
                lucky = rec.lucky_number
                if not lucky and rec.parent_auto_gen:
                    lucky = rec.auto_generated_number
                previous_dict[time_str] = lucky

        for rec in current_records:
            parsed = parse_lottery_time_entry(rec, now, previous_dict)
            if parsed:
                entries.append(parsed)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "fetch_lottery_entries_for_date")

    return entries

# =====================================================
# 🔹 Parse and Validate Time Slot Entry
# =====================================================
def parse_lottery_time_entry(entry, now, previous_dict=None):
    raw_time = entry.time_slot
    time_str = normalize_time_format(raw_time)
    if not time_str:
        return None

    try:
        entry_datetime = get_datetime(f"{entry.date} {time_str}")
        old_number_raw = previous_dict.get(time_str, "") if previous_dict else ""
        
        if entry_datetime <= now:
            # 🔥 FALLBACK LOGIC
            lucky_number_raw = entry.lucky_number
            if not lucky_number_raw and entry.parent_auto_gen:
                lucky_number_raw = entry.auto_generated_number
        else:
            lucky_number_raw = "--" 
            
        return {
            "time_slot": format_time_12h(time_str), 
            "lucky_number": format_number(lucky_number_raw, "N/A"),
            "old_number": format_number(old_number_raw, "N/A"),
            "is_future": entry_datetime > now  
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "parse_lottery_time_entry")

    return None

# =====================================================
# 🔹 Fetch Most Recent Lucky Number
# =====================================================
def fetch_last_lucky_number(now, lookback_limit=50):
    Lottery = DocType("Lottery")
    LotteryEntry = DocType("Lottery Entry")
    try:
        results = (
            frappe.qb.from_(LotteryEntry)
            .inner_join(Lottery).on(LotteryEntry.parent == Lottery.name)
            .select(
                LotteryEntry.date, 
                LotteryEntry.time_slot, 
                LotteryEntry.lucky_number,
                LotteryEntry.auto_generated_number,
                Lottery.auto_generate_number.as_("parent_auto_gen")
            )
            .where((LotteryEntry.date <= now.date()) & (LotteryEntry.docstatus == 1))
            .orderby(LotteryEntry.date, order=frappe.qb.desc)
            .orderby(LotteryEntry.time_slot, order=frappe.qb.desc)
            .limit(lookback_limit)
            .run(as_dict=True)
        )

        for entry in results:
            time_str = normalize_time_format(entry.time_slot)
            if not time_str:
                continue

            entry_dt = get_datetime(f"{entry.date} {time_str}")
            if entry_dt <= now:
                # Apply fallback logic
                lucky_number_raw = entry.lucky_number
                if not lucky_number_raw and entry.parent_auto_gen:
                    lucky_number_raw = entry.auto_generated_number
                
                # Ensure we actually have a number to show before returning
                if lucky_number_raw:
                    return {
                        "time_slot": format_time_12h(time_str),
                        "lucky_number": format_number(lucky_number_raw, "N/A"),
                        "lottery_date": entry.date.strftime("%Y-%m-%d"),
                    }

        return None

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "fetch_last_lucky_number")
        return None
        
# =====================================================
# 🔹 Monthly Lottery Data API
# =====================================================
@frappe.whitelist(allow_guest=True)
def get_monthly_lottery_data(year=None, month=None):
    try:
        now = now_datetime()
        if not year: year = now.year
        if not month: month = now.month
        
        year, month = int(year), int(month)
        days_in_month = calendar.monthrange(year, month)[1]
        
        Lottery = DocType("Lottery")
        LotteryEntry = DocType("Lottery Entry")
        
        # Define dates first so we can use them in the distinct slots query
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{days_in_month:02d}"
        
        # 1. FIX: Fetch distinct slots ONLY for submitted entries in the requested month
        distinct_slots = (
            frappe.qb.from_(LotteryEntry)
            .select(LotteryEntry.time_slot)
            .distinct()
            .where(
                (LotteryEntry.docstatus == 1) & 
                (LotteryEntry.date >= start_date) & 
                (LotteryEntry.date <= end_date)
            )
            .run(as_dict=True)
        )
        
        raw_time_slots = []
        for slot in distinct_slots:
            norm_time = normalize_time_format(slot.time_slot)
            if norm_time and norm_time not in raw_time_slots:
                raw_time_slots.append(norm_time)
                
        raw_time_slots.sort()
        formatted_time_slots = [format_time_12h(ts) for ts in raw_time_slots]
        
        # 2. Fetch the actual grid data
        monthly_entries = (
            frappe.qb.from_(LotteryEntry)
            .inner_join(Lottery).on(LotteryEntry.parent == Lottery.name)
            .select(
                LotteryEntry.date, 
                LotteryEntry.time_slot, 
                LotteryEntry.lucky_number,
                LotteryEntry.auto_generated_number,
                Lottery.auto_generate_number.as_("parent_auto_gen")
            )
            .where(
                (LotteryEntry.date >= start_date) & 
                (LotteryEntry.date <= end_date) & 
                (LotteryEntry.docstatus == 1) &
                (Lottery.docstatus == 1)
            )
            .orderby(LotteryEntry.date)
            .orderby(LotteryEntry.time_slot)
            .run(as_dict=True)
        )
        
        monthly_data = {}
        for entry in monthly_entries:
            date_str = entry.date.strftime("%d-%m-%Y")
            time_str = normalize_time_format(entry.time_slot)
            f_time_str = format_time_12h(time_str)
            entry_dt = get_datetime(f"{entry.date} {time_str}")
            
            if date_str not in monthly_data:
                monthly_data[date_str] = {}
                
            if entry_dt > now:
                monthly_data[date_str][f_time_str] = "--"
            else:
                # 🔥 FALLBACK LOGIC
                lucky_number_raw = entry.lucky_number
                if not lucky_number_raw and entry.parent_auto_gen:
                    lucky_number_raw = entry.auto_generated_number
                    
                monthly_data[date_str][f_time_str] = format_number(lucky_number_raw, "")
        
        grid_data = []
        for day in range(1, days_in_month + 1):
            date_str = f"{day:02d}-{month:02d}-{year}"
            row_data = {"date": date_str}
            for f_ts in formatted_time_slots:
                row_data[f_ts] = monthly_data.get(date_str, {}).get(f_ts, "")
            grid_data.append(row_data)
        
        frappe.log_error("Monthly Data Fetched", {"month": month, "year": year, "time_slots": formatted_time_slots, "sample_entry": grid_data[0] if grid_data else {}})
        return {
            "grid_data": grid_data,
            "time_slots": formatted_time_slots,
            "month": month,
            "year": year,
            "month_name": calendar.month_name[month]
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_monthly_lottery_data")
        return {"grid_data": [], "time_slots": [], "month": month, "year": year, "error": str(e)}

# =====================================================
# 🔹 Fetch 36 Jodi
# =====================================================
@frappe.whitelist(allow_guest=True)
def get_36_jodi():
    is_enabled = frappe.db.get_single_value("Jodi 36", "active")
    if not is_enabled:
        return []

    JodiEntry = DocType("Jodi Entry")

    try:
        jodi_list = (
            frappe.qb.from_(JodiEntry)
            .select(JodiEntry.number)
            .orderby(JodiEntry.creation, order=frappe.qb.desc)
            .run(as_dict=True)
        )
        # Format the numbers before sending to frontend
        for j in jodi_list:
            j["number"] = format_number(j.get("number"), "")
        return jodi_list
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_36_jodi")
        return []

# =====================================================
# 🔹 Helpers & Scheduler (Unchanged logic, just kept here)
# =====================================================
def normalize_time_format(raw_time):
    try:
        if isinstance(raw_time, timedelta):
            total = int(raw_time.total_seconds())
            hh, mm, ss = total // 3600, (total % 3600) // 60, total % 60
            return f"{hh:02d}:{mm:02d}:{ss:02d}"
        if isinstance(raw_time, str) and ":" in raw_time:
            parts = raw_time.split(':')
            if len(parts) == 2:
                return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:00"
            elif len(parts) == 3:
                return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
            return raw_time
        return "00:00:00"
    except Exception:
        return None

def is_past_entry(entry_date, time_str, now):
    try:
        entry_datetime = get_datetime(f"{entry_date} {time_str}")
        return entry_datetime <= now
    except Exception:
        return False

def log(msg):
    print(f"[Lottery API] {msg}")

@frappe.whitelist(allow_guest=True)
def auto_jodi_scheduler():
    settings = frappe.get_single("Jodi 36")
    if not (settings.active and settings.auto_generate_jodi):
        return
    try:
        auto_create_jodi(settings)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "auto_jodi_scheduler failed")

def auto_create_jodi(settings):
    number_of_jodi = cint(settings.number_of_jodi or 36)
    frequency_duration = get_frequency_seconds(settings.frequency)
    now = now_datetime()
    last_generated = settings.last_generated_on

    if not should_generate_new_batch_by_duration(frequency_duration, last_generated, now):
        return

    jodi_list = generate_unique_jodis(number_of_jodi)
    if cint(settings.clear_previous) == 1:
        settings.set("entries", [])
    for num in jodi_list:
        settings.append("entries", {"number": num})
    
    settings.last_generated_on = now
    settings.save(ignore_permissions=True)
    frappe.db.commit()

def get_frequency_seconds(frequency_value):
    if not frequency_value: return 86400 
    try:
        td = to_timedelta(frequency_value)
        return int(td.total_seconds())
    except Exception:
        return int(frequency_value) if str(frequency_value).isdigit() else 86400

def should_generate_new_batch_by_duration(frequency_seconds, last_generated, now):
    if not last_generated: return True
    last_generated_dt = get_datetime(last_generated)
    seconds_since_last = time_diff_in_seconds(now, last_generated_dt)
    return seconds_since_last >= frequency_seconds

def generate_unique_jodis(n):
    n = min(n, 100)
    numbers = [f"{i:02d}" for i in range(100)]
    random.shuffle(numbers)
    return numbers[:n]