"""Local CUPS interaction via the `lp`/`lpstat` CLIs — no pycups dependency.

Mirrors the option mapping and the "confirm the job actually printed" logic of
the bench-side ``print_bridge/transport/cups_direct.py``, but using subprocess
so the agent host needs no compiled C extension.
"""

import logging
import re
import subprocess
import time

log = logging.getLogger("print_bridge_agent.printers")

# How long to wait for CUPS to confirm a job actually printed before failing it.
_CONFIRM_TIMEOUT_SECONDS = 60
_POLL_INTERVAL_SECONDS = 2


class PrinterOfflineError(RuntimeError):
	"""The target CUPS queue is disabled/offline.

	Distinct from a generic failure: the job should be released back to the
	bench's waiting pool (Ready) so it prints when the printer returns, rather
	than being marked Failed.
	"""


def _run(args, timeout=60):
	return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def discover_printers():
	"""Return local CUPS queues as a sync_printers payload."""
	result = _run(["lpstat", "-e"])  # one queue name per line
	printers = []
	for name in (n.strip() for n in result.stdout.splitlines()):
		if not name:
			continue
		printers.append(
			{
				"name": name,
				"printer_name": name,
				"display_name": _description(name) or name,
				"supports_color": 0,
				"supports_duplex": 0,
			}
		)
	return printers


def _description(name):
	result = _run(["lpstat", "-l", "-p", name])
	for line in result.stdout.splitlines():
		line = line.strip()
		if line.startswith("Description:"):
			return line.split(":", 1)[1].strip()
	return None


def printer_statuses():
	"""Map each local queue to Online/Offline for the heartbeat."""
	result = _run(["lpstat", "-p"])
	statuses = {}
	for line in result.stdout.splitlines():
		parts = line.split()
		if len(parts) >= 2 and parts[0] == "printer":
			statuses[parts[1]] = "Offline" if "disabled" in line.lower() else "Online"
	return statuses


def is_online(printer):
	"""True if the given CUPS queue is enabled/accepting (not disabled/offline)."""
	return printer_statuses().get(printer) == "Online"


def build_lp_args(job):
	"""Map Print Job fields → `lp` options (mirrors cups_direct.py)."""
	args = []
	copies = job.get("copies")
	if copies and int(copies) > 1:
		args += ["-n", str(int(copies))]
	duplex = job.get("duplex")
	if duplex and duplex != "None":
		sides = "two-sided-long-edge" if duplex == "Long Edge" else "two-sided-short-edge"
		args += ["-o", f"sides={sides}"]
	color = job.get("color_mode")
	if color:
		args += ["-o", f"print-color-mode={'color' if color == 'Color' else 'monochrome'}"]
	if job.get("paper_size"):
		args += ["-o", f"media={job['paper_size']}"]
	if job.get("tray"):
		args += ["-o", f"InputSlot={job['tray']}"]
	if job.get("is_raw"):
		args += ["-o", "raw"]
	return args


def submit(printer, filepath, job):
	"""Submit the file to CUPS via `lp`; return the CUPS job id (e.g. 'CanonOffice-12')."""
	args = ["lp", "-d", printer] + build_lp_args(job) + [filepath]
	result = _run(args)
	if result.returncode != 0:
		raise RuntimeError(f"lp failed: {(result.stderr or result.stdout).strip() or 'unknown error'}")
	match = re.search(r"request id is (\S+)", result.stdout)
	return match.group(1) if match else None


def confirm_printed(printer, cups_job_id, timeout=_CONFIRM_TIMEOUT_SECONDS):
	"""Poll CUPS until the job completes; raise if it aborts or never confirms.

	`lp` only queues the job and returns immediately, so without this a job CUPS
	later aborts (printer offline, unsupported format, bad driver) would look
	Completed. Mirrors the cups_direct verification.
	"""
	if not cups_job_id:
		return  # couldn't parse an id; trust the submit
	deadline = time.monotonic() + timeout
	while True:
		if cups_job_id not in _job_ids(["lpstat", "-W", "not-completed", "-o", printer]):
			# Left the pending queue: it either completed or was aborted/canceled.
			if cups_job_id in _job_ids(["lpstat", "-W", "completed", "-o", printer]):
				return
			# If the queue went offline, the job should wait (release), not fail.
			if not is_online(printer):
				raise PrinterOfflineError(
					f"CUPS queue '{printer}' went offline during print; releasing job to wait."
				)
			raise RuntimeError(
				f"CUPS job {cups_job_id} on '{printer}' did not print "
				"(aborted/canceled). Check the printer is on and the driver is correct."
			)
		if time.monotonic() > deadline:
			if not is_online(printer):
				raise PrinterOfflineError(
					f"CUPS queue '{printer}' offline; job {cups_job_id} not confirmed, releasing to wait."
				)
			raise RuntimeError(
				f"CUPS job {cups_job_id} on '{printer}' was not confirmed printed "
				f"within {timeout}s. The printer may be paused or unreachable."
			)
		time.sleep(_POLL_INTERVAL_SECONDS)


def _job_ids(args):
	result = _run(args)
	ids = []
	for line in result.stdout.splitlines():
		parts = line.split()
		if parts:
			ids.append(parts[0])
	return ids
