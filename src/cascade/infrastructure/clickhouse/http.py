from __future__ import annotations

from typing import Any

import httpx

from cascade.application.serving.runtime import (
    ClickHouseRuntime,
    ClickHouseRuntimeError,
    CompiledQuery,
    QueryResult,
    ServingTableSpec,
    SyncResult,
)
from cascade.infrastructure.clickhouse.sql_builder import (
    build_create_table_sql,
    build_select_sql,
)


class ClickHouseHttpRuntime(ClickHouseRuntime):
    """Adapter for the ClickHouse HTTP interface.

    Statements are posted as SQL; the query path requests JSON so results can be
    parsed into rows. A sync issues an INSERT ... SELECT from the source table.
    """

    def __init__(
        self,
        base_url: str,
        database: str,
        username: str,
        password: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._database = database
        self._auth = (username, password)
        self._timeout = timeout_seconds

    async def create_or_replace(self, spec: ServingTableSpec) -> None:
        await self._execute(build_create_table_sql(spec))

    async def sync(self, spec: ServingTableSpec) -> SyncResult:
        columns = ", ".join(c.name for c in spec.columns)
        insert = f"INSERT INTO {spec.name} ({columns}) SELECT {columns} FROM {spec.source_table}"
        await self._execute(insert)
        count = await self._scalar(f"SELECT count() FROM {spec.name}")
        return SyncResult(sync_ref=f"ch-{spec.name}", row_count=int(count))

    async def drop(self, name: str) -> None:
        await self._execute(f"DROP TABLE IF EXISTS {name}")

    async def query(self, compiled: CompiledQuery) -> QueryResult:
        sql = build_select_sql(compiled) + " FORMAT JSON"
        payload = await self._post(sql)
        data = payload.get("data", [])
        meta = payload.get("meta", [])
        columns = tuple(col["name"] for col in meta)
        rows = tuple(dict(row) for row in data)
        return QueryResult(columns=columns, rows=rows)

    async def _execute(self, sql: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            response = await client.post(
                self._base_url, params={"database": self._database}, content=sql
            )
        if response.status_code >= 400:
            raise ClickHouseRuntimeError(
                f"statement failed: {response.status_code} {response.text}"
            )

    async def _scalar(self, sql: str) -> str:
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            response = await client.post(
                self._base_url, params={"database": self._database}, content=sql
            )
        if response.status_code >= 400:
            raise ClickHouseRuntimeError(
                f"scalar query failed: {response.status_code} {response.text}"
            )
        return response.text.strip() or "0"

    async def _post(self, sql: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            response = await client.post(
                self._base_url, params={"database": self._database}, content=sql
            )
        if response.status_code >= 400:
            raise ClickHouseRuntimeError(f"query failed: {response.status_code} {response.text}")
        payload: dict[str, Any] = response.json()
        return payload
