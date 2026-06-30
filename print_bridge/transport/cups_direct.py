"""Direct CUPS transport — for LAN benches that can reach the printer directly."""
import time

import frappe
from print_bridge.transport.base import BaseTransport

# How long to wait for CUPS to confirm the job actually printed before failing it.
_CONFIRM_TIMEOUT_SECONDS = 60
_POLL_INTERVAL_SECONDS = 2

# IPP job-state values (RFC 8011)
_JOB_CANCELED = 7
_JOB_ABORTED = 8
_JOB_COMPLETED = 9


class CupsDirectTransport(BaseTransport):
	def deliver(self, job_doc, file_content: bytes) -> None:
		try:
			import cups
		except ImportError:
			raise RuntimeError(
				"pycups is not installed. Run: pip install pycups. "
				"CUPS must be installed on the bench server."
			)

		printer_doc = frappe.get_doc("Print Bridge Printer", job_doc.target_printer)
		conn = cups.Connection()

		options = {}
		if job_doc.duplex and job_doc.duplex != "None":
			options["sides"] = "two-sided-long-edge" if job_doc.duplex == "Long Edge" else "two-sided-short-edge"
		if job_doc.color_mode:
			options["print-color-mode"] = "color" if job_doc.color_mode == "Color" else "monochrome"
		if job_doc.paper_size:
			options["media"] = job_doc.paper_size
		if job_doc.tray:
			options["InputSlot"] = job_doc.tray
		if job_doc.copies and job_doc.copies > 1:
			options["copies"] = str(job_doc.copies)

		printer_name = printer_doc.printer_name
		title = f"PrintBridge-{job_doc.name}"

		import tempfile, os
		with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
			f.write(file_content)
			tmp_path = f.name

		try:
			if job_doc.is_raw:
				cups_job_id = conn.printFile(printer_name, tmp_path, title, {"raw": "true"})
			else:
				cups_job_id = conn.printFile(printer_name, tmp_path, title, options)
		finally:
			os.unlink(tmp_path)

		# printFile only queues the job in CUPS and returns immediately. Confirm the
		# printer actually completed it, so a job CUPS later aborts (printer offline,
		# unsupported format, no driver) is reported Failed instead of a false Completed.
		self._confirm_printed(conn, printer_name, cups_job_id)

	def _confirm_printed(self, conn, printer_name, cups_job_id):
		import cups

		deadline = time.monotonic() + _CONFIRM_TIMEOUT_SECONDS
		while True:
			try:
				attrs = conn.getJobAttributes(cups_job_id)
			except cups.IPPError:
				# Job no longer in CUPS — purged after a successful completion.
				return
			state = attrs.get("job-state")
			reasons = attrs.get("job-state-reasons")
			if state == _JOB_COMPLETED:
				return
			if state in (_JOB_CANCELED, _JOB_ABORTED):
				raise RuntimeError(
					f"CUPS job {cups_job_id} on '{printer_name}' did not print "
					f"(state {state}: {reasons}). Check the printer is on and the driver is correct."
				)
			if time.monotonic() > deadline:
				raise RuntimeError(
					f"CUPS job {cups_job_id} on '{printer_name}' was not confirmed printed "
					f"within {_CONFIRM_TIMEOUT_SECONDS}s (state {state}: {reasons}). "
					"The printer may be offline, paused, or unreachable."
				)
			time.sleep(_POLL_INTERVAL_SECONDS)

	def supports_raw(self) -> bool:
		return True

	def completes_synchronously(self) -> bool:
		return True
