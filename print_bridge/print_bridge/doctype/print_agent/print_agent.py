import hashlib
import secrets

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class PrintAgent(Document):
	def before_insert(self):
		if not self.agent_id:
			self.agent_id = frappe.generate_hash(length=16)

	@frappe.whitelist()
	def generate_token(self):
		"""Generate a new plain-text token, store its hash, and return the token once."""
		token = secrets.token_urlsafe(32)
		self.token_hash = hashlib.sha256(token.encode()).hexdigest()
		self.save(ignore_permissions=True)
		return token

	@frappe.whitelist()
	def revoke_token(self):
		self.token_hash = ""
		self.status = "Offline"
		self.save(ignore_permissions=True)

	def update_heartbeat(self, version=None):
		self.last_heartbeat = now_datetime()
		self.status = "Online"
		if version:
			self.version = version
		self.save(ignore_permissions=True)
