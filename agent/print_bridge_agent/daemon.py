"""The agent daemon: register/heartbeat, then poll → download → print → report."""

import logging
import os
import signal
import tempfile
import time

import requests

from . import __version__, printers
from .client import AgentClient

log = logging.getLogger("print_bridge_agent")


class Agent:
    def __init__(self, url, token, interval=5, name=None, location=None, agent_id=None):
        self.client = AgentClient(url, token)
        self.interval = interval
        self.name = name
        self.location = location
        self.agent_id = agent_id
        self._stop = False

    def stop(self, *_):
        log.info("Shutdown requested, finishing current cycle...")
        self._stop = True

    def run(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        log.info("print-bridge-agent v%s → %s", __version__, self.client.base_url)
        self._startup()

        backoff = self.interval
        while not self._stop:
            try:
                self._tick()
                backoff = self.interval
            except requests.RequestException as exc:
                log.warning("network error: %s (retrying in %ss)", exc, backoff)
                self._sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            except Exception as exc:  # never let the loop die
                log.exception("unexpected error: %s", exc)
            self._sleep(self.interval)
        log.info("Stopped.")

    # ── lifecycle ────────────────────────────────────────────────────────────
    def _startup(self):
        if self.agent_id:
            try:
                self.client.register(
                    self.agent_id,
                    display_name=self.name,
                    location=self.location,
                    version=__version__,
                )
            except Exception as exc:
                log.warning("register failed (continuing): %s", exc)
        try:
            discovered = printers.discover_printers()
            self.client.sync_printers(discovered)
            log.info(
                "synced %d local printer(s): %s",
                len(discovered),
                ", ".join(p["name"] for p in discovered) or "(none)",
            )
        except Exception as exc:
            log.warning("printer sync failed: %s", exc)

    def _tick(self):
        self.client.heartbeat(version=__version__, printer_statuses=printers.printer_statuses())
        result = self.client.poll_jobs() or {}
        for job in result.get("jobs", []):
            if self._stop:
                break
            self._handle_job(job)

    def _handle_job(self, job):
        name = job.get("name")
        printer = job.get("target_printer")
        log.info("job %s → printer %s", name, printer)

        # Pre-submit guard: the printer may have gone offline between the heartbeat
        # and now. Release the claimed job back to Ready so it waits, rather than
        # attempting a print that would fail.
        if not printers.is_online(printer):
            log.info("printer %s offline; releasing job %s back to wait", printer, name)
            self._release(name)
            return

        tmp_path = None
        try:
            content = self.client.download_job_file(name)
            suffix = ".bin" if job.get("is_raw") else ".pdf"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="pbagent-")
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)

            cups_job_id = printers.submit(printer, tmp_path, job)
            printers.confirm_printed(printer, cups_job_id)
            self.client.update_job_status(name, "Completed")
            log.info("job %s completed", name)
        except printers.PrinterOfflineError as exc:
            # Printer went offline during printing — wait, don't fail.
            log.warning("job %s: printer offline mid-print, releasing: %s", name, exc)
            self._release(name)
        except Exception as exc:
            log.error("job %s failed: %s", name, exc)
            try:
                self.client.update_job_status(name, "Failed", error=str(exc))
            except Exception as report_exc:
                log.error("could not report failure for %s: %s", name, report_exc)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _release(self, name):
        """Hand a claimed job back to the bench's waiting pool (Ready)."""
        try:
            self.client.update_job_status(name, "Ready")
        except Exception as report_exc:
            log.error("could not release job %s: %s", name, report_exc)

    def _sleep(self, seconds):
        """Interruptible sleep so SIGTERM/SIGINT is responsive."""
        end = time.monotonic() + seconds
        while not self._stop:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.5, remaining))
