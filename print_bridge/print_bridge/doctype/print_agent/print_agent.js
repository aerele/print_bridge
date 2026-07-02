// Copyright (c) 2026, Aerele Technologies and contributors
// For license information, please see license.txt

// Client script for the Print Agent form — adds token management buttons.

frappe.ui.form.on("Print Agent", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(
			frm.doc.token_hash ? __("Regenerate Token") : __("Generate Token"),
			() => print_bridge_generate_token(frm)
		);

		if (frm.doc.token_hash) {
			frm.add_custom_button(__("Revoke Token"), () => print_bridge_revoke_token(frm));
		}
	},
});

function print_bridge_generate_token(frm) {
	const proceed = () => {
		frm.call("generate_token").then((r) => {
			if (!r.message) return;
			frappe.msgprint({
				title: __("Agent Token"),
				indicator: "orange",
				message: __(
					"Copy this token now — it is shown only once and cannot be retrieved again.<br><br><b>{0}</b><br><br>Paste it into the agent configuration on the office machine.",
					[frappe.utils.escape_html(r.message)]
				),
			});
			frm.reload_doc();
		});
	};

	if (frm.doc.token_hash) {
		frappe.confirm(
			__(
				"This will invalidate the current token. Any running agent using it will stop working until you update it. Continue?"
			),
			proceed
		);
	} else {
		proceed();
	}
}

function print_bridge_revoke_token(frm) {
	frappe.confirm(
		__(
			"Revoke the current token? The agent will be rejected on its next request until a new token is generated."
		),
		() => {
			frm.call("revoke_token").then(() => {
				frappe.show_alert({ message: __("Token revoked"), indicator: "red" });
				frm.reload_doc();
			});
		}
	);
}
