import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class PrintBridgePrinter(Document):
	def mark_online(self):
		self.status = "Online"
		self.last_seen = now_datetime()
		self.save(ignore_permissions=True)

	def mark_offline(self, error=False):
		self.status = "Error" if error else "Offline"
		self.save(ignore_permissions=True)

	def get_transport_driver(self):
		from print_bridge.transport import get_driver

		return get_driver(self.transport)
