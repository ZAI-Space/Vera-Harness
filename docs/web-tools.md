# Tool registry and web providers

Bash handles existing file reads, edits, searches and builds in the selected
execution environment. The tool registry associates a named capability with a
JSON Schema and execution handler. The model receives the same declarations that
the agent uses to validate and route calls. Tool call IDs connect the results to
their requests in the saved trajectory.

The web tools follow the [Hermes provider design](https://hermes-agent.nousresearch.com/docs/developer-guide/web-search-provider-plugin).
Choose search and extraction providers independently.

| Provider | Search | Extract | Configuration |
| --- | --- | --- | --- |
| [SearXNG](https://docs.searxng.org/dev/search_api) | Yes | | `SEARXNG_URL`, with JSON enabled on the instance |
| [Firecrawl](https://docs.firecrawl.dev/api-reference/endpoint/search) | Yes | Markdown | `FIRECRAWL_API_KEY` |
| [Tavily](https://docs.tavily.com/documentation/api-reference/endpoint/search) | Yes | Markdown | `TAVILY_API_KEY` |

## Use from Git Bash

```bash
export SEARXNG_URL=http://127.0.0.1:8080
bash scripts/start.sh -c mini.yaml -c web.search_provider=searxng
```

After setting `FIRECRAWL_API_KEY`, add a separate extraction provider:

```bash
bash scripts/start.sh -c mini.yaml \
  -c web.search_provider=searxng -c web.extract_provider=firecrawl
```

Set both providers to `tavily` to use a single Tavily account. From PowerShell,
run `./start.cmd` with the same CLI options and set endpoint variables with
`$env:VARIABLE = 'value'`. Keep API keys in the process environment or existing
global configuration rather than passing them as CLI or YAML arguments.

`web_search` accepts a query and an optional result limit of 1–8. It returns
source URLs, titles and snippets. `web_extract` accepts one public HTTP(S) URL and
returns up to 6,000 characters of Markdown with a truncation indicator. The
configured provider receives the query or URL. In `confirm` mode the Agent
shows those arguments and asks before submitting them. The Bash whitelist
does not apply to named tools. Provider errors become tool observations.

The CLI adds only the web capabilities configured for the run. Use a native
tool-calling model adapter such as LiteLLM or OpenRouter. The text-action
adapters accept Bash commands in text and cannot advertise named web tools.
The application contacts configured provider APIs. Providers fetch the source
pages and apply their own network restrictions.

## Register another capability

```python
from minisweagent.agents.default import DefaultAgent
from minisweagent.tools import ToolSpec, make_tool_registry

registry = make_tool_registry(environment)
registry.register(
    ToolSpec("lookup_status", "Read the local application status", {"type": "object"}),
    lambda arguments: {"output": "ready", "returncode": 0, "exception_info": ""},
)
agent = DefaultAgent(model, environment, tool_registry=registry, **agent_config)
```

Use one model adapter instance per registry. To extend web backends, implement
`WebProvider.search`, `WebProvider.extract`, or both, then pass the provider to
`register_web_tools`. This keeps the model-facing names and arguments consistent
across provider changes.
