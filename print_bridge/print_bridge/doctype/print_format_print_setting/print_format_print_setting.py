import frappe
from frappe.model.document import Document


class PrintFormatPrintSetting(Document):
	def validate(self):
		if self.printer and self.printer_group:
			frappe.throw(frappe._("Set either Printer or Printer Group, not both."))
		if self.auto_print_on == "On Workflow State" and not self.workflow_state:
			frappe.throw(frappe._("Workflow State is required when Auto Print On is 'On Workflow State'."))
		if self.copies_from_field and self.copies and self.copies != 1:
			frappe.msgprint(frappe._("Copies from Field will override the static Copies value at print time."), alert=True)
