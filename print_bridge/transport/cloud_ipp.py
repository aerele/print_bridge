"""Cloud IPP transport — for internet-reachable IPP-Everywhere printers."""

import frappe

from print_bridge.transport.base import BaseTransport


class CloudIppTransport(BaseTransport):
	def deliver(self, job_doc, file_content: bytes) -> None:
		try:
			import cups
		except ImportError:
			raise RuntimeError("pycups is required for Cloud IPP. Run: pip install pycups")

		printer_doc = frappe.get_doc("Print Bridge Printer", job_doc.target_printer)
		printer_uri = printer_doc.printer_uri
		if not printer_uri:
			raise ValueError(f"Printer URI not set on {printer_doc.printer_name}")

		conn = cups.Connection()
		options = {}
		if job_doc.copies and job_doc.copies > 1:
			options["copies"] = str(job_doc.copies)
		if job_doc.duplex and job_doc.duplex != "None":
			options["sides"] = (
				"two-sided-long-edge" if job_doc.duplex == "Long Edge" else "two-sided-short-edge"
			)

		import os
		import tempfile

		with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
			f.write(file_content)
			tmp_path = f.name
		try:
			conn.printFile(printer_uri, tmp_path, f"PrintBridge-{job_doc.name}", options)
		finally:
			os.unlink(tmp_path)

	def completes_synchronously(self) -> bool:
		return True
