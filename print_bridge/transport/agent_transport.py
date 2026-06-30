"""Agent transport — jobs are queued to Ready status; the agent polls and pulls them."""
from print_bridge.transport.base import BaseTransport


class AgentTransport(BaseTransport):
	def deliver(self, job_doc, file_content: bytes) -> None:
		"""For agent transport, 'delivering' means marking the job Ready.

		The actual bytes go into the rendered_file field (already done by the renderer).
		The agent polls /api/method/print_bridge.api.agent.poll_jobs and pulls the file.
		"""
		job_doc.set_status("Ready")

	def supports_raw(self) -> bool:
		return True
