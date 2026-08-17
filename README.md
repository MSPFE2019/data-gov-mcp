# data.gov MCP server for Copilot Studio

This MCP server gives Microsoft Copilot Studio agents read-only access to federal APIs that use the `api.data.gov` authentication model.

The GitHub repository contains the source code only. Copilot Studio cannot connect directly to a GitHub repository; deploy the server to a public HTTPS host first.

## MCP tools

- `call_federal_api`: Make a guarded HTTPS GET request to a `.gov` or `.mil` API.
- `get_rate_limit_info`: Call an endpoint and expose the `X-RateLimit-*` headers.

## Required environment variables

| Variable | Purpose |
| --- | --- |
| `DATA_GOV_API_KEY` | Your outbound data.gov key. Use `DEMO_KEY` only for light testing. |
| `MCP_SERVER_API_KEY` | A separate secret that Copilot Studio sends to this MCP server. |
| `MCP_TRANSPORT` | Set to `streamable-http` for Copilot Studio. |

Optional variables include `MCP_HOST` (default `127.0.0.1`), `MCP_PORT` (default `8000`), `MCP_PATH` (default `/mcp`), `MCP_ALLOWED_HOSTS` (comma-separated host allowlist), and `DATA_GOV_ALLOWED_HOSTS` (comma-separated federal API host allowlist). Set `MCP_HOST=0.0.0.0` only inside a container behind HTTPS ingress.

Do not use the data.gov key as the MCP server key. Store both as deployment secrets.

## Deploy with Docker

Build and run locally:

```powershell
docker build -t data-gov-mcp .
docker run --rm -p 8000:8000 `
  -e MCP_TRANSPORT=streamable-http `
  -e MCP_SERVER_API_KEY="replace-with-a-long-random-secret" `
  -e DATA_GOV_API_KEY="your-data-gov-key" `
  data-gov-mcp
```

The local MCP endpoint is:

`http://localhost:8000/mcp`

Copilot Studio requires a publicly reachable HTTPS endpoint. Azure Container Apps, Azure App Service, or another HTTPS container host can run the included `Dockerfile`. Configure the deployment to expose port `8000`, set the required environment variables as secrets, and use the resulting URL ending in `/mcp`.

For production, set `MCP_ALLOWED_HOSTS` to the exact public host and keep `MCP_SERVER_API_KEY` out of source control and container images.

## Add the server to Microsoft Copilot Studio

Microsoft currently supports the **Streamable HTTP** transport for existing MCP servers. SSE is no longer supported for Copilot Studio.

1. Open the agent in Copilot Studio.
2. Turn on **Generative orchestration**.
3. Open **Tools** and select **Add a tool** > **New tool** > **Model Context Protocol**.
4. Enter:
   - **Server name:** `data.gov Federal APIs`
   - **Description:** `Read-only access to approved federal APIs using the data.gov API gateway.`
   - **Server URL:** `https://YOUR_PUBLIC_HOST/mcp`
5. Select **API key** authentication.
6. Select **Header** and set the header name to `X-MCP-API-Key`.
7. Enter the same value configured in the deployment's `MCP_SERVER_API_KEY`.
8. Select **Create**, choose **Create a new connection**, then select **Add to agent**.
9. Review the discovered tools and test the agent with a narrow request, such as asking for one current record from a known federal API.

The server uses its private `DATA_GOV_API_KEY` when calling the downstream federal API. Do not ask Copilot Studio users to provide that key.

## Local stdio mode

For local MCP clients that launch a process directly, stdio remains available:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
$env:DATA_GOV_API_KEY = "DEMO_KEY"
py server.py
```

Leave `MCP_TRANSPORT` unset for stdio mode. Use `MCP_TRANSPORT=streamable-http` only when running as a network service.

## Security notes

- Only HTTPS federal hosts are allowed by default for downstream requests.
- Private, loopback, link-local, multicast, and reserved downstream addresses are rejected.
- Responses are limited to 5 MB to protect server and agent memory.
- The Copilot Studio-facing endpoint requires `X-MCP-API-Key`.
- Caller-supplied `api_key` query parameters are rejected; only the server-held key is used.
- The data.gov API key is sent only from the server to the downstream API and is never returned as a tool result.
- Apply Power Platform data policies to control external connector access in Copilot Studio.

References:

- [Connect an existing MCP server to Copilot Studio](https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent)
- [Extend an agent with MCP](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-mcp)
- [api.data.gov developer manual](https://api.data.gov/docs/developer-manual/)
