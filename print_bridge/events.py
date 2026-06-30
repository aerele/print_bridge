"""Document event hooks for auto-print."""

import frappe


def on_submit(doc, method=None):
	_trigger_auto_print(doc, trigger="On Submit")


def on_workflow_state_change(doc, method=None):
	# on_update_after_submit fires on every post-submit save; only act when the
	# workflow state has actually changed, otherwise we double-print on each edit.
	if "workflow_state" not in (doc.meta.get_valid_columns() if doc.meta else []):
		return
	if not doc.has_value_changed("workflow_state"):
		return
	_trigger_auto_print(doc, trigger="On Workflow State", workflow_state=doc.get("workflow_state"))


def _trigger_auto_print(doc, trigger, workflow_state=None):
	from print_bridge.utils.resolver import resolve_settings

	formats = frappe.db.get_all(
		"Print Format Print Setting",
		filters={"auto_print_on": trigger},
		fields=["print_format", "auto_print_on", "workflow_state", "printer", "printer_group",
		        "copies", "copies_from_field", "duplex", "color_mode", "paper_size", "tray", "is_raw"],
	)

	for fmt in formats:
		if trigger == "On Workflow State":
			if fmt.workflow_state and fmt.workflow_state != workflow_state:
				continue

		pf_doc = frappe.db.get_value("Print Format", fmt.print_format, ["doc_type"], as_dict=True)
		if not pf_doc or pf_doc.doc_type != doc.doctype:
			continue

		copies = fmt.copies or 1
		if fmt.copies_from_field:
			try:
				copies = int(doc.get(fmt.copies_from_field) or 1)
			except (TypeError, ValueError):
				copies = 1

		try:
			from print_bridge.api.print_api import enqueue_print_job
			enqueue_print_job(
				reference_doctype=doc.doctype,
				reference_name=doc.name,
				print_format=fmt.print_format,
				printer=fmt.printer,
				printer_group=fmt.printer_group,
				copies=copies,
				duplex=fmt.duplex,
				color_mode=fmt.color_mode,
				paper_size=fmt.paper_size,
				tray=fmt.tray,
				is_raw=fmt.is_raw,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Print Bridge auto-print error")
