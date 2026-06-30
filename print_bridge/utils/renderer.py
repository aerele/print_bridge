"""Render a Print Format to PDF or raw bytes and attach to a Print Job."""

import frappe
from frappe.utils import get_files_path
from frappe.utils.file_manager import save_file


def render_job(job_doc):
	"""Render the document to bytes, store as a private file, and return the bytes."""
	job_doc.set_status("Rendering")

	settings = frappe.get_single("Print Bridge Settings")
	timeout = settings.render_timeout or 30

	try:
		if job_doc.is_raw:
			content = _render_raw(job_doc)
			ext = "bin"
		else:
			content = _render_pdf(job_doc, timeout=timeout)
			ext = "pdf"
	except Exception as e:
		job_doc.set_status("Failed", error=str(e))
		raise

	filename = f"{job_doc.name}.{ext}"
	file_doc = save_file(
		filename,
		content,
		"Print Job",
		job_doc.name,
		is_private=1,
		df="rendered_file",
	)
	job_doc.rendered_file = file_doc.file_url
	job_doc.save(ignore_permissions=True)
	return content


def _render_pdf(job_doc, timeout=30):
	# Render straight to PDF via frappe.get_print so the Print Format's configured
	# pdf_generator is honored. Default to "chrome" (the modern v16 engine) when the
	# format does not set one — this also covers the built-in "Standard" format.
	import shutil

	pdf_generator = (
		frappe.get_cached_value("Print Format", job_doc.print_format, "pdf_generator")
		or "chrome"
	)
	# Fall back to whichever engine is actually installed: a format may ask for
	# wkhtmltopdf on a bench that only ships Chrome (or vice versa).
	if pdf_generator == "wkhtmltopdf" and not shutil.which("wkhtmltopdf"):
		pdf_generator = "chrome"

	return frappe.get_print(
		job_doc.reference_doctype,
		job_doc.reference_name,
		print_format=job_doc.print_format,
		as_pdf=True,
		pdf_generator=pdf_generator,
	)


def _render_raw(job_doc):
	"""Render to raw bytes via the print format's Jinja template.

	The template is expected to emit ESC/POS or ZPL bytes encoded as latin-1.
	"""
	html = frappe.get_print(
		job_doc.reference_doctype,
		job_doc.reference_name,
		print_format=job_doc.print_format,
		as_pdf=False,
	)
	return html.encode("latin-1", errors="replace")
