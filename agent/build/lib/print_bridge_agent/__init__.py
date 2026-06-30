"""Print Bridge office agent.

A small, Frappe-independent daemon that runs on a machine inside the office LAN.
It dials *out* to the company's Print Bridge bench over HTTPS, pulls print jobs
targeting its printers, downloads the rendered file, and prints it on the local
CUPS server via the `lp` CLI (no pycups required). See README.md.
"""

__version__ = "0.1.0"
