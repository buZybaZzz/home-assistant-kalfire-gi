"""Kalfire Gi local protocol; independent of Home Assistant."""

from .client import GiClient, Snapshot

__all__ = ["GiClient", "Snapshot"]
