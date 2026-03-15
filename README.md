# EvalView Support Automation Template

LLM-backed support automation agent with EvalView regression guardrails.

This starter is built around a problem most agent teams actually have:

**the endpoint still returns 200, the answer still sounds plausible, but the agent silently changed tool use or skipped a key support workflow**

The agent handles three realistic support scenarios:
- refund requests
- billing disputes
- VIP outage triage

## Why this repo exists

Most support-agent demos prove that an agent can answer a ticket.
This repo proves something more useful:

**can you catch the bad deploy before it hits customers?**

That is why the repo ships with:
- committed EvalView tests
- committed baselines
- a clean regression mode
- a real LLM-backed path for teams that want credibility

## Fastest path

No API key:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install evalview
make run
```

Keep that terminal running. In a second terminal:

```bash
source .venv/bin/activate
make check
```

Real LLM-backed path:

```bash
cp .env.example .env
export OPENAI_API_KEY=your-key
make llm
```

Keep that terminal running. In a second terminal:

```bash
source .venv/bin/activate
evalview snapshot tests
evalview check tests
```

In baseline mode it uses tools the way you would expect a real support agent to behave. In regression mode it makes two subtle but costly mistakes:
- it escalates every refund after already issuing the refund
- it skips billing-history lookup and gives a vague follow-up answer

## What This Repo Gives You

- FastAPI HTTP agent with a real tool-using LLM path
- editable support playbook in `agent/support_playbook.md`
- deterministic fallback mode so the repo still runs without API keys
- EvalView regression tests for refund, billing, and outage flows
- committed golden baselines for the fallback mode
- GitHub Actions regression check
- one-command baseline vs regression demo

## Agent Modes

The repo supports two backends:

- `mock`
  - deterministic fallback
  - no API key needed
  - used for the committed goldens and CI by default
- `openai`
  - real LLM-backed support agent
  - requires `OPENAI_API_KEY`
  - uses tool calling to choose actions and produce the final response

Backend selection:

- default: `auto`
- if `OPENAI_API_KEY` is set, the app uses the OpenAI backend
- otherwise it falls back to the deterministic backend

You can also force it:

```bash
AGENT_BACKEND=mock
AGENT_BACKEND=openai
```

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install evalview
make run
```

Keep that terminal running. In a second terminal:

```bash
source .venv/bin/activate
make check
```

That should pass against the committed baseline in mock mode.

## Run The Real LLM Agent

```bash
export OPENAI_API_KEY=your-key
make llm
```

This starts the same support agent, but now the model decides:
- when to ask for missing information
- which tools to call
- what to say after the tool results come back
- how to follow your support playbook in `agent/support_playbook.md`

If you want to use EvalView against that LLM-backed behavior, run:

```bash
evalview snapshot tests
evalview check tests
```

That will create baselines for your local model-backed version of the agent.

## Make It Your Own

The fastest way to adapt this repo is to edit:

- `agent/support_playbook.md`
  - policy and escalation rules
- `tests/*.yaml`
  - the user flows you care about
- `agent/app.py`
  - tool implementations and business data

This keeps the example useful for real teams: you can swap the support policy and keep the same EvalView regression loop.

## See A Real Regression

Mock backend:

```bash
make regress
evalview check tests
```

LLM backend:

```bash
export OPENAI_API_KEY=your-key
make llm-regress
evalview check tests
```

You should see:
- `TOOLS_CHANGED` on the refund flow because `escalate_to_human` was added
- `REGRESSION` on the billing dispute flow because the agent stops calling `check_billing_history`

## What EvalView catches here

- refund flow:
  - unnecessary human escalation after a successful refund
- billing dispute:
  - missing billing-history lookup before answering
- VIP outage:
  - correct verification and escalation path for high-priority support

These are the kinds of regressions that still sound plausible in manual spot checks, but should absolutely block deploys.

## Why This Example Is Useful

This is a support agent people can actually relate to:
- it asks for missing information before acting
- it checks history before answering disputes
- it escalates high-priority incidents correctly
- it shows how regressions can be operational, not just textual

That makes it a good fit for teams evaluating whether EvalView can guard real production workflows.

## Files

- `agent/app.py`: FastAPI support automation agent with OpenAI tool-calling backend + mock fallback
- `agent/support_playbook.md`: editable support policy the LLM follows
- `tests/`: EvalView regression tests
- `.evalview/config.yaml`: local adapter config
- `.evalview/golden/`: committed mock-mode baselines
- `.github/workflows/evalview.yml`: CI workflow
- `Makefile`: simple local commands

## Refresh The Baseline

If you intentionally change the agent and want to keep the new behavior:

```bash
evalview snapshot tests
```

Then commit the updated `.evalview/golden/` files.
