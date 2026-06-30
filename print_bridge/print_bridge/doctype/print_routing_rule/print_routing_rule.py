import frappe
from frappe.model.document import Document


class PrintRoutingRule(Document):
	def validate(self):
		if not self.printer and not self.printer_group:
			frappe.throw(frappe._("Each routing rule must resolve to a Printer or Printer Group."))
		if self.printer and self.printer_group:
			frappe.throw(frappe._("Set either Printer or Printer Group, not both."))
