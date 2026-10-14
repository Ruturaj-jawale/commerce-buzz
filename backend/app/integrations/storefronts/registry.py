"""Resolve the platform-neutral commerce event adapter."""

from app.integrations.storefronts.base import UniversalCommerceAdapter

_ADAPTER = UniversalCommerceAdapter()

def get_adapter() -> UniversalCommerceAdapter:
    return _ADAPTER
