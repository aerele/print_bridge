"""Browser / QZ Tray transport.

For desk / USB printing. When selected, the job is rendered and stored; the
Frappe desk UI picks up the Ready status and triggers QZ Tray (or the browser
print dialog) via a realtime event. No server-to-printer network path needed.
"""
import frappe
from print_bridge.transport.base import BaseTransport


class BrowserQzTransport(BaseTransport):
	def deliver(self, job_doc, file_content: bytes) -> None:
		"""Mark job Ready and push a realtime event so the browser can print."""
		job_doc.set_status("Ready")
		frappe.publish_realtime(
			"print_bridge_browser_print",
			{
				"job": job_doc.name,
				"file_url": job_doc.rendered_file,
				"copies": job_doc.copies,
				"is_raw": job_doc.is_raw,
			},
			user=job_doc.requested_by,
		)
