"""User-facing print API."""

import hashlib

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime


# Window within which an identical request is treated as a duplicate and deduped.
_DEDUPE_WINDOW_SECONDS = 120


@frappe.whitelist()
def enqueue_print_job(
	reference_doctype,
	reference_name,
	print_format=None,
	printer=None,
	printer_group=None,
	copies=1,
	duplex=None,
	color_mode=None,
	paper_size=None,
	tray=None,
	is_raw=0,
	action=None,
	force=0,
):
	"""Create a Print Job and dispatch it to the render worker."""
	frappe.has_permission(reference_doctype, doc=reference_name, throw=True)

	if not printer and not printer_group:
		resolved = _resolve_printer(reference_doctype, reference_name, print_format)
		printer = resolved.get("printer")
		printer_group = resolved.get("printer_group")

	if not printer and printer_group:
		group_doc = frappe.get_doc("Printer Group", printer_group)
		printer = group_doc.pick_printer()

	if not printer:
		# "Download PDF" is the documented default that preserves stock behaviour:
		# when nothing routes to a printer, hand the user a PDF instead of erroring.
		if action == "Download PDF":
			pdf_url = frappe.utils.get_url(
				"/api/method/frappe.utils.print_format.download_pdf"
				f"?doctype={frappe.utils.quote(reference_doctype)}"
				f"&name={frappe.utils.quote(reference_name)}"
				f"&format={frappe.utils.quote(print_format or '')}"
			)
			return {"action": "download_pdf", "url": pdf_url}
		frappe.throw(_("Could not resolve a printer for this document. Configure a Print Format Print Setting or Routing Rule."))

	# Deterministic key so accidental double-submits of the same request collapse,
	# while intentional reprints (force=1) always create a fresh job.
	idempotency_key = hashlib.sha256(
		f"{reference_doctype}:{reference_name}:{print_format}:{frappe.session.user}:{printer}:{int(copies)}".encode()
	).hexdigest()[:32]

	if not int(force):
		recent = frappe.db.get_value(
			"Print Job",
			{
				"idempotency_key": idempotency_key,
				"status": ["not in", ["Failed", "Cancelled", "Expired"]],
				"creation": [">", add_to_date(now_datetime(), seconds=-_DEDUPE_WINDOW_SECONDS)],
			},
			"name",
		)
		if recent:
			return {"job": recent, "status": "Duplicate"}

	printer_doc = frappe.get_doc("Print Bridge Printer", printer)

	job = frappe.get_doc({
		"doctype": "Print Job",
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"print_format": print_format,
		"target_printer": printer,
		"target_printer_group": printer_group,
		"agent": printer_doc.agent if printer_doc.transport == "agent" else None,
		"copies": int(copies),
		"duplex": duplex,
		"color_mode": color_mode,
		"paper_size": paper_size,
		"tray": tray,
		"is_raw": int(is_raw),
		"transport": printer_doc.transport,
		"idempotency_key": idempotency_key,
		"status": "Queued",
	})
	job.insert(ignore_permissions=True)
	frappe.db.commit()

	frappe.enqueue(
		"print_bridge.utils.jobs.render_and_dispatch",
		print_job=job.name,
		queue="short",
		timeout=300,
	)

	return {"job": job.name, "status": "Queued"}


@frappe.whitelist()
def get_print_settings_for_format(print_format=None, reference_doctype=None, reference_name=None):
	"""Return the resolved print settings for a given format (used by the UI dialog)."""
	from print_bridge.utils.resolver import resolve_settings
	settings = resolve_settings(
		print_format=print_format,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
	)
	return settings


@frappe.whitelist()
def get_jobs(reference_doctype=None, reference_name=None, limit=20):
	"""Return recent print jobs, optionally filtered to a document."""
	filters = {}
	if reference_doctype:
		filters["reference_doctype"] = reference_doctype
	if reference_name:
		filters["reference_name"] = reference_name

	# Regular users only see their own jobs; managers see all.
	manager_roles = {"System Manager", "Print Manager"}
	if not manager_roles.intersection(frappe.get_roles()):
		filters["requested_by"] = frappe.session.user

	return frappe.db.get_all(
		"Print Job",
		filters=filters,
		fields=["name", "status", "target_printer", "copies", "requested_at", "requested_by", "error_message"],
		order_by="requested_at desc",
		limit=int(limit),
	)


@frappe.whitelist()
def batch_print(jobs):
	"""Enqueue multiple print jobs from a list-view selection."""
	import json
	jobs_data = json.loads(jobs) if isinstance(jobs, str) else jobs
	results = []
	for job_params in jobs_data:
		try:
			result = enqueue_print_job(**job_params)
			results.append({"success": True, **result})
		except Exception as e:
			results.append({"success": False, "error": str(e), "params": job_params})
	return results


def _resolve_printer(reference_doctype, reference_name, print_format):
	"""Try routing rules first, then print format settings."""
	from print_bridge.utils.resolver import resolve_via_routing_rules, resolve_settings
	routing_result = resolve_via_routing_rules(
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		print_format=print_format,
	)
	if routing_result:
		return routing_result

	settings = resolve_settings(
		print_format=print_format,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
	)
	return {
		"printer": settings.get("printer"),
		"printer_group": settings.get("printer_group"),
	}
