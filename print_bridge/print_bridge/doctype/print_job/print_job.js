// Copyright (c) 2026, Aerele Technologies and contributors
// For license information, please see license.txt

// Client script for the Print Job form — exposes the spool actions
// (Reprint / Hold / Release / Cancel) documented in the user guide.

frappe.ui.form.on("Print Job", {
	refresh(frm) {
		if (frm.is_new()) return;

		const status = frm.doc.status;

		// Reprint — available for any status (creates a brand-new job).
		frm.add_custom_button(__("Reprint"), () => print_bridge_job_action(frm, "reprint", {
			reload: false,
			done: (r) => {
				if (r.message && r.message.job) {
					frappe.show_alert({
						message: __("Reprint queued: {0}", [r.message.job]),
						indicator: "green",
					});
				}
			},
		}));

		// Hold — only Queued or Ready jobs can be held.
		if (["Queued", "Ready"].includes(status)) {
			frm.add_custom_button(__("Hold"), () => print_bridge_job_action(frm, "hold"));
		}

		// Release — only Held jobs can be released.
		if (status === "Held") {
			frm.add_custom_button(__("Release"), () => print_bridge_job_action(frm, "release"));
		}

		// Cancel — anything except Completed or Cancelled.
		if (!["Completed", "Cancelled"].includes(status)) {
			frm.add_custom_button(__("Cancel"), () =>
				frappe.confirm(__("Cancel this print job? It will never be printed."), () =>
					print_bridge_job_action(frm, "cancel_job"),
				),
			);
		}
	},
});

function print_bridge_job_action(frm, method, opts = {}) {
	frm.call(method).then((r) => {
		if (opts.done) opts.done(r);
		if (opts.reload !== false) frm.reload_doc();
	});
}
