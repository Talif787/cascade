from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from cascade.application.copilot.commands import AskCommand
from cascade.application.copilot.service import CopilotApplicationService
from cascade.application.governance.queries import (
    CostReportQuery,
    GetLineageQuery,
    ListSlosQuery,
)
from cascade.application.governance.service import GovernanceApplicationService
from cascade.application.serving.commands import (
    FilterInput,
    MeasureInput,
    RunQueryCommand,
)
from cascade.application.serving.service import ServingApplicationService


@dataclass(frozen=True, slots=True)
class ToolContext:
    serving: ServingApplicationService
    governance: GovernanceApplicationService
    copilot: CopilotApplicationService


ToolHandler = Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    scope: str
    input_schema: dict[str, Any]
    handler: ToolHandler


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


async def _list_serving_views(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    entries = await ctx.serving.get_catalog()
    return {
        "views": [
            {
                "id": entry.id,
                "name": entry.name,
                "columns": [
                    {"name": c.name, "type": c.type, "role": c.role} for c in entry.columns
                ],
            }
            for entry in entries
        ]
    }


async def _query_serving_view(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    command = RunQueryCommand(
        view_id=str(args["view_id"]),
        dimensions=tuple(args.get("dimensions", [])),
        measures=tuple(
            MeasureInput(column=m["column"], aggregation=m["aggregation"])
            for m in args.get("measures", [])
        ),
        filters=tuple(
            FilterInput(column=f["column"], op=f["op"], values=tuple(f.get("values", [])))
            for f in args.get("filters", [])
        ),
        limit=int(args.get("limit", 100)),
    )
    result = await ctx.serving.run_query(command)
    return {"columns": result.columns, "rows": result.rows, "row_count": result.row_count}


async def _ask(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    answer = await ctx.copilot.ask(
        AskCommand(
            question=str(args["question"]),
            view_id=args.get("view_id"),
            view_name=args.get("view_name"),
            execute=bool(args.get("execute", True)),
        )
    )
    return {
        "id": answer.id,
        "status": answer.status,
        "rejection_reason": answer.rejection_reason,
        "columns": answer.columns,
        "rows": answer.rows,
        "row_count": answer.row_count,
    }


async def _lineage(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    view = await ctx.governance.get_lineage(
        GetLineageQuery(asset_kind=str(args["asset_kind"]), asset_id=str(args["asset_id"]))
    )
    return {
        "root": view.root,
        "nodes": [dataclasses.asdict(n) for n in view.nodes],
        "edges": [dataclasses.asdict(e) for e in view.edges],
    }


async def _list_slos(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    page = await ctx.governance.list_slos(
        ListSlosQuery(
            asset_kind=args.get("asset_kind"),
            status=args.get("status"),
            state=args.get("state"),
            size=int(args.get("size", 20)),
        )
    )
    return {
        "total": page.total,
        "slos": [
            {
                "id": s.id,
                "name": s.name,
                "asset": f"{s.asset_kind}:{s.asset_id}",
                "status": s.status,
                "state": s.state,
                "breach_count": s.breach_count,
            }
            for s in page.items
        ],
    }


async def _cost_report(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    report = await ctx.governance.cost_report(CostReportQuery())
    return {
        "total_cents": report.total_cents,
        "by_category": [dataclasses.asdict(line) for line in report.by_category],
        "by_asset": [dataclasses.asdict(line) for line in report.by_asset],
    }


_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="cascade_list_serving_views",
        description="List the serving views available to query, with their columns.",
        scope="serving:read",
        input_schema=_object({}),
        handler=_list_serving_views,
    ),
    Tool(
        name="cascade_query_serving_view",
        description="Run a governed analytics query against a serving view by id.",
        scope="serving:read",
        input_schema=_object(
            {
                "view_id": {"type": "string"},
                "dimensions": {"type": "array", "items": {"type": "string"}},
                "measures": {"type": "array", "items": {"type": "object"}},
                "filters": {"type": "array", "items": {"type": "object"}},
                "limit": {"type": "integer"},
            },
            required=["view_id"],
        ),
        handler=_query_serving_view,
    ),
    Tool(
        name="cascade_ask",
        description="Ask a natural-language analytics question over a serving view.",
        scope="copilot:write",
        input_schema=_object(
            {
                "question": {"type": "string"},
                "view_name": {"type": "string"},
                "view_id": {"type": "string"},
                "execute": {"type": "boolean"},
            },
            required=["question"],
        ),
        handler=_ask,
    ),
    Tool(
        name="cascade_lineage",
        description="Get the lineage graph rooted at a dataset or serving view.",
        scope="governance:read",
        input_schema=_object(
            {"asset_kind": {"type": "string"}, "asset_id": {"type": "string"}},
            required=["asset_kind", "asset_id"],
        ),
        handler=_lineage,
    ),
    Tool(
        name="cascade_list_slos",
        description="List freshness SLOs and their current compliance state.",
        scope="governance:read",
        input_schema=_object(
            {
                "asset_kind": {"type": "string"},
                "status": {"type": "string"},
                "state": {"type": "string"},
                "size": {"type": "integer"},
            }
        ),
        handler=_list_slos,
    ),
    Tool(
        name="cascade_cost_report",
        description="Get the cost report rolled up by category and by asset.",
        scope="governance:read",
        input_schema=_object({}),
        handler=_cost_report,
    ),
)

TOOLS: dict[str, Tool] = {tool.name: tool for tool in _TOOLS}


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
        }
        for tool in _TOOLS
    ]
