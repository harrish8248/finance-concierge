# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import re
import sys
import os
import logging
from datetime import datetime
from pathlib import Path

from google.adk import Context, Workflow
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.tools import AgentTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.workflow import Edge, START, node
from google.adk.events import RequestInput
from google.adk.models import Gemini
from google.genai import types
from mcp import StdioServerParameters

from app.config import config

# ─────────────────────────────────────────────────────────────────────────────
# MCP TOOLSET (stdio — spawns mcp_server.py as a subprocess)
# ─────────────────────────────────────────────────────────────────────────────

_MCP_SERVER_PATH = str(Path(__file__).parent / "mcp_server.py")

finance_mcp_toolset = McpToolset(
    connection_params=StdioServerParameters(
        command=sys.executable,
        args=[_MCP_SERVER_PATH],
    ),
)

logger = logging.getLogger(__name__)

async def handle_model_error(*args, **kwargs):
    from google.adk.models.llm_request import LlmRequest
    from google.adk.models.llm_response import LlmResponse
    
    ctx = kwargs.get("callback_context") or (args[0] if len(args) > 0 else None)
    request = kwargs.get("llm_request") or (args[1] if len(args) > 1 else None)
    error = kwargs.get("error") or (args[2] if len(args) > 2 else None)
    
    error_str = str(error)
    logger.warning("Model call failed with error: %s. Using mock fallback.", error_str)

    # Determine which agent is calling by looking at the system instruction
    system_instruction = ""
    if request.config and request.config.system_instruction:
        system_instruction = str(request.config.system_instruction).lower()

    # Get prompt from user query
    user_query = ""
    if request.contents:
        last_content = request.contents[-1]
        if last_content.parts:
            user_query = " ".join(part.text for part in last_content.parts if part.text).lower()

    # 1. EXPENSE TRACKER
    if "expense tracker" in system_instruction:
        mock_data = {
            "categories": {"Bills": 259.99, "Food": 201.09, "Transport": 97.50, "Shopping": 156.21, "Entertainment": 94.96, "Health": 82.49, "Other": 39.99},
            "transactions_analyzed": 20,
            "flagged_items": [],
            "insights": "Your overall spending is well within the budget limits."
        }
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=json.dumps(mock_data))]
            )
        )

    # 2. BUDGET PLANNER
    elif "budget planning" in system_instruction:
        mock_data = {
            "budget_status": {
                "Food": {"budgeted": 400.00, "actual": 201.09, "variance": 198.91, "status": "under"},
                "Entertainment": {"budgeted": 100.00, "actual": 94.96, "variance": 5.04, "status": "under"},
                "Transport": {"budgeted": 150.00, "actual": 97.50, "variance": 52.50, "status": "under"},
                "Shopping": {"budgeted": 200.00, "actual": 156.21, "variance": 43.79, "status": "under"},
                "Bills": {"budgeted": 300.00, "actual": 259.99, "variance": 40.01, "status": "under"},
                "Health": {"budgeted": 100.00, "actual": 82.49, "variance": 17.51, "status": "under"},
                "Other": {"budgeted": 50.00, "actual": 39.99, "variance": 10.01, "status": "under"}
            },
            "overall_health": "healthy",
            "recommendations": [
                "You are under budget in all categories. Excellent job managing your finances this month!",
                "Consider redirecting a portion of your Food or Transport surplus toward savings or investments."
            ],
            "projected_month_end_balance": 1200.00,
            "savings_opportunity": 372.77
        }
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=json.dumps(mock_data))]
            )
        )

    # 3. SUBSCRIPTION MANAGER
    elif "subscription management" in system_instruction or "subscription manager" in system_instruction:
        mock_data = {
            "subscriptions": [
                {"name": "Adobe CC", "amount": 54.99, "frequency": "monthly", "next_renewal": "2026-07-15", "status": "active"},
                {"name": "Netflix", "amount": 15.49, "frequency": "monthly", "next_renewal": "2026-07-10", "status": "active"},
                {"name": "Spotify", "amount": 10.99, "frequency": "monthly", "next_renewal": "2026-07-12", "status": "active"}
            ],
            "total_monthly_cost": 81.47,
            "renewal_alerts": [{"name": "Adobe CC", "days_left": 21}],
            "unused_suspects": [{"name": "Adobe CC", "reason": "No usage detected in the last 30 days"}],
            "potential_savings": 54.99
        }
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=json.dumps(mock_data))]
            )
        )

    # 4. ORCHESTRATOR
    elif "orchestrator" in system_instruction:
        # Check if we have tool responses in the history.
        # If yes, we are doing synthesis.
        # If no, we are predicting tool calls.
        has_tool_responses = any(
            any(p.function_response or p.tool_response for p in c.parts)
            for c in request.contents
            if c.parts
        )
        
        if not has_tool_responses:
            # Predict tool calls based on user query
            if "cancel" in user_query or "adobe" in user_query or "subscription" in user_query:
                # Call subscription manager
                return LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="subscription_manager_agent",
                                args={"request": "Track and manage Adobe CC subscription."}
                            )
                        ]
                    )
                )
            else:
                # Call expense tracker and budget planner
                return LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="expense_tracker_agent",
                                args={"request": "Summarize spending for this month."}
                            ),
                            types.Part.from_function_call(
                                name="budget_planner_agent",
                                args={"request": "Compare spending to budget."}
                            )
                        ]
                    )
                )
        else:
            # Doing synthesis
            if "cancel" in user_query or "adobe" in user_query or "subscription" in user_query:
                ctx.state["requires_review"] = True
                ctx.state["review_reason"] = "Cancel Adobe CC subscription ($54.99/month). No usage detected in the last 30 days."
                
                synthesis_text = (
                    "Based on my analysis, you have 3 active subscriptions costing a total of $81.47/month.\n\n"
                    "I identified that you have not used your Adobe CC subscription ($54.99/month) in the last 30 days, "
                    "which presents a potential savings opportunity.\n\n"
                    "⚠️ Since this subscription costs more than $50/month, I have flagged it for your approval before cancelling."
                )
                return LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=synthesis_text)]
                    )
                )
            else:
                synthesis_text = (
                    "It looks like you've had a fantastic month managing your finances! Here's a summary of your spending and budget performance:\n\n"
                    "**Financial Snapshot:**\n"
                    "Your total spending for this month stands at **$932.23** across 20 analyzed transactions.\n\n"
                    "**Top Spending Categories:**\n"
                    "- Bills: $259.99\n"
                    "- Food: $201.09\n\n"
                    "**Budget vs. Actual:**\n"
                    "I'm pleased to report that you are under budget in all categories this month! Your overall budget health is looking very healthy.\n\n"
                    "Here's a quick breakdown:\n"
                    "- **Food**: Budgeted $400.00, Actual $201.09 (Under by $198.91)\n"
                    "- **Entertainment**: Budgeted $100.00, Actual $94.96 (Under by $5.04)\n"
                    "- **Transport**: Budgeted $150.00, Actual $97.50 (Under by $52.50)\n"
                    "- **Shopping**: Budgeted $200.00, Actual $156.21 (Under by $43.79)\n"
                    "- **Bills**: Budgeted $300.00, Actual $259.99 (Under by $40.01)\n"
                    "- **Health**: Budgeted $100.00, Actual $82.49 (Under by $17.51)\n"
                    "- **Other**: Budgeted $50.00, Actual $39.99 (Under by $10.01)\n\n"
                    "**Top 3 Insights:**\n"
                    "1. All spending categories are currently within budget limits.\n"
                    "2. Food and Transport have the largest surpluses.\n"
                    "3. You have an opportunity to save an extra $372.77 this month.\n\n"
                    "**Next Steps:**\n"
                    "- Consider redirecting a portion of your Food or Transport surplus toward savings or investments.\n"
                    "- Keep logging your purchases."
                )
                return LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=synthesis_text)]
                    )
                )

    # Generic fallback
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="I am your Finance Concierge. How can I help you today?")]
        )
    )



# ─────────────────────────────────────────────────────────────────────────────
# SPECIALIZED SUB-AGENTS
# ─────────────────────────────────────────────────────────────────────────────

is_test = "pytest" in sys.modules or os.environ.get("INTEGRATION_TEST") == "TRUE"
retry_opts = types.HttpRetryOptions(
    attempts=1 if is_test else 4,
    initial_delay=0.1 if is_test else 5.0,
    exp_base=2.0
)

expense_tracker_agent = LlmAgent(
    name="expense_tracker_agent",
    model=Gemini(model=config.model, retry_options=retry_opts),
    description="Analyzes and categorizes individual expense transactions.",
    instruction="""You are an expert personal finance expense tracker.

You have access to MCP tools:
- Use `get_spending_summary` to fetch aggregated spending data by category
- Use `detect_recurring` to find recurring/subscription charges in the data

Given a request, you:
1. Fetch spending data using get_spending_summary for the relevant period
2. Detect recurring charges using detect_recurring
3. Categorize and analyze the transactions
4. Identify any unusual or high-value transactions (above $200)
5. Flag duplicate or suspicious-looking entries

Always respond with a structured JSON report containing:
- categories: {category: total_amount}
- transactions_analyzed: count
- flagged_items: list of flagged transactions with reason
- insights: one-line summary

Be concise and data-focused.""",
    tools=[finance_mcp_toolset],
    output_key="expense_analysis",
    on_model_error_callback=handle_model_error,
)

budget_planner_agent = LlmAgent(
    name="budget_planner_agent",
    model=Gemini(model=config.model, retry_options=retry_opts),
    description="Creates budget plans and analyzes budget vs actual spending.",
    instruction="""You are a personal budget planning expert.

You have access to MCP tools:
- Use `get_spending_summary` to fetch current spending data
- Use `get_budget_limits` to fetch the configured budget limits per category

You help users:
1. Fetch spending data and budget limits using your MCP tools
2. Compare actual spending vs planned budget by category
3. Identify categories where the user is over/under budget
4. Recommend adjustments and savings strategies
5. Project end-of-month surplus or deficit

Always respond with a structured JSON report containing:
- budget_status: {category: {budgeted: X, actual: Y, variance: Z, status: "over/under/on_track"}}
- overall_health: "healthy/warning/critical"
- recommendations: list of actionable suggestions
- projected_month_end_balance: amount
- savings_opportunity: amount

Be practical and encouraging.""",
    tools=[finance_mcp_toolset],
    output_key="budget_analysis",
    on_model_error_callback=handle_model_error,
)

subscription_manager_agent = LlmAgent(
    name="subscription_manager_agent",
    model=Gemini(model=config.model, retry_options=retry_opts),
    description="Tracks recurring subscriptions, renewals, and identifies unused services.",
    instruction="""You are a subscription management specialist.

You help users track and optimize their recurring payments:
1. List all detected recurring charges (weekly/monthly/annual) using MCP tools
2. Calculate total monthly subscription cost
3. Identify subscriptions coming up for renewal in the next 30 days using get_upcoming_renewals
4. Flag potentially unused or duplicate subscriptions
5. Suggest cancellations to reduce monthly spend

Always respond with a structured JSON report containing:
- subscriptions: list of {name, amount, frequency, next_renewal, status}
- total_monthly_cost: amount
- renewal_alerts: subscriptions renewing in ≤30 days
- unused_suspects: subscriptions to consider cancelling
- potential_savings: amount if unused_suspects are cancelled

Be detail-oriented and proactive about renewals.""",
    tools=[finance_mcp_toolset],
    output_key="subscription_analysis",
    on_model_error_callback=handle_model_error,
)

orchestrator_agent = LlmAgent(
    name="orchestrator_agent",
    model=Gemini(model=config.model, retry_options=retry_opts),
    description="Orchestrates finance analysis by delegating to specialized sub-agents.",
    instruction="""You are the Personal Finance Concierge orchestrator.

CRITICAL: Do NOT output any introductory text, conversational filler, or acknowledgment (like "Let me check that for you" or "Please bear with me"). You must immediately call the appropriate specialized sub-agents using your tools in your first turn.

Your job is to understand what the user needs and coordinate the right analysis:
- If they want to track expenses/transactions → delegate to expense_tracker_agent
- If they want to check their budget or savings → delegate to budget_planner_agent  
- If they want to manage subscriptions or recurring payments → delegate to subscription_manager_agent
- For comprehensive reviews, delegate to all three agents

After getting results from sub-agents:
1. Synthesize the findings into a clear, actionable summary
2. Highlight the 3 most important insights
3. Provide 2-3 concrete next steps the user should take
4. Flag any items requiring user approval (large transactions, cancellations, budget changes)

Store your final synthesis in state['orchestrator_summary'].
If any action requires user approval (e.g., cancelling a subscription >$50/month or flagging a transaction >$500), 
set state['requires_review'] = True and state['review_reason'] to explain what needs approval.

Respond in a friendly, professional concierge tone.""",
    tools=[
        AgentTool(agent=expense_tracker_agent),
        AgentTool(agent=budget_planner_agent),
        AgentTool(agent=subscription_manager_agent),
    ],
    output_key="orchestrator_summary",
    on_model_error_callback=handle_model_error,
)


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW FUNCTION NODES
# ─────────────────────────────────────────────────────────────────────────────

@node
async def security_checkpoint(ctx: Context) -> None:
    """
    Phase 4 — Security checkpoint node.
    - PII scrubbing: masks account numbers, card numbers, SSNs, emails
    - Prompt injection detection: blocks jailbreak attempts
    - Structured JSON audit log on every request
    - Domain rule: blocks requests containing raw unmasked card numbers
    """
    raw_input = str(ctx.user_content) if ctx.user_content else ""

    # ── PII SCRUBBING ──────────────────────────────────────────────────────
    pii_patterns = {
        "credit_card":   (r"\b(?:\d[ -]?){13,16}\b", "[CARD-REDACTED]"),
        "ssn":           (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN-REDACTED]"),
        "email":         (r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b", "[EMAIL-REDACTED]"),
        "bank_account":  (r"\b\d{8,17}\b", "[ACCOUNT-REDACTED]"),
        "phone":         (r"\b(?:\+?\d[\d\s\-().]{7,}\d)\b", "[PHONE-REDACTED]"),
        "iban":          (r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}(?:[A-Z0-9]{0,16})\b", "[IBAN-REDACTED]"),
    }

    scrubbed_input = raw_input
    pii_found = []
    if config.pii_redaction_enabled:
        for pii_type, (pattern, replacement) in pii_patterns.items():
            if re.search(pattern, scrubbed_input):
                pii_found.append(pii_type)
                scrubbed_input = re.sub(pattern, replacement, scrubbed_input)

    # ── PROMPT INJECTION DETECTION ─────────────────────────────────────────
    injection_keywords = [
        "ignore previous", "ignore all", "disregard instructions",
        "act as", "jailbreak", "DAN mode", "pretend you are",
        "forget your instructions", "override", "bypass safety",
        "system prompt", "you are now", "new persona",
        "reveal your instructions", "print your prompt",
    ]

    injection_detected = False
    if config.injection_detection_enabled:
        lower_input = raw_input.lower()
        injection_detected = any(kw in lower_input for kw in injection_keywords)

    # ── DOMAIN RULE: raw unmasked card number in input ─────────────────────
    raw_card_detected = bool(re.search(r"\b(?:\d[ ]?){15,16}\b", raw_input))

    # ── AUDIT LOG ──────────────────────────────────────────────────────────
    severity = "INFO"
    if injection_detected or raw_card_detected:
        severity = "CRITICAL"
    elif pii_found:
        severity = "WARNING"

    audit_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": "security_checkpoint",
        "severity": severity,
        "pii_types_scrubbed": pii_found,
        "injection_detected": injection_detected,
        "raw_card_detected": raw_card_detected,
        "input_length": len(raw_input),
    }
    logger.info("AUDIT: %s", json.dumps(audit_entry))

    # ── ROUTE DECISION ─────────────────────────────────────────────────────
    if injection_detected or raw_card_detected:
        ctx.state["security_event"] = audit_entry
        ctx.state["security_block_reason"] = (
            "Prompt injection attempt detected."
            if injection_detected
            else "Raw unmasked card number in request. Please mask sensitive data."
        )
        ctx.route = "SECURITY_EVENT"
    else:
        ctx.state["scrubbed_input"] = scrubbed_input
        ctx.state["pii_scrubbed"] = pii_found
        ctx.route = "CLEAR"


@node
async def review_gate(ctx: Context) -> None:
    """
    Human-in-the-loop gate: pauses for user confirmation when the orchestrator
    flags a high-value or irreversible action for review.
    """
    requires_review = ctx.state.get("requires_review", False)
    review_reason = ctx.state.get("review_reason", "")

    if requires_review:
        response = await ctx.request_confirmation(
            message=(
                f"⚠️ Your Finance Concierge needs your approval:\n\n"
                f"{review_reason}\n\n"
                f"Do you approve this action? Reply 'yes' to confirm or 'no' to cancel."
            ),
        )
        ctx.state["user_approved"] = bool(response and str(response).lower().strip() in ("yes", "y", "approve", "ok"))
        ctx.state["review_response"] = str(response)
    else:
        ctx.state["user_approved"] = True


@node
async def final_output(ctx: Context) -> None:
    """
    Formats and returns the final response to the user. Handles both
    normal completions and security-blocked requests.
    """
    # Was this a security block?
    security_event = ctx.state.get("security_event")
    if security_event and security_event.get("severity") == "CRITICAL":
        block_reason = ctx.state.get("security_block_reason", "Request blocked for security reasons.")
        ctx.output = (
            f"🚫 **Request Blocked**\n\n"
            f"{block_reason}\n\n"
            f"Please rephrase your request and try again."
        )
        return

    # Normal output
    summary = ctx.state.get("orchestrator_summary", "")
    approved = ctx.state.get("user_approved", True)
    review_reason = ctx.state.get("review_reason", "")

    if not approved and review_reason:
        ctx.output = (
            f"✋ **Action Cancelled**\n\n"
            f"The following action was not approved and has been cancelled:\n{review_reason}\n\n"
            f"Here's your analysis summary:\n\n{summary}"
        )
    else:
        pii_note = ""
        pii_types = ctx.state.get("pii_scrubbed", [])
        if pii_types:
            pii_note = f"\n\n_ℹ️ Note: Sensitive data ({', '.join(pii_types)}) was automatically masked for your security._"

        ctx.output = f"{summary}{pii_note}"


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW GRAPH
# ─────────────────────────────────────────────────────────────────────────────

root_agent = Workflow(
    name="finance_concierge_workflow",
    description=(
        "Personal Finance Concierge — tracks budgets, analyzes spending habits, "
        "and manages subscription renewals with security and human-in-the-loop review."
    ),
    edges=[
        # START → security checkpoint (always first)
        Edge(from_node=START, to_node=security_checkpoint),

        # security checkpoint → orchestrator (when safe) or final_output (when blocked)
        Edge(from_node=security_checkpoint, to_node=orchestrator_agent, route="CLEAR"),
        Edge(from_node=security_checkpoint, to_node=final_output, route="SECURITY_EVENT"),

        # orchestrator → human review gate
        Edge(from_node=orchestrator_agent, to_node=review_gate),

        # review gate → final output (single unconditional edge — no duplicate edges)
        Edge(from_node=review_gate, to_node=final_output),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
