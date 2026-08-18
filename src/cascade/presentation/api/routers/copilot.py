from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from cascade.application.copilot.commands import (
    AskCommand,
    GetCopilotQueryQuery,
    ListCopilotQueriesQuery,
)
from cascade.infrastructure.security.jwt import Principal
from cascade.presentation.api.dependencies import CopilotServiceDep
from cascade.presentation.api.schemas.common import PageMeta, PaginatedResponse
from cascade.presentation.api.schemas.copilot import (
    AskRequest,
    AskResponse,
    CopilotQueryResponse,
)
from cascade.presentation.api.security import require_scopes

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])

WriteScope = Annotated[Principal, Depends(require_scopes("copilot:write"))]
ReadScope = Annotated[Principal, Depends(require_scopes("copilot:read"))]


@router.post("/ask", response_model=AskResponse, summary="Ask a question in natural language")
async def ask(
    payload: AskRequest,
    service: CopilotServiceDep,
    _principal: WriteScope,
) -> AskResponse:
    answer = await service.ask(
        AskCommand(
            question=payload.question,
            view_id=payload.view_id,
            view_name=payload.view_name,
            execute=payload.execute,
        )
    )
    return AskResponse.from_view(answer)


@router.get(
    "/queries",
    response_model=PaginatedResponse[CopilotQueryResponse],
    summary="List past copilot queries",
)
async def list_queries(
    service: CopilotServiceDep,
    _principal: ReadScope,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    view_id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    descending: Annotated[bool, Query()] = True,
) -> PaginatedResponse[CopilotQueryResponse]:
    result = await service.list_queries(
        ListCopilotQueriesQuery(
            status=status_filter,
            view_id=view_id,
            page=page,
            size=size,
            descending=descending,
        )
    )
    return PaginatedResponse[CopilotQueryResponse](
        items=[CopilotQueryResponse.from_view(item) for item in result.items],
        meta=PageMeta(page=result.page, size=result.size, total=result.total, pages=result.pages),
    )


@router.get(
    "/queries/{query_id}",
    response_model=CopilotQueryResponse,
    summary="Get one copilot query",
)
async def get_query(
    service: CopilotServiceDep,
    _principal: ReadScope,
    query_id: Annotated[str, Path()],
) -> CopilotQueryResponse:
    view = await service.get_query(GetCopilotQueryQuery(query_id=query_id))
    return CopilotQueryResponse.from_view(view)
