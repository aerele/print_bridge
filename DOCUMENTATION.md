# Print Bridge — Complete User & Administrator Guide

**Version:** 0.1 (v16 compatible)
**Publisher:** Aerele Technologies
**License:** MIT

---

## Table of Contents

1. [What is Print Bridge?](#1-what-is-print-bridge)
2. [How It Works — The Big Picture](#2-how-it-works--the-big-picture)
3. [Installation](#3-installation)
4. [First-Time Setup](#4-first-time-setup)
   - 4.1 [Configure Global Settings](#41-configure-global-settings)
   - 4.2 [Create a Print Agent (for cloud / hosted sites)](#42-create-a-print-agent-for-cloud--hosted-sites)
   - 4.3 [Register Printers](#43-register-printers)
   - 4.4 [Create Printer Groups (optional)](#44-create-printer-groups-optional)
5. [Mapping Print Formats to Printers](#5-mapping-print-formats-to-printers)
6. [Routing Rules (Advanced)](#6-routing-rules-advanced)
7. [Printing a Document](#7-printing-a-document)
   - 7.1 [Manual Print (one document)](#71-manual-print-one-document)
   - 7.2 [Batch Print from List View](#72-batch-print-from-list-view)
   - 7.3 [Auto Print on Submit](#73-auto-print-on-submit)
   - 7.4 [Auto Print on Workflow State](#74-auto-print-on-workflow-state)
8. [Managing Print Jobs (the Spool)](#8-managing-print-jobs-the-spool)
9. [Transport Drivers Explained](#9-transport-drivers-explained)
   - 9.1 [agent — for cloud / hosted benches](#91-agent--for-cloud--hosted-benches)
   - 9.2 [cups\_direct — for self-hosted LAN benches](#92-cups_direct--for-self-hosted-lan-benches)
   - 9.3 [raw\_socket — for thermal / label printers](#93-raw_socket--for-thermal--label-printers)
   - 9.4 [cloud\_ipp — for IPP-Everywhere printers](#94-cloud_ipp--for-ipp-everywhere-printers)
   - 9.5 [browser\_qz — for USB / desk printers](#95-browser_qz--for-usb--desk-printers)
10. [Configuration Resolution — How the App Picks a Printer](#10-configuration-resolution--how-the-app-picks-a-printer)
11. [Roles and Permissions](#11-roles-and-permissions)
12. [Monitoring and Troubleshooting](#12-monitoring-and-troubleshooting)
13. [Migrating from Network Printer Settings](#13-migrating-from-network-printer-settings)
14. [Reference — All DocTypes](#14-reference--all-doctypes)
15. [Reference — All API Endpoints](#15-reference--all-api-endpoints)
16. [FAQ](#16-faq)

---

## 1. What is Print Bridge?

Print Bridge is a Frappe/ERPNext app that gives you **reliable, configurable printing from anywhere** — including Frappe Cloud and any hosted bench behind a router or CGNAT.

**The core problem it solves:**
Frappe's built-in `Network Printer Settings` sends print jobs directly from the server to a printer. This only works if the server can reach the printer over the network. On Frappe Cloud, Hetzner, or any hosted bench, the server is in a data centre and your printers are in your office — the server can't reach them.

**How Print Bridge fixes it:**
A small daemon (the **Print Agent**) runs inside your office. It dials *out* to your bench over HTTPS (port 443, like a browser). The server never needs to reach the printer. No static IP, no port forwarding, no VPN needed.

**What you get on top:**
- Per-print-format printer mapping with duplex, color, tray, and copies settings
- A layered config hierarchy (global → format → role → user)
- Rule-based routing (e.g. "Sales Invoices for Company A → Accounts Laser")
- A Print Job queue (spool) with reprint, hold/release, and retry
- Auto-print on submit or workflow state change
- Batch print from any list view
- Raw ESC/POS and ZPL support for thermal and label printers

---

## 2. How It Works — The Big Picture

```
  Your Office (behind NAT / CGNAT)         Frappe Bench (Cloud or Hetzner)
 ┌─────────────────────────────────┐       ┌──────────────────────────────┐
 │  Print Agent (daemon)           │  HTTPS │  print_bridge app            │
 │  • dials out to bench on :443   │◄──────►│  • Print Job spool           │
 │  • polls for queued jobs        │outbound│  • Resolver / config lookup  │
 │  • pulls rendered PDF           │  only  │  • RQ render workers         │
 │  • prints via local CUPS        │        │  • Realtime status push      │
 └────────────┬────────────────────┘        └──────────────────────────────┘
              │ local network
              ▼
         Office Printers
```

**Flow for every print:**
1. User clicks **Print via Bridge** (or a document auto-triggers on submit)
2. A `Print Job` record is created with status `Queued`
3. An RQ background worker renders the document to PDF (or raw bytes)
4. The rendered file is saved as a private attachment
5. The transport driver delivers it:
   - **agent** → file sits as `Ready`; the office daemon polls, downloads, and spools to local CUPS
   - **cups\_direct / raw\_socket / cloud\_ipp** → server delivers directly
   - **browser\_qz** → a realtime event opens the PDF in the user's browser
6. Status flows back to `Completed` (or `Failed` with an error message)
7. A toast notification appears on the user's screen

---

## 3. Installation

### Prerequisites

- Frappe v16 bench
- Python 3.10+
- Redis and RQ workers running (`bench start` or a production setup)
- A working PDF engine for non-raw print formats. Print Bridge renders via
  `frappe.get_print` and **defaults to the `chrome` generator** (Google Chrome /
  Chromium must be installed on the bench server). A Print Format that explicitly
  sets its **PDF Generator** field to `wkhtmltopdf` is honored when that binary is
  installed; if `wkhtmltopdf` is not on the server, Print Bridge automatically
  falls back to `chrome` so rendering still succeeds.

### Install the app

```bash
# From your bench directory
bench get-app print_bridge https://github.com/aerele/print_bridge
bench --site <your-site> install-app print_bridge
bench --site <your-site> migrate
bench build --app print_bridge
```

> **Frappe Cloud:** Use the Marketplace or contact your site admin to install apps.

### What happens on install

- A `Print Manager` role is created
- A default `Print Bridge Settings` record is created
- If you previously used `Network Printer Settings`, see [Section 13](#13-migrating-from-network-printer-settings)

---

## 4. First-Time Setup

### 4.1 Configure Global Settings

Go to: **Print Bridge > Print Bridge Settings**

| Field | Description | Default |
|---|---|---|
| Default Transport | Which driver to use when no printer-specific transport is set | `agent` |
| Render Timeout (seconds) | How long the PDF renderer may run before being killed | `30` |
| Job TTL (hours) | Jobs older than this are marked `Expired` and will not print | `24` |
| Max Retry Attempts | How many times a failed job is automatically retried | `3` |
| Migrate Network Printer Settings | Import existing printers from the old doctype on next migrate | Off |

For most sites the defaults are fine. Change **Default Transport** to `cups_direct` if your bench server is on the same LAN as your printers.

---

### 4.2 Create a Print Agent (for cloud / hosted sites)

A **Print Agent** is the office-side daemon that bridges your cloud bench to your LAN printers. You need one per office (or one per isolated printer group for HA).

**Step 1 — Create the agent record in Frappe Desk**

Go to: **Print Bridge > Print Agent > New**

Fill in:
- **Agent ID** — auto-generated, leave as is
- **Display Name** — e.g. `Bangalore Office Agent`
- **Location** — e.g. `Bangalore HQ`

Save the record.

**Step 2 — Generate a token**

Click the **Generate Token** button on the saved record.

> A plain-text token is shown **once**. Copy it immediately — it cannot be retrieved again. The app stores only the SHA-256 hash.

**Step 3 — Install the agent on an office machine**

The agent is a small daemon (source: `agent/` in this repo, package name
`print-bridge-agent`). It talks to CUPS through the standard `lp`/`lpstat`
commands — **no pycups build required**. It needs to run on a machine that:
- Is always on (PC, Raspberry Pi, NAS, mini-PC, or a container)
- Is on the same local network as your printers, with CUPS client tools
  installed and the printer added to CUPS with a working driver
  (verify: `lpstat -e` and `echo hi | lp -d <queue>`)
- Can reach the internet on port 443

```bash
# Docker (recommended)
#   CUPS_SERVER points lp at the LAN CUPS server (host IP); or use --network host.
docker run -d --restart=always \
  -e BENCH_URL=https://your-site.frappe.cloud \
  -e AGENT_TOKEN=<paste-token-here> \
  -e CUPS_SERVER=192.168.1.10 \
  aerele/print-bridge-agent:latest

# Or with pip (Python 3.8+)
pip install print-bridge-agent
print-bridge-agent start \
  --url https://your-site.frappe.cloud \
  --token <paste-token-here>

# Or as a systemd service — see agent/README.md for the unit file and all options.
```

**Step 4 — Verify**

Back in Frappe, refresh the `Print Agent` record. Within 30 seconds:
- `Status` should change to `Online`
- `Last Heartbeat` should update
- `Version` should show the agent's version

If the agent discovered local CUPS printers automatically, they appear in **Print Bridge Printer** with `Transport = agent`.

---

### 4.3 Register Printers

Go to: **Print Bridge > Print Bridge Printer**

Printers can be added:
- **Automatically** — by the agent's printer discovery (push from the agent to `sync_printers`)
- **Manually** — click **New** and fill in the form

#### Manual printer form fields

| Field | Description |
|---|---|
| **Printer Name** | Internal unique ID (becomes the document name) |
| **Display Name** | Human-readable label shown in dialogs |
| **Transport** | See [Section 9](#9-transport-drivers-explained) |
| **Agent** | Link to Print Agent (only for `agent` transport) |
| **Printer URI** | Connection address for `cups_direct`, `raw_socket`, `cloud_ipp` |
| **Company / Branch** | Scope this printer to a company or cost center |
| **Capabilities** | Color, duplex, media sizes, trays — used to validate options |
| **Raw / Thermal Capable** | Enable for ESC/POS or ZPL printers |

#### Printer URI formats by transport

| Transport | URI format | Example |
|---|---|---|
| `cups_direct` | CUPS printer name | `HP_LaserJet_M404` |
| `raw_socket` | `socket://host:port` | `socket://192.168.1.50:9100` |
| `cloud_ipp` | `ipp://hostname/ipp/print` | `ipp://printer.example.com/ipp/print` |
| `agent` | (no URI needed — agent handles routing) | — |
| `browser_qz` | (no URI needed — browser handles it) | — |

---

### 4.4 Create Printer Groups (optional)

Groups let you route jobs to a pool of printers with automatic failover if one goes offline.

Go to: **Print Bridge > Printer Group > New**

| Field | Description |
|---|---|
| **Group Name** | e.g. `Accounts Lasers` |
| **Failover Strategy** | `Priority` — use the lowest-priority-number printer that is Online. `Round Robin` — distribute jobs across online printers. |
| **Members** (table) | Add printers with priority numbers (1 = highest priority) |

In the Members child table:
- **Printer** — link to a `Print Bridge Printer`
- **Priority** — lower number = tried first (Priority strategy only)
- **Active** — uncheck to temporarily exclude a printer without deleting it

---

## 5. Mapping Print Formats to Printers

This is the core configuration step. You tell the system: *"When someone prints this format, use this printer with these settings."*

Go to: **Print Bridge > Print Format Print Setting > New**

### Key fields

| Field | Description |
|---|---|
| **Print Format** | The Frappe Print Format to configure (e.g. `Standard Sales Invoice`) |
| **Action** | `Download PDF` (default — no change to current behavior), `Print Directly`, or `Preview then Print` |
| **User / Role / Company** | Scope — leave blank to apply to everyone. Fill in to narrow scope. |
| **Printer** | Direct link to a specific printer |
| **Printer Group** | Link to a printer group (use one or the other, not both) |
| **Copies** | Static copy count |
| **Copies from Field** | Field name on the document to read copy count from (e.g. `qty` on a Delivery Note) |
| **Duplex** | `None`, `Long Edge`, or `Short Edge` |
| **Color Mode** | `Color` or `Monochrome` |
| **Paper Size** | `A4`, `A5`, `Letter`, `Legal`, or `Custom` |
| **Tray** | Tray name as known to the printer (e.g. `Tray2`) |
| **Raw / Thermal** | Enable for ESC/POS / ZPL print formats |
| **Auto Print On** | `Off`, `On Submit`, or `On Workflow State` |
| **Workflow State** | Which state triggers auto-print (only when Auto Print On = `On Workflow State`) |

### Scope examples

| Goal | Set User | Set Role | Set Company |
|---|---|---|---|
| Default for everyone | (blank) | (blank) | (blank) |
| Different printer for Accounts team | (blank) | `Accounts User` | (blank) |
| One user always prints to their desk printer | `john@example.com` | (blank) | (blank) |
| Company A uses a different printer than Company B | (blank) | (blank) | `Company A` |

> **Multiple records for the same format are fine.** The resolver picks the most specific one. A record with a user set beats one with only a role; a record with user + company beats everything except an explicit pick at print time.

---

## 6. Routing Rules (Advanced)

Routing Rules give you SQL-WHERE-style control over printer selection based on document context. They are evaluated before Print Format Print Settings when both are configured.

Go to: **Print Bridge > Print Routing Rule > New**

### Match conditions (all are optional — only filled ones are checked)

| Field | What it matches |
|---|---|
| **DocType** | Only match documents of this type |
| **Print Format** | Only match this specific print format |
| **Company** | Document's company field value |
| **Branch / Cost Center** | Document's cost_center field value |
| **Warehouse** | Document's warehouse field value |
| **User** | The user who clicked Print |
| **Role** | Any of the user's roles |
| **Field Name + Operator + Value** | A field condition on the document (e.g. `total > 10000`) |

### Target (pick one)

| Field | Description |
|---|---|
| **Printer** | Send matching jobs directly to this printer |
| **Printer Group** | Send matching jobs to this group (failover applies) |

### Priority

Rules are evaluated in **ascending priority order** (lowest number = evaluated first). The first matching rule wins.

### Examples

| Priority | DocType | Company | Field | Operator | Value | Target |
|---|---|---|---|---|---|---|
| 10 | Sales Invoice | Aerele Technologies | | | | Accounts Laser (Group) |
| 20 | Delivery Note | | warehouse | = | Main Warehouse | Warehouse Laser |
| 30 | | | | | | (any format flagged is_raw → Zebra Labels) |

---

## 7. Printing a Document

### 7.1 Manual Print (one document)

1. Open any printable document in Frappe Desk
2. Click **Actions → Print via Bridge**
3. A dialog opens pre-filled with the resolved settings for this format and user
4. Adjust **Print Format**, **Printer**, **Copies**, **Duplex**, **Color Mode**, **Paper Size** if needed
5. Click **Print**
6. A toast notification confirms the job was queued
7. When the job completes (or fails), a second toast appears

> If the action resolved to `Download PDF` (the default when no printer is configured), the dialog still appears and lets you override to a printer.

---

### 7.2 Batch Print from List View

1. Go to any list view (e.g. Sales Invoice list)
2. Check the boxes next to the documents you want to print
3. Click **Actions → Print via Bridge**
4. A dialog asks for Print Format and Printer
5. Click **Print All**
6. Each document is enqueued as a separate Print Job — one bad document does not block the rest

---

### 7.3 Auto Print on Submit

Configure a `Print Format Print Setting` with **Auto Print On = On Submit**.

When any user submits a document whose type matches the print format's `doc_type`, the system automatically enqueues a print job. No user interaction needed.

**Example use case:** Every time a Sales Invoice is submitted, one copy automatically goes to the Accounts printer.

---

### 7.4 Auto Print on Workflow State

Configure a `Print Format Print Setting` with:
- **Auto Print On = On Workflow State**
- **Workflow State** = the exact state name that triggers printing (e.g. `Approved`)

When a document transitions into that workflow state, printing is triggered automatically.

**Example use case:** When a Purchase Order reaches `Approved` state, a copy goes to the procurement printer.

---

## 8. Managing Print Jobs (the Spool)

Every print request creates a **Print Job** record. This is your audit log and your control panel for retrying or holding jobs.

Go to: **Print Bridge > Print Job**

### Statuses

| Status | Meaning |
|---|---|
| `Queued` | Job created, waiting for an RQ worker to pick it up |
| `Rendering` | Worker is generating the PDF / raw bytes |
| `Ready` | Rendered file is ready; waiting for agent to pull (agent transport) or browser event sent |
| `Printing` | Agent has downloaded the file and is sending it to the printer |
| `Completed` | Printer confirmed success |
| `Failed` | All retry attempts exhausted; check the Error Message field |
| `Held` | Manually paused — will not be dispatched until released |
| `Expired` | Job was queued too long (older than TTL); it will not print |
| `Cancelled` | Manually cancelled by a user |

### Actions on a Print Job

| Action | Available when | What it does |
|---|---|---|
| **Reprint** | Any status | Creates a brand-new Print Job for the same document with the same settings |
| **Hold** | Queued or Ready | Pauses the job so it will not be dispatched to the printer |
| **Release** | Held | Resumes the job — re-queues it for dispatch |
| **Cancel** | Any except Completed or Cancelled | Marks the job Cancelled so it is never printed |

> Use **Hold** when a printer is being serviced. When the printer is back, **Release** all held jobs.

---

## 9. Transport Drivers Explained

### 9.1 `agent` — for cloud / hosted benches

**When to use:** Your bench is on Frappe Cloud, Hetzner, or any server that cannot reach your office printers directly. This is the default and the most common setup.

**How it works:**
- The bench renders the PDF and marks the job `Ready`
- The Print Agent inside your office polls the bench every few seconds
- It finds the `Ready` job and downloads the PDF from a token-authenticated
  endpoint (`download_job_file`), sending its `X-Agent-Token` header — the file
  itself stays private and is never exposed by a public URL
- It sends the file to the local CUPS queue
- It reports `Completed` or `Failed` back to the bench

**Requirements:**
- One always-on machine in the office running the Print Agent daemon
- Outbound internet access on port 443 from that machine

---

### 9.2 `cups_direct` — for self-hosted LAN benches

**When to use:** Your Frappe bench server is on the same LAN as your printers (common in on-premise setups).

**How it works:** The bench server connects to the local CUPS daemon and submits the job directly using `pycups`. After submitting, it **polls the CUPS job state** and only marks the Print Job `Completed` once CUPS reports the job actually printed (`completed`). If CUPS aborts or cancels the job — or it is not confirmed within 60 seconds (printer offline, paused, wrong/missing driver) — the Print Job is marked `Failed` with the CUPS reason, instead of a false `Completed`.

**Requirements:**
- `pycups` Python package, installed **into the bench's virtualenv**: `./env/bin/pip install pycups` (needs `libcups2-dev` to compile)
- CUPS installed and running on the bench server
- Printer configured in CUPS on the bench server **with a working driver** — a queue that only "accepts" jobs but cannot actually drive the device (e.g. a budget inkjet set up with driverless IPP it does not truly support) will show `Failed`, not `Completed`
- Prefer a fixed-IP device URI (`ipp://<ip>/ipp/print` or `socket://<ip>:9100`) over an mDNS `dnssd://…local` name, which fails to resolve whenever the printer sleeps

**Printer URI:** Use the CUPS printer name (visible in `lpstat -p`)

---

### 9.3 `raw_socket` — for thermal / label printers

**When to use:** ESC/POS receipt printers or Zebra/SATO label printers that accept raw bytes on port 9100.

**How it works:** The bench opens a TCP socket to the printer's IP and port and sends the raw bytes directly.

**Requirements:**
- Bench server can reach the printer's IP (same LAN, or via agent if remote)
- Print format must be a raw template that emits ESC/POS or ZPL
- Enable **Raw / Thermal Capable** and **Raw / Thermal** on the print setting

**Printer URI:** `socket://192.168.1.50:9100`

---

### 9.4 `cloud_ipp` — for IPP-Everywhere printers

**When to use:** Modern printers that expose an internet-reachable IPP endpoint (vendor cloud print services, or printers with a public IP).

**How it works:** Uses `pycups` to submit a job to the printer's IPP URI directly from the bench server.

**Requirements:**
- `pycups` installed
- Printer URI in IPP format: `ipp://hostname/ipp/print` or `ipps://...`

---

### 9.5 `browser_qz` — for USB / desk printers

**When to use:** A user wants to print to their own USB-connected or local desk printer without any server route. The QZ Tray application on the user's machine intercepts the job.

**How it works:**
- Bench renders the PDF and marks job `Ready`
- A Frappe realtime event is pushed to the requesting user's browser session
- The browser opens the rendered PDF in a new tab
- If QZ Tray is installed, it silently prints; otherwise the browser print dialog appears

**Requirements:**
- No server-side printer config needed
- For silent printing: [QZ Tray](https://qz.io/) installed on the user's machine (optional)

---

## 10. Configuration Resolution — How the App Picks a Printer

When you click **Print via Bridge** without manually selecting a printer, the app walks this hierarchy and uses the first match:

```
1. Explicit pick in the print dialog (highest priority — always wins)
          ▼
2. Routing Rules (evaluated by priority ASC — first match wins)
          ▼
3. Print Format Print Setting — user + format match (score 8+)
          ▼
4. Print Format Print Setting — role match (score 4)
          ▼
5. Print Format Print Setting — company match (score 2)
          ▼
6. Print Format Print Setting — format-only (no scope, score 0)
          ▼
7. Global default (Print Bridge Settings — default transport only, no specific printer)
          ▼
Error: "Could not resolve a printer — please configure a Print Format Print Setting"
```

**What this means in practice:**

- A small site configures one Print Format Print Setting per format → everyone uses those settings
- A user who has their own setting for that format gets their setting instead
- Power users layer routing rules on top for document-context routing (by company, warehouse, etc.)

---

## 11. Roles and Permissions

| Role | What they can do |
|---|---|
| **System Manager** | Full access to all Print Bridge records and settings |
| **Print Manager** | Read/write access to Printers, Printer Groups, Routing Rules, Print Format Settings; read Print Jobs |
| **All (any logged-in user)** | Create and read their own Print Jobs |

> Assign the `Print Manager` role to office admins or IT staff who manage printers without needing full System Manager access.

---

## 12. Monitoring and Troubleshooting

### Checking agent health

Go to **Print Bridge > Print Agent**.

| Field | What to check |
|---|---|
| Status | Should be `Online` if the agent is running |
| Last Heartbeat | Should be within the last 2–3 minutes |
| Version | Check it matches the latest release |

If status is `Offline`:
1. SSH into the agent machine and check the agent process / container logs
2. Confirm outbound HTTPS (port 443) is not blocked by a firewall
3. Check the agent token has not been revoked

### Checking printer health

Go to **Print Bridge > Print Bridge Printer**.

| Status | Meaning |
|---|---|
| `Online` | Agent confirmed it is reachable and accepting jobs |
| `Offline` | Agent reported the printer is unreachable |
| `Error` | Last job to this printer failed at the driver level |
| `Unknown` | No status update received yet |

### Checking a failed job

Go to **Print Bridge > Print Job**, open the failed job.

- Read the **Error Message** field — it contains the Python traceback or driver error
- Check **Attempts** — if it equals Max Retry Attempts, the job gave up
- Click **Reprint** to try again after fixing the underlying issue

### Common errors and fixes

| Error | Likely cause | Fix |
|---|---|---|
| `Could not resolve a printer` | No Print Format Print Setting or Routing Rule matches this format/user | Create a Print Format Print Setting for this format |
| `pycups not installed` | cups_direct or cloud_ipp transport used without pycups | `pip install pycups` on the bench server |
| `No active printers in group` | Every member is unchecked (`Active` off) | Re-activate a member or add a printer to the group |
| `No online printers in group` | All active members are currently Offline | Bring a printer back online or add an online printer to the group |
| `Missing X-Agent-Token header` | Agent making API calls without a token | Regenerate the token and restart the agent |
| `Invalid agent token` | Token was revoked or entered incorrectly | Generate a new token from the Print Agent record |
| `Connection refused` on raw_socket | Wrong IP/port in Printer URI, or printer offline | Check printer IP and that it is on and connected |
| Job stuck in `Rendering` | wkhtmltopdf / Chromium crashed | Check Frappe error logs; increase Render Timeout in settings |
| `No wkhtmltopdf executable found` on render | A Print Format is set to the `wkhtmltopdf` generator but it is not installed | Install `wkhtmltopdf`, or set the Print Format's **PDF Generator** field to `chrome` (the app default) |
| Chrome / Chromium errors on render | Google Chrome / Chromium not installed on the bench server | Install Chrome/Chromium, or set the Print Format's **PDF Generator** to `wkhtmltopdf` and install that instead |
| Job stuck in `Ready` for agent | Agent is offline or not polling | Check agent status and logs |

### Scheduler and worker health

Print Bridge requires:
- At least one RQ worker on the `short` queue for rendering and dispatching
- The Frappe scheduler running for heartbeat checks and TTL expiry

```bash
# Check workers
bench worker --queue short &

# Check scheduler
bench schedule &

# Or in production, check your supervisor/systemd config
```

---

## 13. Migrating from Network Printer Settings

If you previously configured printers in Frappe's built-in **Network Printer Settings**:

1. Go to **Print Bridge > Print Bridge Settings**
2. Enable **Migrate Existing Network Printer Settings on Install**
3. Save and run `bench --site <site> migrate`

The migration:
- Reads every existing `Network Printer Settings` record
- Creates a corresponding `Print Bridge Printer` with transport `cups_direct` (if no server IP) or `raw_socket` (if a server IP was set)
- Does not delete the original records — you keep them as a backup
- Skips any printer name that already exists in the Print Bridge registry

After migration, review each imported printer and set the correct transport and URI.

---

## 14. Reference — All DocTypes

### Print Bridge Settings *(Single)*

Global configuration. One record for the entire site.

| Field | Type | Default | Description |
|---|---|---|---|
| default_transport | Select | `agent` | Fallback transport when no printer has an explicit transport |
| render_timeout | Int | `30` | Seconds before the PDF render worker is killed |
| job_ttl_hours | Int | `24` | Jobs older than this many hours are expired |
| max_retry_attempts | Int | `3` | Retry count before a job is permanently marked Failed |
| migrate_network_printer_settings | Check | Off | Import legacy printers on next migrate |

---

### Print Agent

One record per office agent daemon.

| Field | Description |
|---|---|
| agent_id | Auto-generated unique identifier |
| display_name | Human-readable name |
| status | `Registered` / `Online` / `Offline` |
| last_heartbeat | Timestamp of most recent ping from the agent |
| version | Agent software version |
| location | Office or site description |
| agent_url | Internal URL (optional, for diagnostics) |
| token_hash | SHA-256 hash of the agent's secret token |

**Buttons:**
- **Generate Token** — creates a new token and shows it once
- **Revoke Token** — immediately invalidates the current token

---

### Print Bridge Printer

One record per physical or logical printer.

| Field | Description |
|---|---|
| printer_name | Unique ID (used as the document name) |
| display_name | Shown in dialogs |
| transport | `agent` / `cups_direct` / `raw_socket` / `cloud_ipp` / `browser_qz` |
| agent | Link to Print Agent (agent transport only) |
| printer_uri | Connection address (non-agent transports) |
| status | `Online` / `Offline` / `Error` / `Unknown` |
| last_seen | Timestamp of last successful contact |
| company / branch | Scope to a company or cost center |
| supports_color | Capability flag |
| supports_duplex | Capability flag |
| supported_media_sizes | JSON list of supported paper sizes |
| supported_trays | JSON list of tray names |
| is_raw_capable | Can handle ESC/POS or ZPL |

---

### Printer Group

A named pool of printers with failover.

| Field | Description |
|---|---|
| group_name | Unique name |
| failover_strategy | `Priority` or `Round Robin` |
| members | Child table of Printer Group Member records |

**Printer Group Member (child table):**

| Field | Description |
|---|---|
| printer | Link to Print Bridge Printer |
| priority | Lower = tried first (Priority strategy) |
| is_active | Uncheck to temporarily exclude |

---

### Print Format Print Setting

Per-format print configuration with optional scope.

| Field | Description |
|---|---|
| print_format | The Print Format this setting applies to |
| action | `Download PDF` / `Print Directly` / `Preview then Print` |
| user / role / company | Scope (all optional; blank = applies to all) |
| printer / printer_group | Target (set one, not both) |
| copies | Static copy count |
| copies_from_field | Field name on the document to read copy count from |
| duplex | `None` / `Long Edge` / `Short Edge` |
| color_mode | `Color` / `Monochrome` |
| paper_size | `A4` / `A5` / `Letter` / `Legal` / `Custom` |
| tray | Printer tray name |
| is_raw | Enable raw byte path (ESC/POS, ZPL) |
| auto_print_on | `Off` / `On Submit` / `On Workflow State` |
| workflow_state | Trigger state (when auto_print_on = On Workflow State) |

---

### Print Routing Rule

Condition-based routing rule.

| Field | Description |
|---|---|
| priority | Evaluation order (lower = evaluated first) |
| is_active | Enable/disable without deleting |
| doctype_name | Match this DocType only |
| print_format | Match this Print Format only |
| company | Match documents where company = this |
| branch | Match documents where cost_center = this |
| warehouse | Match documents where warehouse = this |
| user | Match when this user prints |
| role | Match when the user has this role |
| field_condition_fieldname | Document field to evaluate |
| field_condition_operator | `=` / `!=` / `>` / `<` / `>=` / `<=` |
| field_condition_value | Value to compare against |
| printer / printer_group | Target when the rule matches |

---

### Print Job

The spool record — one per print request.

| Field | Description |
|---|---|
| name | Auto-numbered: `PJ-YYYY-NNNNN` |
| reference_doctype | The source document type |
| reference_name | The source document |
| print_format | Print format used |
| status | Current job status (see Section 8) |
| requested_by | User who triggered the print |
| requested_at | Timestamp |
| transport | Driver used |
| target_printer / target_printer_group | Where the job was sent |
| agent | Agent handling this job (if agent transport) |
| copies | How many copies |
| duplex / color_mode / paper_size / tray / is_raw | Print options |
| idempotency_key | Deterministic hash of (doctype, name, format, user, printer, copies) used to collapse accidental double-submits within a 120-second window |
| attempts | How many times rendering / delivery was tried |
| rendered_file | Private attachment containing the PDF/raw bytes |
| error_message | Full error traceback if status = Failed |

---

## 15. Reference — All API Endpoints

### User-facing endpoints

Base path: `/api/method/print_bridge.api.print_api.`

| Endpoint | Method | Parameters | Description |
|---|---|---|---|
| `enqueue_print_job` | POST | `reference_doctype`, `reference_name`, `print_format`, `printer`, `printer_group`, `copies`, `duplex`, `color_mode`, `paper_size`, `tray`, `is_raw`, `action`, `force` | Create and queue a print job. If no printer resolves and `action=Download PDF`, returns `{action: "download_pdf", url}` instead of erroring. Identical requests within 120s are deduped (returns the existing job with `status: "Duplicate"`); pass `force=1` to bypass (used by Reprint). |
| `get_print_settings_for_format` | GET | `print_format` (optional — falls back to the DocType's default format), `reference_doctype`, `reference_name` | Return resolved settings for the print dialog |
| `get_jobs` | GET | `reference_doctype`, `reference_name`, `limit` | List recent print jobs |
| `batch_print` | POST | `jobs` (JSON list of job params) | Enqueue multiple jobs |

### Agent-facing endpoints

Base path: `/api/method/print_bridge.api.agent.`

All require header: `X-Agent-Token: <your-token>`

| Endpoint | Method | Parameters | Description |
|---|---|---|---|
| `register` | POST | `agent_id`, `display_name`, `location`, `version` | Agent announces itself on startup |
| `heartbeat` | POST | `version`, `printer_statuses` (JSON) | Periodic keep-alive + status update |
| `poll_jobs` | GET | — | Fetch pending jobs for this agent's printers (each job includes a `file_url` pointing at `download_job_file`) |
| `download_job_file` | GET | `job_name` | Stream the rendered file for a job; only returns files for jobs that belong to the calling agent |
| `update_job_status` | POST | `job_name`, `status`, `error` | Report job outcome (rejected if the job does not belong to this agent) |
| `sync_printers` | POST | `printers` (JSON list) | Push discovered local printers into the registry |

---

## 16. FAQ

**Q: Does Print Bridge work on Frappe Cloud?**
Yes. It was specifically designed for Frappe Cloud. Use the `agent` transport — the office daemon dials out to your Frappe Cloud site, so no inbound firewall rules are needed.

**Q: My printer is not showing up after the agent starts.**
The agent auto-discovers printers via the local CUPS daemon. Make sure:
1. CUPS is installed and running on the agent machine
2. Your printers are added to CUPS (`http://localhost:631`)
3. The agent has permissions to list CUPS printers
Then check **Print Bridge > Print Bridge Printer** for new records.

**Q: Can I have two agents for high availability?**
Yes. Create two Print Agent records, install the agent daemon twice (on two machines), and add printers from both agents to the same Printer Group with `Round Robin` or `Priority` strategy.

**Q: What happens if the agent goes offline while jobs are queued?**
Jobs remain in `Queued` or `Ready` status. When the agent reconnects, it polls and picks them up. If a job's TTL expires while the agent is offline, it is marked `Expired` and will not print — this prevents stale documents printing hours later.

**Q: Can I use Print Bridge with raw ESC/POS / ZPL printers?**
Yes. Use `raw_socket` transport, set the Printer URI to `socket://IP:9100`, and enable **Raw / Thermal Capable** on the printer and **Raw / Thermal** on the Print Format Print Setting. Your print format's Jinja template must emit the raw command bytes directly.

**Q: How do I revoke an agent if a machine is stolen or compromised?**
Open **Print Bridge > Print Agent**, find the agent, and click **Revoke Token**. The agent's token hash is cleared immediately. All subsequent polling attempts by that agent will be rejected with `401 Unauthorized`. Generate a new token and paste it into a replacement agent.

**Q: Will installing Print Bridge break my existing print button?**
No. The default action is `Download PDF`, which is identical to the current Frappe behavior. Print Bridge adds a new **Print via Bridge** button alongside the existing one. Your users can continue using the old button; the new one is opt-in.

**Q: Can I print to multiple printers from one submit?**
Yes. Create multiple `Print Format Print Setting` records for the same print format, each with `Auto Print On = On Submit` and a different printer. The system will enqueue one job per matching setting.

**Q: Where are the rendered PDFs stored?**
As private Frappe file attachments on the `Print Job` record. They are not publicly accessible. The agent fetches them by calling the `download_job_file` endpoint with its `X-Agent-Token` header — the file is streamed only after the token is validated and the job is confirmed to belong to that agent.

**Q: How do I uninstall?**
```bash
bench --site <site> uninstall-app print_bridge
bench --site <site> migrate
```
Print Job records and printer configuration will be removed. The rendered file attachments remain in your Frappe file storage until you clean them manually.
