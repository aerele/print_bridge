"""Post-install setup."""

import frappe
from frappe import _


def after_install():
	_create_print_manager_role()
	_create_default_settings()
	_migrate_network_printer_settings()


def _create_print_manager_role():
	if not frappe.db.exists("Role", "Print Manager"):
		role = frappe.get_doc({"doctype": "Role", "role_name": "Print Manager"})
		role.insert(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep - commit setup/migration progress during install


def _create_default_settings():
	if not frappe.db.exists("Print Bridge Settings", "Print Bridge Settings"):
		settings = frappe.get_doc({"doctype": "Print Bridge Settings"})
		settings.insert(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep - commit setup/migration progress during install


def _migrate_network_printer_settings():
	settings = frappe.get_single("Print Bridge Settings")
	if not settings.migrate_network_printer_settings:
		return

	legacy = frappe.db.get_all(
		"Network Printer Settings",
		fields=["name", "printer_name", "server_ip", "port"],
	)
	for lp in legacy:
		printer_name = lp.printer_name or lp.name
		if frappe.db.exists("Print Bridge Printer", printer_name):
			continue
		uri = f"socket://{lp.server_ip}:{lp.port or 9100}" if lp.server_ip else ""
		new_p = frappe.get_doc(
			{
				"doctype": "Print Bridge Printer",
				"printer_name": printer_name,
				"display_name": printer_name,
				"transport": "cups_direct" if not lp.server_ip else "raw_socket",
				"printer_uri": uri,
				"status": "Unknown",
			}
		)
		new_p.insert(ignore_permissions=True)

	if legacy:
		frappe.db.commit()  # nosemgrep - commit setup/migration progress during install
		frappe.msgprint(
			_("Migrated {0} printer(s) from Network Printer Settings.").format(len(legacy)),
			title=_("Print Bridge Migration"),
		)
