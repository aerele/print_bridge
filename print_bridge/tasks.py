"""Frappe scheduler task entry points."""

import frappe


def all():
	"""Runs every ~5 minutes (Frappe 'all' schedule)."""
	from print_bridge.utils.jobs import check_agent_heartbeats, reclaim_stuck_printing_jobs

	# Isolate the two sweeps: a failure in one must not stop the other from running,
	# and should surface in the Error Log rather than fail the scheduler tick silently.
	for task in (check_agent_heartbeats, reclaim_stuck_printing_jobs):
		try:
			task()
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Print Bridge scheduler: {task.__name__} failed")


def hourly():
	from print_bridge.utils.jobs import expire_old_jobs

	try:
		expire_old_jobs()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Print Bridge scheduler: expire_old_jobs failed")
