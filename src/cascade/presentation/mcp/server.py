from __future__ import annotations

import json
from typing import Any

import structlog

from cascade.application.common.errors import (
    ApplicationError,
    ConflictError,
    InputValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from cascade.domain.common.errors import DomainError
from cascade.infrastructure.security.jwt import Principal
from cascade.presentation.mcp.schemas import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PERMISSION_DENIED,
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    JsonRpcRequest,
    JsonRpcResponse,
    err,
    ok,
)
from cascade.presentation.mcp.tools import TOOLS, ToolContext, tool_definitions

_logger = structlog.get_logger(__name__)


async def dispatch(
    request: JsonRpcRequest, principal: Principal, context: ToolContext
) -> JsonRpcResponse | None:
    """Handle one JSON-RPC request. Returns None for notifications."""

    if request.method == "initialize":
        return ok(
            request.id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if request.method in ("notifications/initialized", "initialized"):
        return None

    if request.method == "tools/list":
        return ok(request.id, {"tools": tool_definitions()})

    if request.method == "tools/call":
        return await _call_tool(request, principal, context)

    return err(request.id, METHOD_NOT_FOUND, f"unknown method {request.method!r}")


async def _call_tool(
    request: JsonRpcRequest, principal: Principal, context: ToolContext
) -> JsonRpcResponse:
    name = request.params.get("name")
    arguments = request.params.get("arguments", {})
    if not isinstance(name, str) or name not in TOOLS:
        return err(request.id, INVALID_PARAMS, f"unknown tool {name!r}")
    if not isinstance(arguments, dict):
        return err(request.id, INVALID_PARAMS, "arguments must be an object")

    tool = TOOLS[name]
    if not principal.has_scope(tool.scope):
        return err(
            request.id,
            PERMISSION_DENIED,
            f"tool {name!r} requires scope {tool.scope!r}",
        )

    try:
        result = await tool.handler(context, arguments)
    except (InputValidationError, KeyError, ValueError) as exc:
        return _tool_error(request.id, f"invalid arguments: {exc}")
    except NotFoundError as exc:
        return _tool_error(request.id, str(exc))
    except (ConflictError, DomainError) as exc:
        return _tool_error(request.id, str(exc))
    except PermissionDeniedError as exc:
        return err(request.id, PERMISSION_DENIED, str(exc))
    except ApplicationError as exc:
        return err(request.id, INTERNAL_ERROR, str(exc))

    return ok(
        request.id,
        {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "structuredContent": result,
            "isError": False,
        },
    )


def _tool_error(request_id: int | str | None, message: str) -> JsonRpcResponse:
    """A tool-level error is reported inside a successful JSON-RPC result.

    The MCP convention is that tool failures are returned as result content with
    isError true, so the model can read and react to them rather than the call
    itself failing at the protocol level.
    """

    payload: dict[str, Any] = {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }
    return ok(request_id, payload)
