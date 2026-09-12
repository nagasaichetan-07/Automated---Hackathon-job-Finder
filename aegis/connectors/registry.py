"""
Aegis — Connector Registry

Provides factory lookups for instantiating connectors by key or class name.
"""

from __future__ import annotations

from connectors.base import BaseConnector
from connectors.greenhouse.connector import GreenhouseConnector
from connectors.lever.connector import LeverConnector
from connectors.rss.connector import RSSConnector
from connectors.web.connector import WebConnector

_REGISTRY: dict[str, type[BaseConnector]] = {
    "greenhouse": GreenhouseConnector,
    "GreenhouseConnector": GreenhouseConnector,
    "lever": LeverConnector,
    "LeverConnector": LeverConnector,
    "rss": RSSConnector,
    "RSSConnector": RSSConnector,
    "atom": RSSConnector,
    "web": WebConnector,
    "WebConnector": WebConnector,
}


def get_connector(connector_key: str) -> BaseConnector:
    """Instantiate a connector based on registry key."""
    cls = _REGISTRY.get(connector_key)
    if not cls:
        raise ValueError(f"Unknown connector '{connector_key}'. Available: {list(_REGISTRY.keys())}")
    return cls()

