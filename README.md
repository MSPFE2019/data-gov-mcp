# data.gov MCP server

An MCP server for calling read-only federal APIs through the api.data.gov authentication model.

## Tools

- `call_federal_api`: Make a guarded HTTPS GET request to a `.gov` or `.mil` API.
- `get_rate_limit_info`: Call an endpoint and expose the `X-RateLimit-*` headers.

## Setup

1. Create a virtual environment and install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   py -m pip install -r requirements.txt
   ```

2. Set `DATA_GOV_API_KEY` to a key from <https://api.data.gov/signup/>. `DEMO_KEY` is used when omitted, but has much lower limits.

3. Start the server over stdio:

   ```powershell
   py server.py
   ```

## MCP client configuration

Use an absolute Windows path in the client configuration:

```json
{
  "mcpServers": {
    "data-gov": {
      "command": "C:\\path\\to\\data-gov-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\data-gov-mcp\\server.py"],
      "env": {
        "DATA_GOV_API_KEY": "${DATA_GOV_API_KEY}"
      }
    }
  }
}
```

The server only permits HTTPS federal hosts by default and rejects private or loopback destinations. Set `DATA_GOV_ALLOWED_HOSTS` when a stricter explicit host allowlist is preferred.
