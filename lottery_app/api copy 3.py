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




def auto_jodi_scheduler():
    settings = frappe.get_single('Jodi 36')
    active = settings.active
    auto_generate_jodi = settings.auto_generate_jodi
    if not (active and auto_generate_jodi):
        return
    
    auto_create_jodi(settings)
    
    
def auto_create_jodi(settings):
    number_of_jodi = settings.number_of_jodi
    frequency = settings.number_of_jodi
    
    
    