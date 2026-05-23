"""Runtime compatibility shims for CI and local development.

AgentScope has changed its public import paths across versions.  Older 0.x
releases expose ``AgentBase`` from ``agentscope.agents`` only, while newer
releases also provide ``agentscope.agent``.  Some tests intentionally use the
newer import path; this shim keeps those tests runnable with the older package
that is available in local/dev environments.
"""

from __future__ import annotations

import sys
import types

try:  # pragma: no cover - exercised during interpreter startup
    import agentscope.agent  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    try:
        from agentscope.agents import AgentBase
    except Exception:
        AgentBase = None  # type: ignore[assignment]

    if AgentBase is not None:
        module = types.ModuleType("agentscope.agent")
        module.AgentBase = AgentBase
        sys.modules.setdefault("agentscope.agent", module)
