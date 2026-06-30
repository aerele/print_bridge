app_name = "print_bridge"
app_title = "Print Bridge"
app_publisher = "Aerele Technologies"
app_description = "Seamless printing layer for Frappe / ERPNext — agent-based, cloud-compatible."
app_email = "hello@aerele.in"
app_license = "mit"

required_apps = ["frappe"]

# ── Desk app entry ────────────────────────────────────────────────────────────
add_to_apps_screen = [
	{
		"name": "print_bridge",
		"title": "Print Bridge",
		"route": "/app/print-job",
	}
]

# ── JS / CSS injected into every Frappe Desk page ────────────────────────────
app_include_js = "/assets/print_bridge/js/print_bridge.js"

# ── Document events — auto-print on submit / workflow ────────────────────────
doc_events = {
	"*": {
		"on_submit": "print_bridge.events.on_submit",
		"on_update_after_submit": "print_bridge.events.on_workflow_state_change",
	}
}

# ── Scheduled tasks ──────────────────────────────────────────────────────────
scheduler_events = {
	"all": [
		"print_bridge.tasks.all"
	],
	"hourly": [
		"print_bridge.tasks.hourly"
	],
}

# ── Installation ──────────────────────────────────────────────────────────────
after_install = "print_bridge.install.after_install"

# ── Log TTL (Print Job audit records kept for 90 days by default) ─────────────
default_log_clearing_doctypes = {
	"Print Job": 90
}
