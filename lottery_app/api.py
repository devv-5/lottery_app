import frappe
from frappe import _
from datetime import datetime, time, timedelta
from frappe.query_builder import DocType


# =====================================================
# 🔹 Core Public API
# =====================================================
@frappe.whitelist(allow_guest=True)
def get_lottery_entries(date=None):
    """Main endpoint: returns entries for given date and last lucky number."""
    log(f"Called get_lottery_entries with date: {date}")

    validated_date = validate_date(date)
    now = datetime.now()

    entries = fetch_lottery_entries_for_date(validated_date, now)
    last_entry = fetch_last_lucky_number(now)
    jodi_entries = get_36_jodi()

    log(f"Returning {len(entries)} entries and last_entry: {bool(last_entry)} and jodi_entries: {len(jodi_entries)}")
    return {"entries": entries, "last_entry": last_entry, "jodi_entries": jodi_entries}


# =====================================================
# 🔹 Validation
# =====================================================
def validate_date(date_str: str) -> datetime.date:
    """Ensure date exists and has valid YYYY-MM-DD format."""
    if not date_str:
        return frappe.utils.nowdate()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        frappe.throw(_("Invalid date format. Please use YYYY-MM-DD"))


# =====================================================
# 🔹 Fetch Entries for Selected Date
# =====================================================
def fetch_lottery_entries_for_date(date, now):
    """Fetch all valid entries for a given date up to current time."""
    LotteryEntry = DocType("Lottery Entry")
    entries = []

    try:
        records = (
            frappe.qb.from_(LotteryEntry)
            .select(LotteryEntry.time_slot, LotteryEntry.lucky_number, LotteryEntry.date)
            .where((LotteryEntry.date == date) & (LotteryEntry.docstatus == 1))
            .orderby(LotteryEntry.time_slot)
            .run(as_dict=True)
        )
        log(f"Found {len(records)} total entries for date: {date}")

        for rec in records:
            parsed = parse_lottery_time_entry(rec, now)
            if parsed:
                entries.append(parsed)

    except Exception as e:
        log(f"Error fetching entries for {date}: {e}")

    return entries


# =====================================================
# 🔹 Parse and Validate Time Slot Entry
# =====================================================
def parse_lottery_time_entry(entry, now):
    """Parse and validate time entry; return dict if valid and past."""
    raw_time = entry.time_slot
    time_str = normalize_time_format(raw_time)
    if not time_str:
        return None

    try:
        hh, mm, ss = map(int, time_str.split(":"))
        if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
            return None

        entry_datetime = datetime.combine(entry.date, time(hh, mm, ss))
        if entry_datetime <= now:
            return {"time_slot": time_str, "lucky_number": entry.lucky_number}

    except Exception as e:
        log(f"Malformed entry skipped: {entry} | {e}")

    return None


# =====================================================
# 🔹 Fetch Most Recent Lucky Number
# =====================================================
def fetch_last_lucky_number(now, lookback_limit=50):
    """
    Get the most recent valid lucky number whose (date + time_slot) <= now.

    Strategy:
      - Fetch the latest `lookback_limit` rows ordered by date desc, time_slot desc.
      - Return the first row where combined datetime <= now.
    """
    LotteryEntry = DocType("Lottery Entry")
    try:
        # fetch a small batch of the most recent entries (date desc, time_slot desc)
        results = (
            frappe.qb.from_(LotteryEntry)
            .select(LotteryEntry.date, LotteryEntry.time_slot, LotteryEntry.lucky_number)
            .where((LotteryEntry.date <= now.date()) & (LotteryEntry.docstatus == 1))
            .orderby(LotteryEntry.date, order=frappe.qb.desc)
            .orderby(LotteryEntry.time_slot, order=frappe.qb.desc)
            .limit(lookback_limit)
            .run(as_dict=True)
        )

        if not results:
            log("No previous lottery entries found")
            return None

        # iterate and pick the most recent one that is actually <= now
        for entry in results:
            time_str = normalize_time_format(entry.time_slot)
            if not time_str:
                # skip malformed time
                continue

            if is_past_entry(entry.date, time_str, now):
                log(f"Last lucky number found -> {entry.date} {time_str}: {entry.lucky_number}")
                return {
                    "time_slot": time_str,
                    "lucky_number": entry.lucky_number,
                    "lottery_date": entry.date.strftime("%Y-%m-%d"),
                }

        # if none in the batch was <= now, we log and return None
        log(f"No valid past entry found among the {len(results)} most recent entries (limit={lookback_limit}).")
        return None

    except Exception as e:
        log(f"Error fetching last lucky number: {e}")
        return None

# =====================================================
# 🔹 Fetch 36 Jodi
# =====================================================
@frappe.whitelist(allow_guest=True)
def get_36_jodi():
    # Assuming "Jodi 36" is a Single Doctype with a field "active"
    is_enabled = frappe.db.get_single_value("Jodi 36", "active")
    if not is_enabled:
        return None

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
        frappe.log_error(f"Error fetching Jodi 36 entries: {e}", "get_36_jodi")
        return None

    


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
            return raw_time
        return "00:00:00"
    except Exception as e:
        log(f"Time normalization failed: {raw_time} | {e}")
        return None


def is_past_entry(entry_date, time_str, now):
    """Return True if the entry datetime is in the past."""
    try:
        hh, mm, ss = map(int, time_str.split(":"))
        entry_datetime = datetime.combine(entry_date, time(hh, mm, ss))
        return entry_datetime <= now
    except Exception as e:
        log(f"Failed to check past entry for {entry_date} {time_str}: {e}")
        return False


def log(msg):
    """Consistent logging wrapper."""
    print(f"[Lottery API] {msg}")


import frappe
import random
from frappe.utils import now_datetime, time_diff_in_seconds, to_timedelta, cint, get_datetime

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
# 🔹 Helper Functions
# =====================================================

def get_frequency_seconds(frequency_value):
    """
    Convert Duration field into seconds.
    Handles string, numeric, or timedelta values.
    """
    if not frequency_value:
        return 86400  # Default 1 day

    try:
        # If it's a string like HH:MM:SS
        td = to_timedelta(frequency_value)
        return int(td.total_seconds())
    except Exception:
        # fallback numeric seconds
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
