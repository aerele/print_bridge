"""Agent-facing API endpoints.

The Print Agent daemon calls these over HTTPS (outbound from the office LAN).
All endpoints require a valid agent token via the X-Agent-Token header.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import now_datetime


def _authenticate_agent():
	"""Validate X-Agent-Token header and return the agent document."""
	token = frappe.get_request_header("X-Agent-Token")
	if not token:
		frappe.throw(_("Missing X-Agent-Token header"), frappe.AuthenticationError)

	token_hash = hashlib.sha256(token.encode()).hexdigest()
	agent_name = frappe.db.get_value("Print Agent", {"token_hash": token_hash})
	if not agent_name:
		frappe.throw(_("Invalid agent token"), frappe.AuthenticationError)

	return frappe.get_doc("Print Agent", agent_name)


@frappe.whitelist(allow_guest=True)
def register(agent_id, display_name=None, location=None, version=None):
	"""Called by a fresh agent with its token to register / re-register."""
	agent = _authenticate_agent()
	if agent.agent_id != agent_id:
		frappe.throw(_("Token does not match agent_id"), frappe.AuthenticationError)
	agent.display_name = display_name or agent.display_name
	agent.location = location or agent.location
	agent.version = version
	agent.update_heartbeat(version=version)
	return {"status": "ok", "agent": agent.name}


@frappe.whitelist(allow_guest=True)
def heartbeat(version=None, printer_statuses=None):
	"""Agent heartbeat. Also accepts printer status updates."""
	agent = _authenticate_agent()
	agent.update_heartbeat(version=version)

	if printer_statuses:
		import json

		statuses = json.loads(printer_statuses) if isinstance(printer_statuses, str) else printer_statuses
		for printer_name, status in statuses.items():
			printer = frappe.db.get_value(
				"Print Bridge Printer", {"printer_name": printer_name, "agent": agent.name}
			)
			if printer:
				frappe.db.set_value(
					"Print Bridge Printer",
					printer,
					{
						"status": status,
						"last_seen": now_datetime(),
					},
				)
	frappe.db.commit()
	return {"status": "ok"}


@frappe.whitelist(allow_guest=True)
def poll_jobs():
	"""Agent polls for jobs targeting its printers. Returns a list of pending jobs."""
	agent = _authenticate_agent()

	# Only consider Online printers: a job for an offline printer (machine or
	# printer powered off) must stay Ready and wait, not be claimed here. The
	# agent sends its heartbeat (which refreshes each printer's status) earlier
	# in the same poll cycle, so this status is fresh.
	printers = frappe.db.get_all(
		"Print Bridge Printer",
		filters={"agent": agent.name, "status": "Online"},
		pluck="name",
	)
	if not printers:
		return {"jobs": []}

	jobs = frappe.db.get_all(
		"Print Job",
		filters={"status": "Ready", "target_printer": ["in", printers]},
		fields=["name", "target_printer", "copies", "duplex", "color_mode", "paper_size", "tray", "is_raw"],
		order_by="requested_at asc",
		limit=10,
	)

	result = []
	for job in jobs:
		signed_url = _get_signed_file_url(job["name"])
		result.append({**job, "file_url": signed_url})
		frappe.db.set_value("Print Job", job["name"], "status", "Printing")

	frappe.db.commit()
	return {"jobs": result}


@frappe.whitelist(allow_guest=True)
def update_job_status(job_name, status, error=None):
	"""Agent reports the final status of a job."""
	agent = _authenticate_agent()
	# An agent may only report a terminal result or release a claimed job back to
	# the waiting pool. "Ready" is the release signal used when the printer turns
	# out to be offline (before or during printing).
	allowed = {"Completed", "Failed", "Ready"}
	if status not in allowed:
		frappe.throw(_("Agent may not set status {0}").format(status))

	if not frappe.db.exists("Print Job", job_name):
		frappe.throw(_("Print Job {0} not found").format(job_name))

	job = frappe.get_doc("Print Job", job_name)
	if job.agent and job.agent != agent.name:
		frappe.throw(_("Job {0} does not belong to this agent").format(job_name), frappe.PermissionError)

	# Only a job this agent has actually claimed may be released back to Ready.
	if status == "Ready" and job.status != "Printing":
		return {"status": "ignored"}

	job.set_status(status, error=error)
	frappe.db.commit()
	return {"status": "ok"}


@frappe.whitelist(allow_guest=True)
def download_job_file(job_name):
	"""Stream the rendered file for a job to the authenticated agent.

	The agent has no Frappe session cookie, so it cannot fetch the private
	/private/files/... URL directly. It calls this token-authenticated endpoint
	(with the X-Agent-Token header) instead.
	"""
	agent = _authenticate_agent()

	job = frappe.db.get_value("Print Job", job_name, ["agent", "rendered_file"], as_dict=True)
	if not job:
		frappe.throw(_("Print Job {0} not found").format(job_name))
	if job.agent and job.agent != agent.name:
		frappe.throw(_("Job {0} does not belong to this agent").format(job_name), frappe.PermissionError)
	if not job.rendered_file:
		frappe.throw(_("Job {0} has no rendered file").format(job_name))

	file_doc = frappe.get_doc("File", {"file_url": job.rendered_file})
	content = file_doc.get_content()

	frappe.local.response.filename = file_doc.file_name
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"


@frappe.whitelist(allow_guest=True)
def sync_printers(printers):
	"""Agent pushes its discovered local printers into the registry."""
	import json

	agent = _authenticate_agent()
	printers_data = json.loads(printers) if isinstance(printers, str) else printers

	created = []
	for p in printers_data:
		printer_name = p.get("name") or p.get("printer_name")
		if not printer_name:
			continue
		if frappe.db.exists("Print Bridge Printer", printer_name):
			existing = frappe.get_doc("Print Bridge Printer", printer_name)
			existing.supports_color = p.get("supports_color", existing.supports_color)
			existing.supports_duplex = p.get("supports_duplex", existing.supports_duplex)
			existing.status = "Online"
			existing.last_seen = now_datetime()
			existing.save(ignore_permissions=True)
		else:
			new_printer = frappe.get_doc(
				{
					"doctype": "Print Bridge Printer",
					"printer_name": printer_name,
					"display_name": p.get("display_name", printer_name),
					"transport": "agent",
					"agent": agent.name,
					"supports_color": p.get("supports_color", 0),
					"supports_duplex": p.get("supports_duplex", 0),
					"status": "Online",
					"last_seen": now_datetime(),
				}
			)
			new_printer.insert(ignore_permissions=True)
			created.append(printer_name)

	frappe.db.commit()
	return {"status": "ok", "created": created}


def _get_signed_file_url(job_name):
	"""Return the token-authenticated download URL for a job's rendered file.

	The agent fetches this with its X-Agent-Token header (see download_job_file).
	"""
	file_path = frappe.db.get_value("Print Job", job_name, "rendered_file")
	if not file_path:
		return None
	return frappe.utils.get_url(
		"/api/method/print_bridge.api.agent.download_job_file?job_name=" + frappe.utils.quote(job_name)
	)
