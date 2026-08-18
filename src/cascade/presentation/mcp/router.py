from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import JSONResponse

from cascade.presentation.api.dependencies import (
    CopilotServiceDep,
    GovernanceServiceDep,
    ServingServiceDep,
)
from cascade.presentation.api.security import CurrentPrincipal
from cascade.presentation.mcp.schemas import (
    INVALID_REQUEST,
    JsonRpcRequest,
    err,
)
from cascade.presentation.mcp.server import dispatch
from cascade.presentation.mcp.tools import ToolContext

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("", summary="Governed data MCP endpoint (JSON-RPC 2.0)")
async def mcp_endpoint(
    request: JsonRpcRequest,
    principal: CurrentPrincipal,
    serving: ServingServiceDep,
    governance: GovernanceServiceDep,
    copilot: CopilotServiceDep,
) -> JSONResponse:
    context = ToolContext(serving=serving, governance=governance, copilot=copilot)
    if request.jsonrpc != "2.0":
        return JSONResponse(
            content=err(request.id, INVALID_REQUEST, "jsonrpc must be '2.0'").model_dump(
                exclude_none=True
            )
        )
    response = await dispatch(request, principal, context)
    if response is None:
        return JSONResponse(status_code=204, content=None)
    return JSONResponse(content=response.model_dump(exclude_none=True))
