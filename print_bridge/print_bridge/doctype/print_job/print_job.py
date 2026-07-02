import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class PrintJob(Document):
	def before_insert(self):
		if not self.idempotency_key:
			self.idempotency_key = frappe.generate_hash(length=32)
		if not self.requested_at:
			self.requested_at = now_datetime()
		if not self.requested_by:
			self.requested_by = frappe.session.user

	@frappe.whitelist()
	def reprint(self):
		"""Enqueue this job again as a new Print Job."""
		from print_bridge.api.print_api import enqueue_print_job

		return enqueue_print_job(
			reference_doctype=self.reference_doctype,
			reference_name=self.reference_name,
			print_format=self.print_format,
			printer=self.target_printer,
			printer_group=self.target_printer_group,
			copies=self.copies,
			duplex=self.duplex,
			color_mode=self.color_mode,
			paper_size=self.paper_size,
			tray=self.tray,
			is_raw=self.is_raw,
			force=1,
		)

	@frappe.whitelist()
	def hold(self):
		if self.status not in ("Queued", "Ready"):
			frappe.throw(frappe._("Only Queued or Ready jobs can be held."))
		self.status = "Held"
		self.save(ignore_permissions=True)

	@frappe.whitelist()
	def release(self):
		if self.status != "Held":
			frappe.throw(frappe._("Only Held jobs can be released."))
		self.status = "Queued"
		self.save(ignore_permissions=True)
		# If the job was held before it was ever rendered, it must be rendered
		# first; otherwise just re-dispatch the already-rendered file.
		if self.rendered_file:
			from print_bridge.utils.jobs import dispatch_job

			frappe.enqueue(dispatch_job, print_job=self.name, queue="short")
		else:
			from print_bridge.utils.jobs import render_and_dispatch

			frappe.enqueue(render_and_dispatch, print_job=self.name, queue="short", timeout=300)

	@frappe.whitelist()
	def cancel_job(self):
		if self.status in ("Completed", "Cancelled"):
			frappe.throw(frappe._("Cannot cancel a {0} job.").format(self.status))
		self.status = "Cancelled"
		self.save(ignore_permissions=True)

	def set_status(self, status, error=None):
		self.status = status
		if error:
			self.error_message = str(error)
		self.save(ignore_permissions=True)
		frappe.publish_realtime(
			"print_job_status",
			{"job": self.name, "status": status, "error": error},
			user=self.requested_by,
		)
