"""Frappe scheduler task entry points."""

import frappe


def all():
	"""Runs every ~5 minutes (Frappe 'all' schedule)."""
	from print_bridge.utils.jobs import check_agent_heartbeats, reclaim_stuck_printing_jobs

	check_agent_heartbeats()
	reclaim_stuck_printing_jobs()


def hourly():
	from print_bridge.utils.jobs import expire_old_jobs

	expire_old_jobs()
