"""Network helpers shared by the analyzers."""

import ipaddress
import urllib.request
from urllib.parse import urlparse

# Local and private-network addresses must skip corporate proxies, which cannot reach them.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def is_local_host(hostname):
    """True for localhost, *.local names and loopback / private / link-local IP addresses."""
    hostname = (hostname or "").strip("[]").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def opener_for(url):
    """A direct opener for local hosts, the default (proxy-aware) opener for everything else."""
    return DIRECT if is_local_host(urlparse(url).hostname) else urllib.request.build_opener()
