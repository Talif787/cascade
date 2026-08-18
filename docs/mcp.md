# The governed data MCP server

The MCP server exposes the platform to AI agents through the Model Context Protocol, so an
agent can discover and use the platform's capabilities as tools. It is a thin presentation
layer over the application services that already exist: it adds no new business logic, only a
protocol surface and per-tool authorization.

## Protocol

The server speaks JSON-RPC 2.0 over a single HTTP endpoint, `POST /mcp`. It implements the
core MCP methods:

- `initialize` returns the protocol version and server info.
- `tools/list` returns the tool catalog, each with a name, description, and JSON input schema.
- `tools/call` runs a named tool with arguments and returns its result.

Notifications such as `notifications/initialized` are accepted and produce no response, per
the protocol.

## Tools

Each tool maps to an existing application service and declares the scope it requires.

| Tool                          | Capability                                   | Scope              |
| ----------------------------- | -------------------------------------------- | ------------------ |
| `cascade_list_serving_views`  | List queryable serving views and columns     | `serving:read`     |
| `cascade_query_serving_view`  | Run a governed analytics query               | `serving:read`     |
| `cascade_ask`                 | Ask a natural-language question (copilot)    | `copilot:write`    |
| `cascade_lineage`             | Get the lineage graph for an asset           | `governance:read`  |
| `cascade_list_slos`           | List freshness SLOs and compliance state     | `governance:read`  |
| `cascade_cost_report`         | Get the cost report                          | `governance:read`  |

Because the tools delegate to the same services as the REST API, they inherit every
guardrail: the query tool and the copilot tool both validate against a serving view's declared
columns, and the governance tools read the same aggregates the REST endpoints do.

## Authorization

The endpoint authenticates the bearer token once, producing a principal with a set of scopes.
Each `tools/call` then checks that the principal holds the tool's required scope before
dispatching. A caller with only read scopes can list and query views and read governance data,
but cannot call `cascade_ask`, which needs `copilot:write`. A missing token is rejected at the
transport level; a missing scope is returned as a JSON-RPC error with an application-defined
code, so the agent learns it lacks permission rather than getting a silent empty result.

## Error handling

Two kinds of failure are distinguished. Protocol problems (an unknown method, an unknown tool,
malformed parameters, or a missing scope) are returned as JSON-RPC errors. Tool problems (a
view that does not exist, a query the domain rejects) are returned as a successful JSON-RPC
result whose content is marked with `isError` true. This follows the MCP convention: the model
is meant to read tool errors and adapt, so they belong in the result rather than failing the
call at the protocol layer.

## Relationship to the copilot

The MCP server and the copilot are complementary. The copilot is the natural-language entry
point; the MCP server is how an autonomous agent reaches the platform, including the copilot,
as structured tools. An agent can list views, ask a question through `cascade_ask`, and follow
up with a precise `cascade_query_serving_view` call, all within the scopes its token grants.
