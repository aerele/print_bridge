# Print Bridge office agent.
# Pulls jobs from the bench over HTTPS and prints via the local CUPS server.
FROM python:3.12-slim

# cups-client provides the `lp` / `lpstat` CLIs the agent shells out to.
RUN apt-get update \
 && apt-get install -y --no-install-recommends cups-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

# Provide BENCH_URL and AGENT_TOKEN at runtime. To reach a CUPS server that is
# NOT inside the container, set CUPS_SERVER=<host-ip[:631]> (or run with
# --network host and a local cupsd). Example:
#   docker run -d --restart=always \
#     -e BENCH_URL=https://acme.frappe.cloud \
#     -e AGENT_TOKEN=xxxxx \
#     -e CUPS_SERVER=192.168.1.10 \
#     aerele/print-bridge-agent:latest
ENTRYPOINT ["print-bridge-agent", "start"]
