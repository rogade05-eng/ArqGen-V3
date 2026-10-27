"""Shared pricing math for exporters (unit cost of a budget item)."""

from __future__ import annotations

from typing import Any, Dict, Optional


def item_unit_cost(context, item: Dict[str, Any],
                   plist: Optional[Dict[str, Any]], date_iso: str) -> float:
    """Unit cost = Σ factor × (1 + waste%) × price (latest price ≤ date)."""
    if not plist:
        return 0.0
    total = 0.0
    for link in item.get("resources", []):
        price = context.budget_repo.get_price(
            link["resource_id"], plist["id"], date_iso) or 0.0
        total += link["factor"] * (1.0 + link["waste_pct"] / 100.0) * price
    return total


__all__ = ["item_unit_cost"]
