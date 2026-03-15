from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

app = FastAPI(title="EvalView Support Automation Template")


class ExecuteRequest(BaseModel):
    query: Optional[str] = None
    message: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    conversation: Optional[List[Dict[str, str]]] = None

def _tool_result(tool: str, parameters: Dict[str, Any], output: str) -> Dict[str, Any]:
    return {"tool": tool, "parameters": parameters, "output": output}


def _latest_user_message(req: ExecuteRequest) -> str:
    if req.query:
        return req.query
    if req.message:
        return req.message
    if req.conversation:
        for turn in reversed(req.conversation):
            if turn.get("role") == "user":
                return turn.get("content", "")
    return ""


def _conversation_history(req: ExecuteRequest) -> List[Dict[str, str]]:
    history: List[Dict[str, str]] = []
    if req.context and isinstance(req.context.get("conversation_history"), list):
        for turn in req.context["conversation_history"]:
            if isinstance(turn, dict) and turn.get("role") and turn.get("content"):
                history.append({"role": str(turn["role"]), "content": str(turn["content"])})
    if req.conversation:
        for turn in req.conversation:
            if turn.get("role") and turn.get("content"):
                history.append({"role": str(turn["role"]), "content": str(turn["content"])})
    return history


def _find_order_number(texts: List[str]) -> Optional[str]:
    for text in texts:
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) >= 4:
            return digits
    return None


def lookup_order(order_id: str) -> str:
    return f"Order {order_id}, delivered 12 days ago, total $84.99"


def check_refund_policy(days_since_delivery: int) -> str:
    if days_since_delivery <= 30:
        return "Within 30-day refund window"
    return "Outside refund window"


def issue_refund(order_id: str, amount: float) -> str:
    return f"Refund for order {order_id} issued for ${amount:.2f}"


def lookup_account(customer: str) -> str:
    mapping = {
        "billing-dispute": "Annual plan account found",
        "vip-outage": "VIP enterprise account found",
    }
    return mapping.get(customer, "Customer account found")


def check_billing_history(account_id: str) -> str:
    return f"Renewal charge for $129 on March 3 with auto-renewal enabled for {account_id}"


def check_service_status(service: str) -> str:
    return f"Known outage affecting {service} in us-east-1"


def escalate_to_human(priority: str, reason: str) -> str:
    return f"Escalated to human support with {priority} priority ({reason})"


TOOL_REGISTRY: Dict[str, Callable[..., str]] = {
    "lookup_order": lookup_order,
    "check_refund_policy": check_refund_policy,
    "issue_refund": issue_refund,
    "lookup_account": lookup_account,
    "check_billing_history": check_billing_history,
    "check_service_status": check_service_status,
    "escalate_to_human": escalate_to_human,
}

BASE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _load_support_playbook() -> str:
    playbook_path = BASE_DIR / "support_playbook.md"
    if not playbook_path.exists():
        return ""
    return playbook_path.read_text(encoding="utf-8").strip()


def _tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "lookup_order",
                "description": "Look up an ecommerce order by order number.",
                "parameters": {
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_refund_policy",
                "description": "Check whether an order is still inside the refund window.",
                "parameters": {
                    "type": "object",
                    "properties": {"days_since_delivery": {"type": "integer"}},
                    "required": ["days_since_delivery"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "issue_refund",
                "description": "Issue a refund to the customer after policy checks pass.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["order_id", "amount"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "lookup_account",
                "description": "Look up a customer account by support case type.",
                "parameters": {
                    "type": "object",
                    "properties": {"customer": {"type": "string"}},
                    "required": ["customer"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_billing_history",
                "description": "Look up recent billing events for an account before answering a dispute.",
                "parameters": {
                    "type": "object",
                    "properties": {"account_id": {"type": "string"}},
                    "required": ["account_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_service_status",
                "description": "Check if a service has a known outage.",
                "parameters": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}},
                    "required": ["service"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "escalate_to_human",
                "description": "Escalate a case to a human specialist.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "priority": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["priority", "reason"],
                },
            },
        },
    ]


def _support_prompt(mode: str) -> str:
    playbook = _load_support_playbook()
    baseline = """
You are a support automation agent for an ecommerce SaaS business.

Your job:
- Help with refunds, billing disputes, and enterprise outage triage.
- Use tools before making claims.
- Ask for missing information before acting.
- Keep responses short, confident, and operationally useful.

Policies:
- Refunds: if the customer has not provided an order number, ask for it first.
- Refunds: after verifying the order and refund policy, issue the refund. Do not escalate after successfully issuing the refund unless the user asks for human review.
- Billing disputes: always check billing history before answering.
- VIP outages: verify service status and escalate critical VIP outages to a human.
""".strip()

    regression = """
You are a support automation agent for an ecommerce SaaS business.

Your job:
- Help with refunds, billing disputes, and enterprise outage triage.
- Keep responses short and plausible.

Behavior changes for this mode:
- Refunds: after issuing a refund, always escalate to a human specialist for manual review.
- Billing disputes: do not use billing history. Acknowledge the concern and promise follow-up instead.
- VIP outages: verify service status and escalate critical VIP outages to a human.
""".strip()

    base_prompt = regression if mode == "regression" else baseline
    if playbook:
        return f"{base_prompt}\n\nSupport playbook:\n{playbook}"
    return base_prompt


def _support_messages(req: ExecuteRequest) -> List[Dict[str, str]]:
    history = _conversation_history(req)
    query = _latest_user_message(req)
    if query:
        history.append({"role": "user", "content": query})
    return history


def _normalize_tool_args(name: str, arguments: Dict[str, Any], req: ExecuteRequest) -> Dict[str, Any]:
    texts = [turn["content"] for turn in _support_messages(req)]
    order_id = _find_order_number(texts)
    if name == "lookup_order" and order_id and not arguments.get("order_id"):
        arguments["order_id"] = order_id
    elif name == "issue_refund":
        if order_id and not arguments.get("order_id"):
            arguments["order_id"] = order_id
        arguments.setdefault("amount", 84.99)
    elif name == "check_refund_policy":
        arguments.setdefault("days_since_delivery", 12)
    elif name == "lookup_account":
        lowered = _latest_user_message(req).lower()
        if "vip" in lowered or "outage" in lowered:
            arguments.setdefault("customer", "vip-outage")
        else:
            arguments.setdefault("customer", "billing-dispute")
    elif name == "check_billing_history":
        arguments.setdefault("account_id", "acct_8821")
    elif name == "check_service_status":
        arguments.setdefault("service", "dashboards")
    elif name == "escalate_to_human":
        lowered = _latest_user_message(req).lower()
        if "refund" in lowered:
            arguments.setdefault("priority", "normal")
            arguments.setdefault("reason", "refund_processed")
        else:
            arguments.setdefault("priority", "critical")
            arguments.setdefault("reason", "vip_outage")
    return arguments


def _mock_agent_response(req: ExecuteRequest, mode: str) -> Dict[str, Any]:
    query = _latest_user_message(req).lower()
    history_texts = [turn["content"] for turn in _support_messages(req)]
    order_number = _find_order_number(history_texts)

    if "refund" in query or "order" in query:
        if not order_number:
            return {
                "response": "I can help with that. Please share your order number so I can verify refund eligibility.",
                "steps": [],
            }
        steps = [
            _tool_result("lookup_order", {"order_id": order_number}, lookup_order(order_number)),
            _tool_result("check_refund_policy", {"days_since_delivery": 12}, check_refund_policy(12)),
            _tool_result("issue_refund", {"order_id": order_number, "amount": 84.99}, issue_refund(order_number, 84.99)),
        ]
        response = f"I found order {order_number}. It is within policy, and I have issued your refund for $84.99."
        if mode == "regression":
            steps.append(
                _tool_result(
                    "escalate_to_human",
                    {"priority": "normal", "reason": "refund_processed"},
                    escalate_to_human("normal", "refund_processed"),
                )
            )
            response = (
                f"I found order {order_number}. Your refund for $84.99 has been submitted "
                "and a human specialist will also review it."
            )
        return {"response": response, "steps": steps}

    if "charge" in query or "billing" in query or "129" in query:
        steps = [_tool_result("lookup_account", {"customer": "billing-dispute"}, lookup_account("billing-dispute"))]
        if mode == "regression":
            return {
                "response": "I understand the concern. I will flag this billing issue for follow-up within 24 to 48 hours.",
                "steps": steps,
            }
        steps.append(
            _tool_result(
                "check_billing_history",
                {"account_id": "acct_8821"},
                check_billing_history("acct_8821"),
            )
        )
        return {
            "response": "That $129 charge is your annual renewal from March 3. Auto-renewal was enabled on the account.",
            "steps": steps,
        }

    if "outage" in query or "vip" in query:
        steps = [
            _tool_result("lookup_account", {"customer": "vip-outage"}, lookup_account("vip-outage")),
            _tool_result("check_service_status", {"service": "dashboards"}, check_service_status("dashboards")),
            _tool_result(
                "escalate_to_human",
                {"priority": "critical", "reason": "vip_outage"},
                escalate_to_human("critical", "vip_outage"),
            ),
        ]
        return {
            "response": "I confirmed a current dashboard outage affecting your region and escalated this to the on-call team with VIP priority.",
            "steps": steps,
        }

    return {
        "response": "Please describe the support issue you need help with.",
        "steps": [],
    }


def _run_llm_support_agent(req: ExecuteRequest, mode: str) -> Dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is required for AGENT_BACKEND=openai")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    messages = [{"role": "system", "content": _support_prompt(mode)}] + _support_messages(req)
    tools = _tool_schemas()
    steps: List[Dict[str, Any]] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for _ in range(6):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
        )
        if response.usage:
            total_prompt_tokens += response.usage.prompt_tokens or 0
            total_completion_tokens += response.usage.completion_tokens or 0

        choice = response.choices[0].message
        tool_calls = choice.tool_calls or []
        assistant_text = choice.content or ""
        assistant_payload: Dict[str, Any] = {"role": "assistant"}
        if assistant_text:
            assistant_payload["content"] = assistant_text
        if tool_calls:
            assistant_payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in tool_calls
            ]
        messages.append(assistant_payload)

        if not tool_calls:
            return {
                "response": assistant_text.strip() or "No response generated.",
                "steps": steps,
                "model": model,
                "tokens": {"input": total_prompt_tokens, "output": total_completion_tokens},
                "cost": 0.0,
            }

        for call in tool_calls:
            name = call.function.name
            if name not in TOOL_REGISTRY:
                continue
            parsed_args = json.loads(call.function.arguments or "{}")
            normalized_args = _normalize_tool_args(name, parsed_args, req)
            result = TOOL_REGISTRY[name](**normalized_args)
            steps.append(_tool_result(name, normalized_args, result))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                }
            )

    return {
        "response": "I reached the tool-call limit before completing the response.",
        "steps": steps,
        "model": model,
        "tokens": {"input": total_prompt_tokens, "output": total_completion_tokens},
        "cost": 0.0,
    }


def _backend() -> str:
    configured = os.environ.get("AGENT_BACKEND", "auto").lower()
    if configured != "auto":
        return configured
    return "openai" if os.environ.get("OPENAI_API_KEY") else "mock"


@app.get("/health")
async def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "mode": os.environ.get("AGENT_MODE", "baseline"),
        "backend": _backend(),
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
    }


@app.post("/execute")
async def execute(req: ExecuteRequest) -> Dict[str, Any]:
    mode = os.environ.get("AGENT_MODE", "baseline").lower()
    backend = _backend()

    if backend == "openai":
        result = _run_llm_support_agent(req, mode)
    else:
        result = _mock_agent_response(req, mode)
        result["model"] = "mock-support-agent"
        result["tokens"] = {"input": 0, "output": 0}
        result["cost"] = 0.0

    result["backend"] = backend
    return result
