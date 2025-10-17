// Copyright (c) 2025, Samad and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lottery", {
    refresh(frm) {
        if (frm.is_new()) {
            frm.set_value('start_time', '08:00:00');
            frm.set_value('end_time', '23:59:59');
        }

    },
});
