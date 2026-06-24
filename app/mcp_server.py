"""
finance-concierge MCP Server
─────────────────────────────
Exposes 4 finance-specific tools over stdio transport (MCP Python SDK).
Used by: expense_tracker_agent, budget_planner_agent

Tools:
  1. get_spending_summary   — returns aggregated spending by category for a period
  2. get_budget_limits      — returns configured budget limits per category
  3. detect_recurring       — identifies recurring/subscription charges in transactions
  4. get_upcoming_renewals  — lists subscriptions renewing within N days
"""

import json
import sys
from datetime import datetime, timedelta
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ─────────────────────────────────────────────────────────────────────────────
# DEMO DATA  (in production these would query a real database / API)
# ─────────────────────────────────────────────────────────────────────────────

DEMO_TRANSACTIONS = [
    {"date": "2026-06-01", "merchant": "Whole Foods",      "amount": 87.43,  "category": "Food"},
    {"date": "2026-06-02", "merchant": "Netflix",           "amount": 15.99,  "category": "Entertainment"},
    {"date": "2026-06-03", "merchant": "Shell Gas",         "amount": 55.20,  "category": "Transport"},
    {"date": "2026-06-04", "merchant": "Starbucks",         "amount": 6.75,   "category": "Food"},
    {"date": "2026-06-05", "merchant": "Amazon Prime",      "amount": 14.99,  "category": "Shopping"},
    {"date": "2026-06-06", "merchant": "Spotify",           "amount": 9.99,   "category": "Entertainment"},
    {"date": "2026-06-07", "merchant": "Electric Bill",     "amount": 142.00, "category": "Bills"},
    {"date": "2026-06-08", "merchant": "Gym Membership",    "amount": 49.99,  "category": "Health"},
    {"date": "2026-06-10", "merchant": "Uber",              "amount": 23.40,  "category": "Transport"},
    {"date": "2026-06-11", "merchant": "Target",            "amount": 63.22,  "category": "Shopping"},
    {"date": "2026-06-12", "merchant": "Whole Foods",       "amount": 94.11,  "category": "Food"},
    {"date": "2026-06-14", "merchant": "Disney+",           "amount": 13.99,  "category": "Entertainment"},
    {"date": "2026-06-15", "merchant": "Internet Bill",     "amount": 79.99,  "category": "Bills"},
    {"date": "2026-06-16", "merchant": "Pharmacy",          "amount": 32.50,  "category": "Health"},
    {"date": "2026-06-18", "merchant": "H&M",               "amount": 78.00,  "category": "Shopping"},
    {"date": "2026-06-20", "merchant": "Chipotle",          "amount": 12.80,  "category": "Food"},
    {"date": "2026-06-21", "merchant": "Adobe CC",          "amount": 54.99,  "category": "Entertainment"},
    {"date": "2026-06-22", "merchant": "Lyft",              "amount": 18.90,  "category": "Transport"},
    {"date": "2026-06-23", "merchant": "Water Bill",        "amount": 38.00,  "category": "Bills"},
    {"date": "2026-06-24", "merchant": "LinkedIn Premium",  "amount": 39.99,  "category": "Other"},
]

DEMO_BUDGETS = {
    "Food":          {"limit": 400.00, "period": "monthly"},
    "Transport":     {"limit": 150.00, "period": "monthly"},
    "Entertainment": {"limit": 100.00, "period": "monthly"},
    "Shopping":      {"limit": 200.00, "period": "monthly"},
    "Bills":         {"limit": 300.00, "period": "monthly"},
    "Health":        {"limit": 100.00, "period": "monthly"},
    "Other":         {"limit": 50.00,  "period": "monthly"},
}

DEMO_SUBSCRIPTIONS = [
    {"name": "Netflix",          "amount": 15.99, "frequency": "monthly",  "next_renewal": "2026-07-02"},
    {"name": "Spotify",          "amount": 9.99,  "frequency": "monthly",  "next_renewal": "2026-07-06"},
    {"name": "Amazon Prime",     "amount": 14.99, "frequency": "monthly",  "next_renewal": "2026-07-05"},
    {"name": "Disney+",          "amount": 13.99, "frequency": "monthly",  "next_renewal": "2026-07-14"},
    {"name": "Adobe CC",         "amount": 54.99, "frequency": "monthly",  "next_renewal": "2026-07-21"},
    {"name": "Gym Membership",   "amount": 49.99, "frequency": "monthly",  "next_renewal": "2026-07-08"},
    {"name": "LinkedIn Premium", "amount": 39.99, "frequency": "monthly",  "next_renewal": "2026-07-24"},
    {"name": "iCloud 2TB",       "amount": 9.99,  "frequency": "monthly",  "next_renewal": "2026-06-28"},
]


# ─────────────────────────────────────────────────────────────────────────────
# MCP SERVER
# ─────────────────────────────────────────────────────────────────────────────

server = Server("finance-concierge-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_spending_summary",
            description=(
                "Returns aggregated spending totals grouped by category for a given "
                "date range. Useful for expense analysis and budget comparison."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format (inclusive). Defaults to start of current month.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format (inclusive). Defaults to today.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_budget_limits",
            description=(
                "Returns configured monthly budget limits for each spending category. "
                "Useful for comparing actual spending vs budgeted amounts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter to a specific category. Leave empty to get all categories.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="detect_recurring",
            description=(
                "Analyzes recent transactions to identify recurring/subscription charges. "
                "Returns a list of detected recurring payments with their estimated frequency and amounts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "min_occurrences": {
                        "type": "integer",
                        "description": "Minimum number of times a charge must appear to be considered recurring. Default: 1.",
                        "default": 1,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_upcoming_renewals",
            description=(
                "Lists subscriptions that are scheduled to renew within the next N days. "
                "Helps users prepare for upcoming charges and decide which to cancel."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days ahead to look for renewals. Default: 30.",
                        "default": 30,
                    },
                },
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "get_spending_summary":
        start = arguments.get("start_date", datetime.utcnow().strftime("%Y-%m-01"))
        end   = arguments.get("end_date",   datetime.utcnow().strftime("%Y-%m-%d"))

        totals: dict[str, float] = {}
        txns_in_range = []
        for t in DEMO_TRANSACTIONS:
            if start <= t["date"] <= end:
                cat = t["category"]
                totals[cat] = round(totals.get(cat, 0.0) + t["amount"], 2)
                txns_in_range.append(t)

        result = {
            "period":        {"start": start, "end": end},
            "total_spending": round(sum(totals.values()), 2),
            "by_category":   totals,
            "transaction_count": len(txns_in_range),
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "get_budget_limits":
        category = arguments.get("category", "").strip()
        if category and category in DEMO_BUDGETS:
            data = {category: DEMO_BUDGETS[category]}
        else:
            data = DEMO_BUDGETS

        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    elif name == "detect_recurring":
        min_occ = arguments.get("min_occurrences", 1)
        # Count merchant occurrences in demo data
        merchant_counts: dict[str, list] = {}
        for t in DEMO_TRANSACTIONS:
            m = t["merchant"]
            merchant_counts.setdefault(m, []).append(t)

        recurring = []
        for merchant, txns in merchant_counts.items():
            if len(txns) >= min_occ:
                avg_amount = round(sum(t["amount"] for t in txns) / len(txns), 2)
                recurring.append({
                    "merchant":    merchant,
                    "occurrences": len(txns),
                    "avg_amount":  avg_amount,
                    "likely_subscription": len(txns) >= 2 or avg_amount < 60,
                })

        recurring.sort(key=lambda x: x["avg_amount"], reverse=True)
        return [TextContent(type="text", text=json.dumps({"recurring_charges": recurring}, indent=2))]

    elif name == "get_upcoming_renewals":
        days_ahead = arguments.get("days_ahead", 30)
        today      = datetime.utcnow().date()
        cutoff     = today + timedelta(days=days_ahead)

        upcoming = []
        for sub in DEMO_SUBSCRIPTIONS:
            renewal_date = datetime.strptime(sub["next_renewal"], "%Y-%m-%d").date()
            if today <= renewal_date <= cutoff:
                days_until = (renewal_date - today).days
                upcoming.append({**sub, "days_until_renewal": days_until})

        upcoming.sort(key=lambda x: x["days_until_renewal"])
        total = round(sum(s["amount"] for s in upcoming), 2)
        return [TextContent(type="text", text=json.dumps({
            "upcoming_renewals":       upcoming,
            "total_upcoming_charges":  total,
            "renewal_count":           len(upcoming),
        }, indent=2))]

    else:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
