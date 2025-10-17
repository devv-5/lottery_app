import frappe
from frappe import _
from datetime import datetime, time, timedelta
from frappe.query_builder import DocType
from frappe.utils import now_datetime, nowdate, get_datetime, time_diff_in_seconds, to_timedelta, cint
import random

# =====================================================
# 🔹 Core Public API
# =====================================================
@frappe.whitelist(allow_guest=True)
def get_lottery_entries(date=None):
    """Main endpoint: returns entries for given date and last lucky number."""
    validated_date = validate_date(date)
    now = now_datetime()

    entries = fetch_lottery_entries_for_date(validated_date, now)
    last_entry = fetch_last_lucky_number(now)
    jodi_entries = get_36_jodi() or []

    return {"entries": entries, "last_entry": last_entry, "jodi_entries": jodi_entries}

# =====================================================
# 🔹 Validation
# =====================================================
def validate_date(date_str):
    """Ensure date exists and has valid YYYY-MM-DD format."""
    if not date_str:
        return nowdate()
    try:
        # If it's already a date object, return it
        if isinstance(date_str, datetime):
            return date_str.date()
        if hasattr(date_str, 'date'):
            return date_str.date()
        # Parse string date
        return datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except ValueError:
        frappe.throw(_("Invalid date format. Please use YYYY-MM-DD"))

# =====================================================
# 🔹 Fetch Entries for Selected Date
# =====================================================
def fetch_lottery_entries_for_date(date, now):
    """Fetch all valid entries for a given date up to current time with previous day data."""
    LotteryEntry = DocType("Lottery Entry")
    entries = []

    try:
        # Ensure date is a date object
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d").date()
        
        print(f"[DEBUG] Fetching entries for date: {date} (type: {type(date)})")

        # Get current date entries
        current_records = (
            frappe.qb.from_(LotteryEntry)
            .select(LotteryEntry.time_slot, LotteryEntry.lucky_number, LotteryEntry.date)
            .where((LotteryEntry.date == date) & (LotteryEntry.docstatus == 1))
            .orderby(LotteryEntry.time_slot)
            .run(as_dict=True)
        )

        print(f"[DEBUG] Current records found: {len(current_records)}")

        # Get previous day entries for comparison
        previous_date = date - timedelta(days=1)
        print(f"[DEBUG] Previous date: {previous_date}")

        previous_records = (
            frappe.qb.from_(LotteryEntry)
            .select(LotteryEntry.time_slot, LotteryEntry.lucky_number, LotteryEntry.date)
            .where((LotteryEntry.date == previous_date) & (LotteryEntry.docstatus == 1))
            .orderby(LotteryEntry.time_slot)
            .run(as_dict=True)
        )

        print(f"[DEBUG] Previous records found: {len(previous_records)}")

        # Create a dictionary of previous day entries for easy lookup
        previous_dict = {}
        for rec in previous_records:
            time_str = normalize_time_format(rec.time_slot)
            if time_str:
                previous_dict[time_str] = rec.lucky_number
                print(f"[DEBUG] Added previous entry: {time_str} -> {rec.lucky_number}")

        print(f"[DEBUG] Previous dict: {previous_dict}")

        for rec in current_records:
            parsed = parse_lottery_time_entry(rec, now, previous_dict)
            if parsed:
                entries.append(parsed)
                print(f"[DEBUG] Added entry: {parsed}")

        print(f"[DEBUG] Final entries with old numbers: {entries}")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "fetch_lottery_entries_for_date")
        print(f"[ERROR] fetch_lottery_entries_for_date: {str(e)}")
        print(f"[ERROR] Date that caused issue: {date} (type: {type(date)})")

    return entries

# =====================================================
# 🔹 Parse and Validate Time Slot Entry
# =====================================================
def parse_lottery_time_entry(entry, now, previous_dict=None):
    """Parse and validate time entry; return dict if valid and past."""
    raw_time = entry.time_slot
    time_str = normalize_time_format(raw_time)
    if not time_str:
        return None

    try:
        entry_datetime = get_datetime(f"{entry.date} {time_str}")  # timezone-aware
        if entry_datetime <= now:
            # Get previous day's number for the same time slot
            old_number = previous_dict.get(time_str, "--") if previous_dict else "--"
            
            return {
                "time_slot": time_str, 
                "lucky_number": entry.lucky_number,
                "old_number": old_number
            }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "parse_lottery_time_entry")
        print(f"[ERROR] parse_lottery_time_entry: {str(e)}")

    return None

# =====================================================
# 🔹 Fetch Most Recent Lucky Number
# =====================================================
def fetch_last_lucky_number(now, lookback_limit=50):
    """
    Get the most recent valid lucky number whose (date + time_slot) <= now.
    """
    LotteryEntry = DocType("Lottery Entry")
    try:
        results = (
            frappe.qb.from_(LotteryEntry)
            .select(LotteryEntry.date, LotteryEntry.time_slot, LotteryEntry.lucky_number)
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
                return {
                    "time_slot": time_str,
                    "lucky_number": entry.lucky_number,
                    "lottery_date": entry.date.strftime("%Y-%m-%d"),
                }

        return None

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "fetch_last_lucky_number")
        return None

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
        return jodi_list or []
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_36_jodi")
        return []

# =====================================================
# 🔹 Helpers
# =====================================================
def normalize_time_format(raw_time):
    """Convert timedelta or string time into HH:MM:SS."""
    try:
        if isinstance(raw_time, timedelta):
            total = int(raw_time.total_seconds())
            hh, mm, ss = total // 3600, (total % 3600) // 60, total % 60
            return f"{hh:02d}:{mm:02d}:{ss:02d}"
        if isinstance(raw_time, str) and ":" in raw_time:
            # Ensure consistent time format (HH:MM:SS)
            parts = raw_time.split(':')
            if len(parts) == 2:
                return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:00"
            elif len(parts) == 3:
                return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
            return raw_time
        return "00:00:00"
    except Exception as e:
        print(f"[ERROR] normalize_time_format: {str(e)}")
        return None

def is_past_entry(entry_date, time_str, now):
    """Return True if the entry datetime is in the past."""
    try:
        entry_datetime = get_datetime(f"{entry.date} {time_str}")
        return entry_datetime <= now
    except Exception as e:
        return False

def log(msg):
    """Consistent logging wrapper."""
    print(f"[Lottery API] {msg}")

# =====================================================
# 🔹 Auto Jodi Scheduler
# =====================================================
@frappe.whitelist(allow_guest=True)
def auto_jodi_scheduler():
    """
    Scheduled job that auto-generates 'Jodi 36' entries
    based on the 'Jodi 36' single doctype settings.
    """
    settings = frappe.get_single("Jodi 36")

    if not (settings.active and settings.auto_generate_jodi):
        frappe.logger().info("[Jodi Scheduler] Skipped: inactive or auto-generation disabled.")
        return

    try:
        auto_create_jodi(settings)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "auto_jodi_scheduler failed")
        frappe.logger().error(f"[Jodi Scheduler] Failed: {e}")

def auto_create_jodi(settings):
    """
    Create Jodi entries according to the frequency duration.
    """
    number_of_jodi = cint(settings.number_of_jodi or 36)
    frequency_duration = get_frequency_seconds(settings.frequency)
    now = now_datetime()
    last_generated = settings.last_generated_on

    if not should_generate_new_batch_by_duration(frequency_duration, last_generated, now):
        frappe.logger().info("[Jodi Scheduler] Skipping: within frequency interval.")
        return

    frappe.logger().info(f"[Jodi Scheduler] Generating {number_of_jodi} new Jodi entries.")

    # Generate unique 2-digit numbers (00–99)
    jodi_list = generate_unique_jodis(number_of_jodi)

    # Clear previous entries if needed
    if cint(settings.clear_previous) == 1:
        settings.set("entries", [])
        frappe.logger().info("[Jodi Scheduler] Cleared previous Jodi entries.")

    # Append new child rows correctly
    for num in jodi_list:
        settings.append("entries", {"number": num})

    # Update timestamp
    settings.last_generated_on = now
    settings.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.logger().info(f"[Jodi Scheduler] Successfully created {len(jodi_list)} new Jodi entries.")

# =====================================================
# 🔹 Scheduler Helper Functions
# =====================================================
def get_frequency_seconds(frequency_value):
    """
    Convert Duration field into seconds.
    Handles string, numeric, or timedelta values.
    """
    if not frequency_value:
        return 86400  # Default 1 day

    try:
        td = to_timedelta(frequency_value)
        return int(td.total_seconds())
    except Exception:
        return int(frequency_value) if str(frequency_value).isdigit() else 86400

def should_generate_new_batch_by_duration(frequency_seconds, last_generated, now):
    if not last_generated:
        return True

    last_generated_dt = get_datetime(last_generated)
    seconds_since_last = time_diff_in_seconds(now, last_generated_dt)
    return seconds_since_last >= frequency_seconds

def generate_unique_jodis(n):
    """
    Generate n unique 2-digit Jodi numbers (00–99)
    """
    n = min(n, 100)
    numbers = [f"{i:02d}" for i in range(100)]
    random.shuffle(numbers)
    return numbers[:n]