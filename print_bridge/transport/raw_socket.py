"""Raw socket transport — sends bytes directly to a printer socket (port 9100)."""

import socket

import frappe

from print_bridge.transport.base import BaseTransport


class RawSocketTransport(BaseTransport):
	def deliver(self, job_doc, file_content: bytes) -> None:
		printer_doc = frappe.get_doc("Print Bridge Printer", job_doc.target_printer)
		uri = printer_doc.printer_uri or ""

		host, port = self._parse_uri(uri)
		with socket.create_connection((host, port), timeout=10) as sock:
			sock.sendall(file_content)

	def _parse_uri(self, uri: str):
		uri = uri.replace("socket://", "")
		if ":" in uri:
			host, port_str = uri.rsplit(":", 1)
			return host.strip(), int(port_str.strip())
		return uri.strip(), 9100

	def supports_raw(self) -> bool:
		return True

	def completes_synchronously(self) -> bool:
		return True
