# Copyright (c) 2025, Samad and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from datetime import datetime, timedelta
import random

class Lottery(Document):

    def validate(self):
        """Runs on every save to ensure uniqueness and valid time range."""
        # self.validate_time_range()
        self.append_entries()
        self.set_date_to_each_entry()

    def before_insert(self):
        """Auto-generate entries on creation if not present."""
        self.validate_date()

    def before_submit(self):
        """Ensure no missing entries on submission."""
        if not self.lottery_entries:
            frappe.throw("Cannot submit Lottery without any entries.")

    # -------------------- Helpers --------------------
    
    
    def set_date_to_each_entry(self):
        for entry in self.lottery_entries:
            entry.date = self.date

    def append_entries(self):
        """Generate time slots and lucky numbers based on frequency."""
        if self.lottery_entries:
            return  # skip if already populated

        freq_map = {"15 mins": 15, "30 mins": 30, "1 Hour": 60}
        interval = freq_map.get(self.frequency, 60)

        # Safe parsing for Frappe Time field (handles seconds/microseconds)
        start_str = (self.start_time or "00:00").split('.')[0]
        end_str = (self.end_time or "23:59").split('.')[0]

        # Determine format: HH:MM or HH:MM:SS
        time_format = "%H:%M" if len(start_str) == 5 else "%H:%M:%S"

        start = datetime.strptime(start_str, time_format)
        end = datetime.strptime(end_str, time_format)

        while start < end:
            self.append("lottery_entries", {
                "time_slot": start.strftime("%H:%M"),
                # "lucky_number": random.randint(1000, 9999)
            })
            start += timedelta(minutes=interval)

    def validate_date(self):
        """Ensure only one Lottery per date."""
        if not self.date:
            frappe.throw("Date is required.")

        already_exists = frappe.db.exists(
            "Lottery",
            {"date": self.date, "docstatus": ["<", 2]},
        )
        if already_exists:
            frappe.throw(f"Lottery for {self.date} already exists.")

    def validate_time_range(self):
        """Ensure Start Time < End Time."""
        print("Debug", self.start_time, self.end_time)
        if self.start_time and self.end_time:
            start_str = self.start_time.split('.')[0]
            end_str = self.end_time.split('.')[0]
            time_format = "%H:%M" if len(start_str) == 5 else "%H:%M:%S"

            start = datetime.strptime(start_str, time_format)
            end = datetime.strptime(end_str, time_format)

            if start >= end:
                frappe.throw("Start Time must be before End Time.")
