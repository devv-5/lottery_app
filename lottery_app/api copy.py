import frappe
from frappe import _
from datetime import datetime, time, timedelta
from frappe.query_builder import DocType

@frappe.whitelist(allow_guest=True)
def get_lottery_entries(date):
    """
    Returns Lottery Entries for a given date where the entry time is <= current time,
    along with the last lucky number from the highest date lottery's highest timeslot entry 
    where timeslot is <= current time.
    """
    print("\n\n[Lottery API] Called get_lottery_entries with date:", date, "\n")

    if not date:
        frappe.throw(_("Date is required"))

    try:
        # Validate date format
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        frappe.throw(_("Invalid date format. Please use YYYY-MM-DD"))

    now = datetime.now()
    print("[Lottery API] Current datetime:", now, "\n")

    # -----------------------------
    # Fetch selected date entries - SIMPLIFIED WITH date FIELD
    # -----------------------------
    entries = []
    try:
        LotteryEntry = DocType('Lottery Entry')
        
        # Directly query Lottery Entry with date field
        all_entries = (frappe.qb.from_(LotteryEntry)
                      .select(LotteryEntry.time_slot, LotteryEntry.lucky_number, LotteryEntry.date)
                      .where(
                          (LotteryEntry.date == date) & 
                          (LotteryEntry.docstatus == 1)
                      )
                      .orderby(LotteryEntry.time_slot)
                      .run(as_dict=True))

        print(f"[Lottery API] Found {len(all_entries)} total entries for date: {date}")

        for entry in all_entries:
            entry_time_raw = entry.time_slot
            try:
                if isinstance(entry_time_raw, timedelta):
                    total_seconds = int(entry_time_raw.total_seconds())
                    hh = total_seconds // 3600
                    mm = (total_seconds % 3600) // 60
                    ss = total_seconds % 60
                    entry_time_str = f"{hh:02d}:{mm:02d}:{ss:02d}"
                else:
                    entry_time_str = str(entry_time_raw or "00:00:00")

                # Parse time safely
                time_parts = entry_time_str.split(":")
                if len(time_parts) >= 2:
                    hh = int(time_parts[0])
                    mm = int(time_parts[1])
                    ss = int(time_parts[2]) if len(time_parts) > 2 else 0
                    
                    # Validate time components
                    if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                        # Create datetime object using the entry date
                        entry_date = entry.date
                        entry_datetime = datetime.combine(entry_date, time(hh, mm, ss))
                        
                        # Show entry only if it's in the past
                        if entry_datetime <= now:
                            entries.append({
                                "time_slot": entry_time_str,
                                "lucky_number": entry.lucky_number
                            })
                    else:
                        print(f"[Lottery API] Invalid time components: {entry_time_str}")
                else:
                    print(f"[Lottery API] Invalid time format: {entry_time_str}")

            except (ValueError, TypeError, AttributeError) as e:
                print(f"[Lottery API] Skipping malformed entry: {entry} | Error: {e}")
                continue

    except Exception as e:
        print(f"[Lottery API] Error fetching selected date entries: {e}")

    print(f"[Lottery API] Filtered entries for selected date ({date}): {len(entries)}\n")

    # -----------------------------
    # Determine last lucky number - SIMPLIFIED WITH date FIELD
    # -----------------------------
    last_entry = None
    try:
        LotteryEntry = DocType('Lottery Entry')
        
        # Get the single most recent valid entry across all lotteries
        last_lottery_entry = (frappe.qb.from_(LotteryEntry)
                             .select(
                                 LotteryEntry.date,
                                 LotteryEntry.time_slot,
                                 LotteryEntry.lucky_number
                             )
                             .where(
                                 (LotteryEntry.date <= now.date()) &
                                 (LotteryEntry.docstatus == 1)
                             )
                             .orderby(LotteryEntry.date, order=frappe.qb.desc)
                             .orderby(LotteryEntry.time_slot, order=frappe.qb.desc)
                             .limit(1)
                             .run(as_dict=True))

        if last_lottery_entry:
            entry = last_lottery_entry[0]
            entry_time_raw = entry.time_slot
            
            # Process time slot
            if isinstance(entry_time_raw, timedelta):
                total_seconds = int(entry_time_raw.total_seconds())
                hh = total_seconds // 3600
                mm = (total_seconds % 3600) // 60
                ss = total_seconds % 60
                entry_time_str = f"{hh:02d}:{mm:02d}:{ss:02d}"
            else:
                entry_time_str = str(entry_time_raw or "00:00:00")

            # Validate if the entry time is <= current time
            try:
                time_parts = entry_time_str.split(":")
                if len(time_parts) >= 2:
                    hh = int(time_parts[0])
                    mm = int(time_parts[1])
                    ss = int(time_parts[2]) if len(time_parts) > 2 else 0
                    
                    if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                        entry_datetime = datetime.combine(entry.date, time(hh, mm, ss))
                        
                        if entry_datetime <= now:
                            last_entry = {
                                "time_slot": entry_time_str,
                                "lucky_number": entry.lucky_number,
                                "lottery_date": entry.date.strftime("%Y-%m-%d")
                            }
                            print(f"[Lottery API] Found last lucky number -> Date: {entry.date}, Time Slot: {entry_time_str}, Lucky Number: {entry.lucky_number}")
                        else:
                            print(f"[Lottery API] Last entry time is in future, skipping: {entry_time_str}")
                    else:
                        print(f"[Lottery API] Invalid time components for last number: {entry_time_str}")
                else:
                    print(f"[Lottery API] Invalid time format for last number: {entry_time_str}")
                    
            except (ValueError, TypeError, AttributeError) as e:
                print(f"[Lottery API] Error processing last entry: {e}")

        if not last_entry:
            print("[Lottery API] No valid last lucky number found")

    except Exception as e:
        print(f"[Lottery API] Error fetching last lucky number: {e}")

    return {
        "entries": entries, 
        "last_entry": last_entry
    }