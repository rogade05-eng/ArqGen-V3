"""Budget module plugin (spec sections 53-62)."""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class BudgetPlugin(ARQGenPlugin):
    plugin_id = "budget"
    name = "Presupuesto"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["qto"]
    entities: list[str] = ["RESOURCE", "PRICE", "BUDGET", "BUDGET_CHAPTER", "BUDGET_ITEM"]
    services: list[str] = ["PricingService", "BudgetService"]
    events: list[str] = ["PRICE_CHANGED", "BUDGET_CHANGED"]
    commands: list[str] = ["CHANGE_PRICE"]
    reports: list[str] = ["budget_report", "price_history"]
