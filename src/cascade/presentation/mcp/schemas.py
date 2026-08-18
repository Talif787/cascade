from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "cascade-governed-data"
SERVER_VERSION = "0.8.0"


class JsonRpcRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    jsonrpc: str = Field(default="2.0")
    id: int | str | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcError(BaseModel):
    code: int
    message: str


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: dict[str, Any] | None = None
    error: JsonRpcError | None = None


# JSON-RPC error codes used by this server.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# Application-defined: the caller lacks the scope a tool requires.
PERMISSION_DENIED = -32001


def ok(request_id: int | str | None, result: dict[str, Any]) -> JsonRpcResponse:
    return JsonRpcResponse(id=request_id, result=result)


def err(request_id: int | str | None, code: int, message: str) -> JsonRpcResponse:
    return JsonRpcResponse(id=request_id, error=JsonRpcError(code=code, message=message))
