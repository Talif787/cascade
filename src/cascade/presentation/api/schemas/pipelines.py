from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cascade.application.pipelines.dto import PipelineView


class ConnectorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, examples=["postgres_cdc"])
    resource: str = Field(min_length=1, max_length=512, examples=["public.orders"])
    options: dict[str, str] = Field(default_factory=dict)


class RegisterPipelineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=63, examples=["orders-cdc-to-lake"])
    source: ConnectorPayload
    sink: ConnectorPayload
    description: str = Field(default="", max_length=1024)


class ConnectorResponse(BaseModel):
    type: str
    resource: str
    options: dict[str, str]


class PipelineResponse(BaseModel):
    id: str
    name: str
    source: ConnectorResponse
    sink: ConnectorResponse
    status: str
    description: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_view(cls, view: PipelineView) -> PipelineResponse:
        return cls(
            id=view.id,
            name=view.name,
            source=ConnectorResponse(
                type=view.source.type, resource=view.source.resource, options=view.source.options
            ),
            sink=ConnectorResponse(
                type=view.sink.type, resource=view.sink.resource, options=view.sink.options
            ),
            status=view.status,
            description=view.description,
            version=view.version,
            created_at=view.created_at,
            updated_at=view.updated_at,
        )
