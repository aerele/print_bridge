from print_bridge.transport.agent_transport import AgentTransport
from print_bridge.transport.browser_qz import BrowserQzTransport
from print_bridge.transport.cloud_ipp import CloudIppTransport
from print_bridge.transport.cups_direct import CupsDirectTransport
from print_bridge.transport.raw_socket import RawSocketTransport

_DRIVERS = {
	"agent": AgentTransport,
	"cups_direct": CupsDirectTransport,
	"raw_socket": RawSocketTransport,
	"cloud_ipp": CloudIppTransport,
	"browser_qz": BrowserQzTransport,
}


def get_driver(transport_key):
	cls = _DRIVERS.get(transport_key)
	if not cls:
		raise ValueError(f"Unknown transport driver: {transport_key}")
	return cls()
