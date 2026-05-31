# Copyright (c) 2025, Samad and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from datetime import datetime, timedelta
import random

class Lottery(Document):

    def validate(self):
        """Runs on every save to ensure uniqueness and valid time range."""
        self.append_entries()
        self.set_date_to_each_entry() 

    def before_insert(self):
        """Auto-generate entries on creation if not present."""
        self.validate_date()

    def before_submit(self):
        """Ensure no missing entries on submission if auto-gen is off."""
        # Optional: You can remove this check if you want to allow blank submissions entirely
        pass

    # -------------------- Helpers --------------------
    
    def set_date_to_each_entry(self):
        for entry in self.lottery_entries:
            entry.date = self.date

    def append_entries(self):
        """Generate time slots and pre-fill hidden auto-generated numbers."""
        if self.lottery_entries:
            return  

        freq_map = {"15 mins": 15, "30 mins": 30, "1 Hour": 60}
        interval = freq_map.get(self.frequency, 60)

        start_str = (self.start_time or "00:00").split('.')[0]
        end_str = (self.end_time or "23:59").split('.')[0]
        time_format = "%H:%M" if len(start_str) == 5 else "%H:%M:%S"

        start = datetime.strptime(start_str, time_format)
        end = datetime.strptime(end_str, time_format)

        while start < end:
            if self.auto_generate_number:
                self.append("lottery_entries", {
                    "time_slot": start.strftime("%H:%M"),
                    "date": self.date,
                    # 🔥 SECRET SAUCE: Pre-generate the fallback number here
                    "auto_generated_number": f"{random.randint(0, 99):02d}" 
                })
            else:
                self.append("lottery_entries", {
                    "time_slot": start.strftime("%H:%M"),
                    "date": self.date,
                })
            start += timedelta(minutes=interval)

    def validate_date(self):
        if not self.date:
            frappe.throw("Date is required.")

        already_exists = frappe.db.exists(
            "Lottery",
            {"date": self.date, "docstatus": ["<", 2]},
        )
        if already_exists:
            frappe.throw(f"Lottery for {self.date} already exists.")