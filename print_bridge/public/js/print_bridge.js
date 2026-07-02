/**
 * Print Bridge — Frappe Desk integration
 *
 * Injects a "Print via Bridge" button into the form toolbar and handles
 * the print dialog, batch print from list view, and browser/QZ Tray realtime events.
 */

frappe.provide("print_bridge");

// Resolve the default print format for a form. Frappe stores it on the DocType
// meta; fall back to the built-in "Standard" format when none is configured.
print_bridge.default_print_format = function (frm) {
	return (frm.meta && frm.meta.default_print_format) || "Standard";
};

// ── Form toolbar button ───────────────────────────────────────────────────────

frappe.ui.form.on("*", {
	refresh(frm) {
		if (frm.doc.docstatus === undefined || frm.doc.__islocal) return;

		frm.add_custom_button(
			__("Print via Bridge"),
			() => {
				print_bridge.open_print_dialog(frm);
			},
			__("Actions")
		);
	},
});

// ── Print dialog ──────────────────────────────────────────────────────────────

print_bridge.open_print_dialog = function (frm) {
	frappe.call({
		method: "print_bridge.api.print_api.get_print_settings_for_format",
		args: {
			print_format: print_bridge.default_print_format(frm),
			reference_doctype: frm.doctype,
			reference_name: frm.docname,
		},
		callback(r) {
			const settings = r.message || {};
			const dialog = new frappe.ui.Dialog({
				title: __("Print via Bridge"),
				fields: [
					{
						label: __("Print Format"),
						fieldname: "print_format",
						fieldtype: "Link",
						options: "Print Format",
						reqd: 1,
						default: print_bridge.default_print_format(frm),
						get_query: () => {
							return {
								filters: { doc_type: frm.doctype },
							};
						},
					},
					{
						label: __("Printer"),
						fieldname: "printer",
						fieldtype: "Link",
						options: "Print Bridge Printer",
						default: settings.printer,
					},
					{
						label: __("Copies"),
						fieldname: "copies",
						fieldtype: "Int",
						default: settings.copies || 1,
					},
					{ fieldtype: "Column Break" },
					{
						label: __("Duplex"),
						fieldname: "duplex",
						fieldtype: "Select",
						options: "None\nLong Edge\nShort Edge",
						default: settings.duplex,
					},
					{
						label: __("Color Mode"),
						fieldname: "color_mode",
						fieldtype: "Select",
						options: "Color\nMonochrome",
						default: settings.color_mode,
					},
					{
						label: __("Paper Size"),
						fieldname: "paper_size",
						fieldtype: "Select",
						options: "A4\nA5\nLetter\nLegal\nCustom",
						default: settings.paper_size,
					},
				],
				primary_action_label: __("Print"),
				primary_action(values) {
					dialog.hide();
					frappe.call({
						method: "print_bridge.api.print_api.enqueue_print_job",
						args: {
							reference_doctype: frm.doctype,
							reference_name: frm.docname,
							print_format: values.print_format,
							printer: values.printer,
							copies: values.copies || 1,
							duplex: values.duplex,
							color_mode: values.color_mode,
							paper_size: values.paper_size,
							action: settings.action,
						},
						callback(r) {
							if (!r.message) return;
							if (r.message.action === "download_pdf") {
								window.open(r.message.url, "_blank");
								return;
							}
							frappe.show_alert({
								message: __("Print job queued: {0}", [r.message.job]),
								indicator: "green",
							});
							print_bridge.watch_job(r.message.job, frm);
						},
					});
				},
			});
			dialog.show();
		},
	});
};

// ── Realtime job status toast ─────────────────────────────────────────────────

print_bridge.watch_job = function (job_name, frm) {
	frappe.realtime.on("print_job_status", (data) => {
		if (data.job !== job_name) return;
		if (data.status === "Completed") {
			frappe.show_alert({ message: __("Printed: {0}", [job_name]), indicator: "green" });
		} else if (data.status === "Failed") {
			frappe.show_alert({
				message: __("Print failed: {0}", [data.error || job_name]),
				indicator: "red",
			});
		}
	});
};

// ── Browser / QZ Tray realtime handler ───────────────────────────────────────

frappe.realtime.on("print_bridge_browser_print", (data) => {
	if (!data.file_url) return;
	// Open the rendered PDF in a new window for browser printing.
	// If QZ Tray is available on the user's machine, it can intercept this.
	const win = window.open(data.file_url, "_blank");
	if (win) win.focus();
});

// ── List view batch print ─────────────────────────────────────────────────────

(function () {
	if (!frappe.views || !frappe.views.ListView || !frappe.views.ListView.prototype) return;
	const orig = frappe.views.ListView.prototype.get_actions_menu_items;
	if (!orig) return;
	frappe.views.ListView.prototype.get_actions_menu_items = function () {
		const items = orig.call(this);
		items.push({
			label: __("Print via Bridge"),
			action: () => {
				const selected = this.get_checked_items(true);
				if (!selected.length) {
					frappe.msgprint(__("Select at least one record."));
					return;
				}
				print_bridge.open_batch_print_dialog(this.doctype, selected);
			},
		});
		return items;
	};
})();

print_bridge.open_batch_print_dialog = function (doctype, names) {
	const dialog = new frappe.ui.Dialog({
		title: __("Batch Print via Bridge — {0} document(s)", [names.length]),
		fields: [
			{
				label: __("Print Format"),
				fieldname: "print_format",
				fieldtype: "Link",
				options: "Print Format",
				reqd: 1,
			},
			{
				label: __("Printer"),
				fieldname: "printer",
				fieldtype: "Link",
				options: "Print Bridge Printer",
			},
			{
				label: __("Copies"),
				fieldname: "copies",
				fieldtype: "Int",
				default: 1,
			},
		],
		primary_action_label: __("Print All"),
		primary_action(values) {
			dialog.hide();
			const jobs = names.map((name) => ({
				reference_doctype: doctype,
				reference_name: name,
				print_format: values.print_format,
				printer: values.printer,
				copies: values.copies || 1,
			}));
			frappe.call({
				method: "print_bridge.api.print_api.batch_print",
				args: { jobs: JSON.stringify(jobs) },
				callback(r) {
					const results = r.message || [];
					const ok = results.filter((x) => x.success).length;
					const fail = results.length - ok;
					frappe.show_alert({
						message: __("{0} queued, {1} failed", [ok, fail]),
						indicator: fail ? "orange" : "green",
					});
				},
			});
		},
	});
	dialog.show();
};
