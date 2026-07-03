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
     - 4.2.1 [Create the agent record and token](#421-create-the-agent-record-and-token)
     - 4.2.2 [Prepare the office machine](#422-prepare-the-office-machine)
     - 4.2.3 [Find your CUPS server (macOS / Ubuntu / Windows)](#423-find-your-cups-server-macos--ubuntu--windows)
     - 4.2.4 [Install and run with Docker](#424-install-and-run-with-docker)
     - 4.2.5 [Run and verify](#425-run-and-verify)
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
   - **agent** → file sits as `Ready`; the office daemon polls, downloads, and spools to local CUPS. If the machine or printer is offline the job simply waits in `Ready` until it returns (it is never failed or expired)
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
- **A working CUPS driver/queue for each physical printer** (only for the `agent`
  and `cups_direct` transports). Print Bridge hands the rendered file to CUPS and
  lets CUPS drive the printer, so the printer must already print from CUPS.
  Printers with **driverless IPP / IPP-Everywhere** need no extra driver; older
  ones (e.g. many Canon PIXMA like the E470) need a driver package such as
  `printer-driver-gutenprint` installed on the CUPS host. See §4.2.2.

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
| Job TTL (hours) | Jobs older than this are marked `Expired` and will not print (agent jobs *waiting* in `Ready` are exempt — they hold until the machine/printer returns) | `24` |
| Max Retry Attempts | How many times a failed job is automatically retried | `3` |
| Migrate Network Printer Settings | Import existing printers from the old doctype on next migrate | Off |

For most sites the defaults are fine. Change **Default Transport** to `cups_direct` if your bench server is on the same LAN as your printers.

---

### 4.2 Create a Print Agent (for cloud / hosted sites)

A **Print Agent** is the office-side daemon that bridges your cloud bench to your
LAN printers. You need one per office (or one per isolated printer group for HA).
It talks to CUPS through the standard `lp` / `lpstat` commands — **no pycups
build required** — and every connection is outbound-only (HTTPS/443), so no
static IP, port forwarding, or VPN is needed.

The agent lives in the `agent/` folder of this repo (Python package
`print-bridge-agent`). It ships as a **Docker** image you build locally from the
included `Dockerfile` — this guide uses Docker throughout, which bundles Python,
the agent, and the CUPS client so the only thing you install on the office
machine is Docker itself.

> Throughout, replace `<bench-url>` with your site (e.g.
> `https://your-site.frappe.cloud`, or `http://localhost:8000` for a local
> bench) and `<token>` with the token from step 4.2.1. `<bench>` means your bench
> directory, so the agent source is `<bench>/apps/print_bridge/agent`.

---

#### 4.2.1 Create the agent record and token

1. Go to **Print Bridge > Print Agent > New** and fill in:
   - **Agent ID** — auto-generated, leave as is
   - **Display Name** — e.g. `Bangalore Office Agent`
   - **Location** — e.g. `Bangalore HQ`
   Save the record.
2. Click **Generate Token** on the saved record.

> The plain-text token is shown **once**. Copy it immediately — it cannot be
> retrieved again. The app stores only its SHA-256 hash.

---

#### 4.2.2 Prepare the office machine

The agent runs in Docker, but it prints through a **CUPS server that runs on the
host** (or elsewhere on your LAN) — the container itself only carries the CUPS
*client*. So the office machine must be **always on**, on the **same LAN as your
printers**, able to reach the bench on port 443, and running a **CUPS server with
at least one printer**. The agent only ever prints to, and syncs, the queues that
CUPS reports.

> **The single most common cause of "no printers synced":** the host has no CUPS
> server (`cupsd`) running, or no printer added. Then `lpstat -e` returns nothing
> and the agent syncs **zero printers** even though it shows `Online`.

On Debian / Ubuntu (for macOS and Windows, see
[4.2.3](#423-find-your-cups-server-macos--ubuntu--windows)):

```bash
# Install the CUPS server (not just the client). printer-driver-cups-pdf adds a
# virtual "PDF" printer, handy for testing without physical hardware.
sudo apt install cups printer-driver-cups-pdf

# Make sure the CUPS daemon is running and starts on boot
sudo systemctl enable --now cups

# Let your user manage/print (log out and back in, or run `newgrp lpadmin`)
sudo usermod -aG lpadmin "$USER"
```

Add a printer — either a real one via the CUPS web UI at
**http://localhost:631 → Administration → Add Printer** (give it a working
driver), or rely on the virtual `PDF` queue from `cups-pdf` for testing. Then
verify a queue exists and prints:

```bash
lpstat -e                 # must list at least one queue, e.g. "PDF"
echo "hi" | lp -d PDF     # a test job (the PDF printer writes to ~/PDF/)
```

If `lpstat -e` prints nothing, stop and fix CUPS here first — the agent cannot
sync a printer that CUPS does not report.

---

#### 4.2.3 Find your CUPS server (macOS / Ubuntu / Windows)

The agent container carries only the CUPS *client*; it prints by talking to a
CUPS *server* somewhere on your network. The `CUPS_SERVER` environment variable
tells the container **which machine's CUPS to use**.

> **Format matters:** `CUPS_SERVER` must be `host[:port]` — e.g. `localhost:631`
> or `192.168.1.10:631`. It is **not** a URL: do **not** write
> `http://localhost:631` (a common mistake that leaves the agent unable to see
> any printers). Also note `--network host` works fully **only on Linux**; on
> Docker Desktop (macOS/Windows) use `host.docker.internal` instead.

Where CUPS lives on each OS, and what to pass:

| OS | Runs CUPS? | Where to find / enable it | `CUPS_SERVER` value |
|---|---|---|---|
| **Ubuntu / Linux** | Yes (`cupsd`) | Web UI `http://localhost:631`; **Settings → Printers**; list queues with `lpstat -e` | With `--network host`: **omit it** (defaults to `localhost:631`). From another host: `<machine-lan-ip>:631` |
| **macOS** | Yes (CUPS is built in) | Enable the web UI once with `cupsctl WebInterface=yes`, then `http://localhost:631`; **System Settings → Printers & Scanners** | Docker Desktop has no `--network host` → use `host.docker.internal:631` (CUPS on the Mac), or `<lan-ip>:631` for another box |
| **Windows** | **No** — Windows has no native CUPS | Windows uses its own print spooler, which the agent cannot drive | Run CUPS on a Linux/macOS machine on the LAN and point at it: `<cups-host-ip>:631` |

> **Windows note:** because Windows has no CUPS, you cannot print to a
> Windows-attached printer directly through the agent. Either run the agent (and
> CUPS) on a small Linux box / Raspberry Pi that shares the printer, or add the
> printer to a CUPS server on another machine and point `CUPS_SERVER` at it.

---

#### 4.2.4 Install and run with Docker

**Step 1 — Install Docker**

```bash
# Linux
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker run hello-world        # verify Docker works
```

On macOS / Windows, install **Docker Desktop** from docker.com instead, then run
`docker run hello-world` to verify.

**Step 2 — Build the image**

The image is not published to Docker Hub, so build it once from the included
`Dockerfile`:

```bash
cd <bench>/apps/print_bridge/agent
docker build -t print-bridge-agent .
```

**Step 3 — Run the container**

Pick the variant that matches your OS (see
[4.2.3](#423-find-your-cups-server-macos--ubuntu--windows) for how to choose the
`CUPS_SERVER` value):

**Linux — CUPS on the same machine** (use `--network host`, no `CUPS_SERVER`):

```bash
docker run -d --restart=always --name pbagent --network host \
  -e BENCH_URL=<bench-url> \
  -e AGENT_TOKEN=<token> \
  print-bridge-agent
```

**macOS / Windows, or CUPS on another host** (`--network host` is unavailable, so
name the server explicitly):

```bash
docker run -d --restart=always --name pbagent \
  -e BENCH_URL=<bench-url> \
  -e AGENT_TOKEN=<token> \
  -e CUPS_SERVER=host.docker.internal:631 \
  print-bridge-agent
```

What the flags mean:
- **`-d`** — run in the background (detached).
- **`--restart=always`** — bring the agent back after a crash or a reboot.
- **`--name pbagent`** — a memorable name for the commands below.
- **`-e BENCH_URL=` / `-e AGENT_TOKEN=`** — your site URL and the token from
  step 4.2.1.
- **`-e CUPS_SERVER=`** — the CUPS server as `host[:port]` (no `http://`). Omit
  it when using `--network host` on Linux; set it to `host.docker.internal:631`
  on Docker Desktop, or `<ip>:631` for CUPS on another machine.

> A local bench at `http://localhost:8000` is **not** reachable from inside a
> Docker Desktop container as `localhost` — use `http://host.docker.internal:8000`
> for `BENCH_URL` on macOS/Windows. On Linux with `--network host`, `localhost`
> works.

**Step 4 — Manage the container**

```bash
docker ps                    # is it running?
docker logs -f pbagent       # watch the agent's logs
docker restart pbagent       # restart (e.g. after adding a printer)
docker stop pbagent          # stop
docker rm pbagent            # remove
```

**Step 5 — Update to a newer agent**

```bash
cd <bench>/apps/print_bridge/agent
docker build -t print-bridge-agent .
docker stop pbagent && docker rm pbagent
# then re-run the `docker run ...` command from Step 3
```

---

#### 4.2.5 Run and verify

On startup the agent registers, discovers your local CUPS printers, and begins
polling. Watch its log with `docker logs -f pbagent` — you should see lines like:

```
print-bridge-agent v0.1.0 → <bench-url>
synced 1 local printer(s): PDF
```

> `synced 0 local printer(s): (none)` means the container reached no CUPS queues
> — check §4.2.2 (printer added?) and §4.2.3 (`CUPS_SERVER` format / networking).

Then, back in Frappe:

- **Print Bridge > Print Agent** — `Status` flips to `Online` and `Last
  Heartbeat` updates within ~30 seconds; `Version` shows the agent's version.
- **Print Bridge > Print Bridge Printer** — each discovered printer appears with
  `Transport = agent` and `Status = Online`.

Send a test print from any document; it should come out on the local printer.

> **Printer discovery/sync runs only at agent startup** — the periodic heartbeat
> only updates the *status* of printers it already knows. So if you add a printer
> to CUPS **after** the container started, run `docker restart pbagent` to sync it.

**Configuration environment variables** (all passed with `-e` on `docker run`):

| Flag | Env var | Default | Purpose |
|---|---|---|---|
| `--url` | `BENCH_URL` | — | Bench base URL (required) |
| `--token` | `AGENT_TOKEN` | — | Agent token (required) |
| `--interval` | `POLL_INTERVAL` | `5` | Seconds between polls |
| `--name` | `AGENT_NAME` | — | Optional display name |
| `--location` | `AGENT_LOCATION` | — | Optional location |
| `--agent-id` | `AGENT_ID` | — | Optional; enables the `register` call |
| `--log-level` | `LOG_LEVEL` | `INFO` | Logging level (`DEBUG` for verbose) |

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
| `Ready` | Rendered file is ready; waiting for agent to pull (agent transport) or browser event sent. **Agent jobs hold here indefinitely** until *both* the agent machine and the target printer are Online — see the note below |
| `Printing` | Agent has claimed the job and is sending it to the printer |
| `Completed` | Printer confirmed success |
| `Failed` | All retry attempts exhausted; check the Error Message field |
| `Held` | **Manually** paused — will not be dispatched until released. This is distinct from an agent job *waiting* in `Ready` (automatic) |
| `Expired` | Job was queued too long (older than TTL); it will not print. **Agent jobs waiting in `Ready` are exempt** and are never expired |
| `Cancelled` | Manually cancelled by a user |

> **Hold-until-available (agent transport).** If the office machine or the
> target printer is **off**, an agent job does **not** fail or expire — it stays
> in `Ready` and waits. `poll_jobs` only hands a job to the agent when the target
> printer's status is `Online`, so a job for an offline printer simply waits. The
> moment the next heartbeat marks the printer `Online` again (machine back up,
> printer powered on), the job is claimed and printed automatically. A job that
> was claimed (`Printing`) but whose agent then crashed is returned to `Ready` by
> a 15-minute lease reaper so it is not lost.

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
- The Print Agent inside your office polls the bench every few seconds, sending a
  heartbeat with the live status of each local printer just before it polls
- The bench hands out a `Ready` job **only when its target printer is `Online`**.
  If the printer (or the whole machine) is off, the job stays `Ready` and waits —
  it is never failed or expired (see *Hold-until-available* in Section 8)
- The agent downloads the PDF from a token-authenticated endpoint
  (`download_job_file`), sending its `X-Agent-Token` header — the file itself
  stays private and is never exposed by a public URL
- It sends the file to the local CUPS queue and confirms the job actually printed
- It reports `Completed` back to the bench. If it finds the printer went offline
  before or during printing, it **releases the job back to `Ready`** (to wait and
  reprint when the printer returns) instead of marking it `Failed`. A genuine
  error with the printer still online is reported as `Failed`

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
| Job waiting in `Ready` for agent | **Expected** if the machine or printer is off — the job is *held* and will print automatically when both are back `Online`. Only a problem if the Print Agent **and** the printer both already show `Online` | If both show `Online`, check the agent process/logs; otherwise no action needed — it is waiting by design |

### Agent (Docker) installation and setup errors

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent shows `Online` but `synced 0 local printer(s)` | The host CUPS has no printer queue, **or** `CUPS_SERVER` is malformed so the container reached no CUPS | Add a printer and confirm `lpstat -e` lists it (see [Section 4.2.2](#422-prepare-the-office-machine)); make sure `CUPS_SERVER` is `host[:port]` (see [Section 4.2.3](#423-find-your-cups-server-macos--ubuntu--windows)); then `docker restart pbagent` (sync runs only at startup) |
| Jobs stay `Ready`, never print; agent can't reach CUPS | Container isn't pointed at a reachable CUPS server | Linux: add `--network host` (and omit `CUPS_SERVER`); macOS/Windows: `-e CUPS_SERVER=host.docker.internal:631`; CUPS on another box: `-e CUPS_SERVER=<ip>:631` |
| `CUPS_SERVER=http://…` has no effect | libcups expects `host[:port]`, not a URL | Drop the `http://` scheme — e.g. `localhost:631` or `192.168.1.10:631` |
| Agent can't connect to the bench (`BENCH_URL`) | On Docker Desktop, `localhost` points at the container, not the host | Use `http://host.docker.internal:8000` for a local bench on macOS/Windows; on Linux use `--network host` so `localhost` works |
| Printer added but agent still doesn't see it | Discovery/sync happens only at startup | `docker restart pbagent` to re-sync |

### Scheduler and worker health

Print Bridge requires:
- At least one RQ worker on the `short` queue for rendering and dispatching
- The Frappe scheduler running for heartbeat checks, TTL expiry, and the
  stuck-`Printing` reclaim (a 15-minute lease returns a claimed job to `Ready` if
  its agent died mid-print, so it is retried instead of lost)

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
| `poll_jobs` | GET | — | Fetch pending jobs for this agent's printers **that are currently `Online`** (each job includes a `file_url` pointing at `download_job_file`); claiming a job moves it `Ready → Printing` |
| `download_job_file` | GET | `job_name` | Stream the rendered file for a job; only returns files for jobs that belong to the calling agent |
| `update_job_status` | POST | `job_name`, `status`, `error` | Report job outcome. Allowed values: `Completed`, `Failed`, or `Ready` (release a claimed job back to waiting — accepted only when the job is currently `Printing`). Rejected if the job does not belong to this agent |
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
The jobs **hold** in `Ready` and wait. When the agent reconnects (and the printer is back `Online`), it polls and picks them up automatically. Agent jobs waiting in `Ready` are **not** expired by the TTL — they wait indefinitely until the machine and printer return, so nothing is silently dropped during an outage. (The TTL still applies to jobs genuinely stuck in `Queued`/`Rendering`, and to non-agent transports.)

**Q: A job is sitting in `Ready` and my printer shows `Offline` — is my printer really off?**
Not necessarily. The Print Bridge Printer is only marked `Online` while the agent is **running and sending heartbeats**. If the agent is stopped, the heartbeat reaper marks the agent and its printers `Offline` after ~5 minutes — even though the physical printer is fine. Start the agent; on its next heartbeat the printer flips back to `Online` and the waiting job prints. To check the printer's *real* state, run `lpstat -p <queue>` on the agent machine.

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
