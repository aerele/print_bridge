import frappe
from frappe.model.document import Document


class PrinterGroup(Document):
	def get_active_printers(self):
		return [
			m.printer for m in self.members
			if m.is_active and frappe.db.get_value("Print Bridge Printer", m.printer, "status") == "Online"
		]

	def pick_printer(self):
		"""Return the best available printer from this group based on failover strategy."""
		active = [
			m for m in sorted(self.members, key=lambda x: x.priority)
			if m.is_active
		]
		if not active:
			frappe.throw(frappe._("No active printers in group {0}.").format(self.group_name))

		online = [
			m.printer for m in active
			if frappe.db.get_value("Print Bridge Printer", m.printer, "status") == "Online"
		]
		if not online:
			frappe.throw(frappe._("No online printers in group {0}.").format(self.group_name))

		if self.failover_strategy == "Round Robin":
			import random
			return random.choice(online)

		# Priority: active is sorted by priority, so online[0] is the
		# highest-priority printer that is currently Online.
		return online[0]
