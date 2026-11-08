"""Agents: let the model do things, within limits you set.

Datas ships a deliberately small agent runner rather than a framework: a tool-calling
loop over the OpenAI-compatible endpoint (local, pooled or remote) with a sandboxed
workspace and explicit permissions. Because every provider speaks the same API, any
external agent framework (smolagents, Open Interpreter, LangGraph, your own) can be
pointed at ``http://127.0.0.1:8420/v1`` instead — see docs/AGENTS.md.
"""

from datas.agents.runner import AgentConfig, run_agent  # noqa: F401
