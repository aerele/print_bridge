"""Command-line entry point: `print-bridge-agent start --url … --token …`."""

import argparse
import logging
import os

from . import __version__
from .daemon import Agent


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="print-bridge-agent",
        description="Print Bridge office agent — pulls print jobs from a Frappe "
        "bench and prints them on local CUPS printers.",
    )
    parser.add_argument("--version", action="version", version=f"print-bridge-agent {__version__}")
    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start", help="Start the agent daemon")
    start.add_argument("--url", default=os.environ.get("BENCH_URL"),
                       help="Bench base URL, e.g. https://acme.frappe.cloud (or BENCH_URL env)")
    start.add_argument("--token", default=os.environ.get("AGENT_TOKEN"),
                       help="Agent token from the Print Agent doctype (or AGENT_TOKEN env)")
    start.add_argument("--interval", type=float, default=float(os.environ.get("POLL_INTERVAL", "5")),
                       help="Seconds between polls (default 5)")
    start.add_argument("--name", default=os.environ.get("AGENT_NAME"), help="Optional display name")
    start.add_argument("--location", default=os.environ.get("AGENT_LOCATION"), help="Optional location")
    start.add_argument("--agent-id", default=os.environ.get("AGENT_ID"),
                       help="Optional agent id; enables the register call")
    start.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "INFO"))

    args = parser.parse_args(argv)
    if args.command != "start":
        parser.print_help()
        return 1
    if not args.url or not args.token:
        parser.error("--url/BENCH_URL and --token/AGENT_TOKEN are required")

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    Agent(
        url=args.url,
        token=args.token,
        interval=args.interval,
        name=args.name,
        location=args.location,
        agent_id=args.agent_id,
    ).run()
    return 0
