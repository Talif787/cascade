from __future__ import annotations

from typing import Any

from httpx import AsyncClient

_MCP = "/mcp"
_DATASETS = "/api/v1/datasets"
_VIEWS = "/api/v1/serving-views"


def _rpc(method: str, params: dict[str, Any] | None = None, rid: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}


async def _ready_view(client: AsyncClient) -> dict[str, Any]:
    ds = await client.post(
        _DATASETS,
        json={
            "name": "gold.orders",
            "layer": "gold",
            "transformation": {"engine": "dbt", "identifier": "gold_orders"},
        },
    )
    view = await client.post(
        _VIEWS,
        json={
            "name": "analytics.orders",
            "source_dataset_id": ds.json()["id"],
            "engine": "merge_tree",
            "columns": [{"name": "region", "type": "string", "role": "dimension"}],
            "order_by": ["region"],
        },
    )
    body = view.json()
    await client.post(f"{_VIEWS}/{body['id']}/sync")
    return body


async def test_initialize(client: AsyncClient) -> None:
    response = await client.post(_MCP, json=_rpc("initialize"))
    body = response.json()
    assert body["result"]["serverInfo"]["name"] == "cascade-governed-data"
    assert "protocolVersion" in body["result"]


async def test_tools_list(client: AsyncClient) -> None:
    response = await client.post(_MCP, json=_rpc("tools/list"))
    names = {t["name"] for t in response.json()["result"]["tools"]}
    assert "cascade_list_serving_views" in names
    assert "cascade_ask" in names
    assert "cascade_cost_report" in names


async def test_unknown_method(client: AsyncClient) -> None:
    response = await client.post(_MCP, json=_rpc("does/not/exist"))
    assert response.json()["error"]["code"] == -32601


async def test_call_list_serving_views(client: AsyncClient) -> None:
    await _ready_view(client)
    response = await client.post(
        _MCP, json=_rpc("tools/call", {"name": "cascade_list_serving_views", "arguments": {}})
    )
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["views"][0]["name"] == "analytics.orders"


async def test_call_query_serving_view(client: AsyncClient) -> None:
    view = await _ready_view(client)
    response = await client.post(
        _MCP,
        json=_rpc(
            "tools/call",
            {
                "name": "cascade_query_serving_view",
                "arguments": {"view_id": view["id"], "dimensions": ["region"]},
            },
        ),
    )
    result = response.json()["result"]
    assert result["isError"] is False
    assert "region" in result["structuredContent"]["columns"]


async def test_call_cost_report(client: AsyncClient) -> None:
    response = await client.post(
        _MCP, json=_rpc("tools/call", {"name": "cascade_cost_report", "arguments": {}})
    )
    result = response.json()["result"]
    assert result["isError"] is False
    assert "total_cents" in result["structuredContent"]


async def test_unknown_tool_is_invalid_params(client: AsyncClient) -> None:
    response = await client.post(
        _MCP, json=_rpc("tools/call", {"name": "cascade_nope", "arguments": {}})
    )
    assert response.json()["error"]["code"] == -32602


async def test_tool_error_is_reported_in_result(client: AsyncClient) -> None:
    # querying a nonexistent view id surfaces as a tool error, not a protocol error
    response = await client.post(
        _MCP,
        json=_rpc(
            "tools/call",
            {
                "name": "cascade_query_serving_view",
                "arguments": {"view_id": "9b3c9215-e635-4d07-a379-ca21864ebddb"},
            },
        ),
    )
    result = response.json()["result"]
    assert result["isError"] is True


async def test_scope_enforced_per_tool(readonly_client: AsyncClient) -> None:
    # the read-only principal lacks copilot:write, which cascade_ask requires
    response = await readonly_client.post(
        _MCP,
        json=_rpc(
            "tools/call",
            {
                "name": "cascade_ask",
                "arguments": {"question": "hi", "view_name": "analytics.orders"},
            },
        ),
    )
    assert response.json()["error"]["code"] == -32001


async def test_missing_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.post(_MCP, json=_rpc("tools/list"), headers={"Authorization": ""})
    assert response.status_code == 401
