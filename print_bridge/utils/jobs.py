"""Background job workers — called by Frappe's RQ worker pool."""

import frappe

# How long an agent may hold a claimed job (Ready→Printing) before we assume the
# agent died and return the job to the waiting pool. Comfortably longer than the
# agent's 60s confirm_printed window so a slow-but-healthy print is never reclaimed
# mid-flight (which would risk a duplicate print).
_PRINTING_LEASE_MINUTES = 15


def render_and_dispatch(print_job):
	"""Render the print job document and hand off to the transport driver."""
	job_doc = frappe.get_doc("Print Job", print_job)
	if job_doc.status not in ("Queued",):
		return

	settings = frappe.get_single("Print Bridge Settings")
	max_attempts = settings.max_retry_attempts or 3

	job_doc.attempts = (job_doc.attempts or 0) + 1
	job_doc.save(ignore_permissions=True)

	try:
		from print_bridge.utils.renderer import render_job

		content = render_job(job_doc)
	except Exception as e:
		_handle_failure(job_doc, e, max_attempts)
		return

	try:
		from print_bridge.transport import get_driver

		printer_doc = frappe.get_doc("Print Bridge Printer", job_doc.target_printer)
		driver = get_driver(printer_doc.transport)
		driver.deliver(job_doc, content)
		# Direct transports print inline; handoff transports (agent, browser_qz) have
		# already moved the job to Ready and report Completed later.
		if driver.completes_synchronously():
			job_doc.set_status("Completed")
	except Exception as e:
		_handle_failure(job_doc, e, max_attempts)
		return

	frappe.db.commit()  # nosemgrep - persist job/agent state from background worker or scheduler


def dispatch_job(print_job):
	"""Re-dispatch an already-rendered (Ready or Held→Released) job."""
	job_doc = frappe.get_doc("Print Job", print_job)
	if job_doc.status not in ("Ready", "Queued"):
		return
	try:
		content = _load_rendered_file(job_doc)
		from print_bridge.transport import get_driver

		printer_doc = frappe.get_doc("Print Bridge Printer", job_doc.target_printer)
		driver = get_driver(printer_doc.transport)
		driver.deliver(job_doc, content)
		if driver.completes_synchronously():
			job_doc.set_status("Completed")
	except Exception as e:
		job_doc.set_status("Failed", error=str(e))
	frappe.db.commit()  # nosemgrep - persist job/agent state from background worker or scheduler


def _handle_failure(job_doc, error, max_attempts):
	if job_doc.attempts < max_attempts:
		job_doc.set_status("Queued", error=str(error))
		frappe.enqueue(
			render_and_dispatch,
			print_job=job_doc.name,
			queue="short",
			timeout=300,
		)
	else:
		job_doc.set_status("Failed", error=str(error))
	frappe.db.commit()  # nosemgrep - persist job/agent state from background worker or scheduler


def _load_rendered_file(job_doc):
	if not job_doc.rendered_file:
		raise ValueError("No rendered file attached to job")
	file_doc = frappe.get_doc("File", {"file_url": job_doc.rendered_file})
	return file_doc.get_content()


def expire_old_jobs():
	"""Mark Queued/Ready jobs older than TTL as Expired. Called by scheduler."""
	settings = frappe.get_single("Print Bridge Settings")
	ttl_hours = settings.job_ttl_hours or 24

	cutoff = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-ttl_hours)
	old_jobs = frappe.db.get_all(
		"Print Job",
		filters={"status": ["in", ["Queued", "Ready", "Rendering"]], "requested_at": ["<", cutoff]},
		fields=["name", "status", "transport"],
	)
	for job in old_jobs:
		# Agent jobs waiting in Ready must hold indefinitely until the office
		# machine/printer comes back online — never expire them. Queued/Rendering
		# (a genuinely stuck render) and non-agent Ready jobs still respect the TTL.
		if job.status == "Ready" and job.transport == "agent":
			continue
		frappe.db.set_value("Print Job", job.name, "status", "Expired")

	if old_jobs:
		frappe.db.commit()  # nosemgrep - persist job/agent state from background worker or scheduler


def check_agent_heartbeats():
	"""Mark agents Offline if they haven't sent a heartbeat in 5 minutes."""
	cutoff = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-5)
	stale = frappe.db.get_all(
		"Print Agent",
		filters={"status": "Online", "last_heartbeat": ["<", cutoff]},
		pluck="name",
	)
	for agent_name in stale:
		frappe.db.set_value("Print Agent", agent_name, "status", "Offline")
		printers = frappe.db.get_all(
			"Print Bridge Printer",
			filters={"agent": agent_name, "status": "Online"},
			pluck="name",
		)
		for p in printers:
			frappe.db.set_value("Print Bridge Printer", p, "status", "Offline")

	if stale:
		frappe.db.commit()  # nosemgrep - persist job/agent state from background worker or scheduler


def reclaim_stuck_printing_jobs():
	"""Return agent jobs stuck in Printing back to Ready when the lease expires.

	poll_jobs flips a job Ready→Printing on claim, before the agent confirms
	anything. If the agent crashes (or the machine dies) after claiming, the job
	would otherwise sit in Printing forever. We use the row's `modified` time —
	bumped by the claim's set_value — as the claim timestamp. The Online-printer
	gate in poll_jobs ensures a reclaimed job is only re-handed-out once the
	printer is genuinely back online.
	"""
	cutoff = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-_PRINTING_LEASE_MINUTES)
	stuck = frappe.db.get_all(
		"Print Job",
		filters={"status": "Printing", "transport": "agent", "modified": ["<", cutoff]},
		pluck="name",
	)
	for job_name in stuck:
		frappe.db.set_value("Print Job", job_name, "status", "Ready")

	if stuck:
		frappe.db.commit()  # nosemgrep - persist job/agent state from background worker or scheduler
