"""HTTP client for the bench-side agent endpoints (`print_bridge.api.agent`).

Every call authenticates with the `X-Agent-Token` header — no Frappe login or
cookie is used, so there is nothing to keep in sync and CSRF does not apply.
Whitelisted Frappe methods return their value wrapped as ``{"message": ...}``;
``download_job_file`` instead streams the raw file bytes.
"""

import json

import requests

_BASE_PATH = "/api/method/print_bridge.api.agent."


class AgentClient:
	def __init__(self, base_url, token, timeout=30):
		self.base_url = base_url.rstrip("/")
		self.token = token
		self.timeout = timeout
		self.session = requests.Session()
		self.session.headers.update({"X-Agent-Token": token})

	def _url(self, method):
		return f"{self.base_url}{_BASE_PATH}{method}"

	def _post(self, method, **params):
		# requests drops keys whose value is None, so optional params just vanish.
		resp = self.session.post(self._url(method), data=params, timeout=self.timeout)
		resp.raise_for_status()
		return resp.json().get("message")

	def _get(self, method, **params):
		resp = self.session.get(self._url(method), params=params, timeout=self.timeout)
		resp.raise_for_status()
		return resp.json().get("message")

	# ── endpoints ────────────────────────────────────────────────────────────
	def register(self, agent_id, display_name=None, location=None, version=None):
		return self._post(
			"register",
			agent_id=agent_id,
			display_name=display_name,
			location=location,
			version=version,
		)

	def heartbeat(self, version=None, printer_statuses=None):
		return self._post(
			"heartbeat",
			version=version,
			printer_statuses=json.dumps(printer_statuses or {}),
		)

	def poll_jobs(self):
		return self._get("poll_jobs")

	def update_job_status(self, job_name, status, error=None):
		return self._post("update_job_status", job_name=job_name, status=status, error=error)

	def sync_printers(self, printers):
		return self._post("sync_printers", printers=json.dumps(printers))

	def download_job_file(self, job_name):
		"""Stream a job's rendered file. Built from base_url (not the job's
		file_url) so it is robust against a mis-set site host_name."""
		resp = self.session.get(
			self._url("download_job_file"),
			params={"job_name": job_name},
			timeout=self.timeout,
		)
		resp.raise_for_status()
		return resp.content
