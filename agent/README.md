# Print Bridge Agent

The office-side companion for the [Print Bridge](https://github.com/aerele/print_bridge)
Frappe/ERPNext app. It runs on **one always-on machine inside your office LAN**,
dials *out* to your Print Bridge bench over HTTPS, pulls print jobs for your
local printers, and prints them via the local CUPS server.

Because every connection is **outbound only**, this works on ordinary broadband
with no static IP, no port forwarding, and no VPN — including CGNAT. It is what
makes Print Bridge usable on Frappe Cloud, where the bench cannot reach your
office printers directly.

> The agent talks to CUPS through the standard `lp` / `lpstat` commands, so it
> needs **no pycups / C-extension build** — just CUPS client tools and Python.

## Requirements

- One always-on machine on the same LAN as your printers (mini-PC, NAS,
  Raspberry Pi, spare desktop, or a small container).
- CUPS client tools (`lp`, `lpstat`) installed, and your printer added to CUPS
  with a working driver. Verify with `lpstat -e` and `echo hi | lp -d <queue>`.
- Outbound HTTPS (port 443) to your bench. Python 3.8+ (for the pip install).

## Setup (two steps)

1. **In Frappe Desk:** Print Bridge → Print Agent → New → Save → **Generate
   Token** (copy it — it is shown only once).
2. **On the office machine:** run the agent with your bench URL + token (below).

The agent then self-registers, auto-discovers your local CUPS printers (pushing
them into the registry as `transport = agent`), and starts printing jobs.

## Install & run

### pip

```bash
pip install print-bridge-agent
print-bridge-agent start \
  --url https://your-site.frappe.cloud \
  --token <paste-token-here>
```

Or via environment variables (handy for services/containers):

```bash
export BENCH_URL=https://your-site.frappe.cloud
export AGENT_TOKEN=<paste-token-here>
print-bridge-agent start
```

### Docker

```bash
docker run -d --restart=always \
  -e BENCH_URL=https://your-site.frappe.cloud \
  -e AGENT_TOKEN=<paste-token-here> \
  -e CUPS_SERVER=192.168.1.10 \
  aerele/print-bridge-agent:latest
```

`CUPS_SERVER` points the container's `lp` at the CUPS server on your LAN (host IP,
optionally `:631`). Alternatively run with `--network host` against a local cupsd.

### systemd service

`/etc/systemd/system/print-bridge-agent.service`:

```ini
[Unit]
Description=Print Bridge Agent
After=network-online.target cups.service
Wants=network-online.target

[Service]
Environment=BENCH_URL=https://your-site.frappe.cloud
Environment=AGENT_TOKEN=paste-token-here
ExecStart=/usr/local/bin/print-bridge-agent start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now print-bridge-agent
journalctl -u print-bridge-agent -f
```

## Options

| Flag | Env | Default | Description |
|---|---|---|---|
| `--url` | `BENCH_URL` | — | Bench base URL (required) |
| `--token` | `AGENT_TOKEN` | — | Agent token from the Print Agent doctype (required) |
| `--interval` | `POLL_INTERVAL` | `5` | Seconds between polls |
| `--name` | `AGENT_NAME` | — | Optional display name |
| `--location` | `AGENT_LOCATION` | — | Optional location |
| `--agent-id` | `AGENT_ID` | — | Optional; enables the `register` call |
| `--log-level` | `LOG_LEVEL` | `INFO` | Logging level |

## How it works

```
poll_jobs ─► download rendered PDF (X-Agent-Token) ─► lp -d <queue> ─► local CUPS ─► printer
          ─► confirm via lpstat ─► report Completed / Failed
```

Each cycle the agent sends a heartbeat (with per-printer status), then asks the
bench for jobs targeting its printers. For each job it downloads the private
rendered file, prints it with `lp`, confirms the CUPS job actually completed
(so a silently-dropped job is reported `Failed`, not a false `Completed`), and
reports the outcome. If the network drops, jobs stay queued on the bench and
flush when the agent reconnects.

## Security

- The token is a scoped, rotatable machine credential. Revoke it from the Print
  Agent doctype to cut an office off instantly.
- Rendered files are private and fetched only with the token header over TLS.
- The agent sends no document content anywhere except your own printers.
