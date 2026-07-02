"""Base class for all transport drivers."""

from abc import ABC, abstractmethod


class BaseTransport(ABC):
	@abstractmethod
	def deliver(self, job_doc, file_content: bytes) -> None:
		"""Deliver rendered bytes to the printer.

		Raise an exception on failure — the caller will catch and set the job status.
		"""
		...

	def supports_raw(self) -> bool:
		return False

	def completes_synchronously(self) -> bool:
		"""Whether deliver() prints inline so the job is finished when it returns.

		Direct server-side transports (cups_direct, raw_socket, cloud_ipp) return
		True, so the caller marks the job Completed. Handoff transports
		(agent, browser_qz) return False — they move the job to Ready and something
		else (the agent report-back, or the browser) finishes it later.
		"""
		return False
