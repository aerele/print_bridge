"""Configuration resolution hierarchy (most-specific wins).

A Print Format Print Setting is scored by which scope fields it pins
(see _score_setting); higher score = more specific and wins:

  user match   -> +8
  role match   -> +4
  company match-> +2
  format-only  ->  0   (no scope set; applies to everyone)

Overall resolution order:
  1. Explicit pick passed at print time (handled in print_api.py)
  2. Routing Rules (resolve_via_routing_rules, by priority asc)
  3. Highest-scoring Print Format Print Setting (above)
  4. Global default (Print Bridge Settings)
"""

import frappe


def resolve_settings(print_format, reference_doctype=None, reference_name=None):
	"""Walk the hierarchy and return the most specific matching setting dict."""
	user = frappe.session.user
	user_roles = frappe.get_roles(user)
	company = None
	if reference_doctype and reference_name:
		company = frappe.db.get_value(reference_doctype, reference_name, "company")

	candidates = _get_candidates(print_format, user, user_roles, company)
	if candidates:
		best = candidates[0]
		return _setting_to_dict(best)

	return _global_defaults()


def resolve_via_routing_rules(reference_doctype, reference_name, print_format):
	"""Check Print Routing Rules in priority order. Return printer/group or None."""
	rules = frappe.db.get_all(
		"Print Routing Rule",
		filters={"is_active": 1},
		fields="*",
		order_by="priority asc",
	)

	doc_values = {}
	if reference_doctype and reference_name:
		try:
			doc = frappe.get_doc(reference_doctype, reference_name)
			doc_values = doc.as_dict()
		except Exception:
			pass

	user = frappe.session.user
	user_roles = set(frappe.get_roles(user))

	for rule in rules:
		if not _rule_matches(rule, reference_doctype, print_format, doc_values, user, user_roles):
			continue
		return {
			"printer": rule.printer,
			"printer_group": rule.printer_group,
		}
	return None


def _get_candidates(print_format, user, user_roles, company):
	"""Query Print Format Print Setting records ordered by specificity."""
	all_settings = frappe.db.get_all(
		"Print Format Print Setting",
		filters={"print_format": print_format},
		fields="*",
	)

	scored = []
	for s in all_settings:
		score = _score_setting(s, user, user_roles, company)
		if score is not None:
			scored.append((score, s))

	scored.sort(key=lambda x: -x[0])
	return [s for _, s in scored]


def _score_setting(s, user, user_roles, company):
	"""Return a specificity score (higher = more specific). None = doesn't match."""
	score = 0
	if s.user:
		if s.user != user:
			return None
		score += 8
	if s.role:
		if s.role not in user_roles:
			return None
		score += 4
	if s.company:
		if s.company != company:
			return None
		score += 2
	return score


def _rule_matches(rule, reference_doctype, print_format, doc_values, user, user_roles):
	if rule.doctype_name and rule.doctype_name != reference_doctype:
		return False
	if rule.print_format and rule.print_format != print_format:
		return False
	if rule.company and rule.company != doc_values.get("company"):
		return False
	if rule.branch and rule.branch != doc_values.get("cost_center"):
		return False
	if rule.warehouse and rule.warehouse != doc_values.get("warehouse"):
		return False
	if rule.user and rule.user != user:
		return False
	if rule.role and rule.role not in user_roles:
		return False
	if rule.field_condition_fieldname:
		field_val = str(doc_values.get(rule.field_condition_fieldname, ""))
		cond_val = str(rule.field_condition_value or "")
		op = rule.field_condition_operator or "="
		if not _eval_operator(field_val, op, cond_val):
			return False
	return True


def _eval_operator(a, op, b):
	try:
		a_num, b_num = float(a), float(b)
		if op == "=":
			return a_num == b_num
		if op == "!=":
			return a_num != b_num
		if op == ">":
			return a_num > b_num
		if op == "<":
			return a_num < b_num
		if op == ">=":
			return a_num >= b_num
		if op == "<=":
			return a_num <= b_num
	except (ValueError, TypeError):
		pass
	if op == "=":
		return a == b
	if op == "!=":
		return a != b
	return False


def _setting_to_dict(s):
	return {
		"action": s.get("action", "Download PDF"),
		"printer": s.get("printer"),
		"printer_group": s.get("printer_group"),
		"copies": s.get("copies", 1),
		"copies_from_field": s.get("copies_from_field"),
		"duplex": s.get("duplex"),
		"color_mode": s.get("color_mode"),
		"paper_size": s.get("paper_size"),
		"tray": s.get("tray"),
		"is_raw": s.get("is_raw", 0),
		"auto_print_on": s.get("auto_print_on", "Off"),
		"workflow_state": s.get("workflow_state"),
	}


def _global_defaults():
	settings = frappe.get_single("Print Bridge Settings")
	return {
		"action": settings.get("action") or "Download PDF",
		"printer": settings.get("printer"),
		"printer_group": settings.get("printer_group"),
		"copies": settings.get("copies") or 1,
		"duplex": settings.get("duplex"),
		"color_mode": settings.get("color_mode"),
		"paper_size": settings.get("paper_size"),
		"tray": settings.get("tray"),
		"is_raw": settings.get("is_raw") or 0,
		"auto_print_on": settings.get("auto_print_on") or "Off",
	}
