# Building a Secure MCP Server with CrewAI: A Step-by-Step Guide

This guide walks through building the Linear-GitHub MCP server from scratch. We'll start simple and progressively add complexity: first a basic MCP server, then API integrations, then multi-agent AI with CrewAI, and finally enterprise-grade security with Keycard.

## Table of Contents

1. [Phase 1: Hello MCP](#phase-1-hello-mcp) - Basic MCP server
2. [Phase 2: Adding Real Tools](#phase-2-adding-real-tools) - Linear & GitHub integration
3. [Phase 3: The Security Problem](#phase-3-the-security-problem) - Why tokens in config files are bad
4. [Phase 4: Adding Keycard](#phase-4-adding-keycard) - OAuth & identity management
5. [Phase 5: Multi-Agent AI with CrewAI](#phase-5-multi-agent-ai-with-crewai) - Research automation
6. [Phase 6: Tool-Secured Mode](#phase-6-tool-secured-mode) - Tokens never visible to agents

---

## Phase 1: Hello MCP

### What is MCP?

MCP (Model Context Protocol) is an open standard that lets AI assistants (like Claude, Cursor, or custom agents) use external tools. Think of it as a plugin system for AI.

```
┌─────────────┐     MCP Protocol     ┌─────────────┐
│  AI Client  │ ←─────────────────→  │  MCP Server │
│  (Claude)   │   "call tool X"      │  (Your App) │
└─────────────┘                      └─────────────┘
```

### Your First MCP Server

Install FastMCP:

```bash
pip install fastmcp
```

Create `server.py`:

```python
from fastmcp import FastMCP

mcp = FastMCP("My First Server")

@mcp.tool(name="echo")
async def echo_tool(message: str) -> str:
    """Echo back a message."""
    return f"You said: {message}"

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

Run it:

```bash
python server.py
```

That's it! You now have an MCP server running at `http://localhost:8000/mcp`. Any MCP-compatible client can connect and use your `echo` tool.

### Connecting from Claude Code or Cursor

Add to your MCP client config (e.g., `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "my-server": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Now when you chat with the AI, it can use your echo tool!

---

## Phase 2: Adding Real Tools

Let's add tools that actually do something useful: read from Linear (task tracking) and GitHub (code).

### Linear Tool (GraphQL API)

```python
import httpx

@mcp.tool(name="task")
async def get_linear_task(identifier: str) -> dict:
    """Get a Linear task by identifier (e.g., 'ENG-123')."""

    # ⚠️ INSECURE: Token hardcoded!
    token = "lin_api_xxxxx"

    query = """
    query($identifier: String!) {
        issue(id: $identifier) {
            id
            identifier
            title
            description
            state { name }
        }
    }
    """

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.linear.app/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": query, "variables": {"identifier": identifier}}
        )
        return response.json()
```

### GitHub Tool (REST API)

```python
@mcp.tool(name="tree")
async def get_repo_structure(owner: str, repo: str, path: str = "") -> dict:
    """Get repository file structure."""

    # ⚠️ INSECURE: Token hardcoded!
    token = "ghp_xxxxx"

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
        )
        return response.json()
```

### The Tools So Far

| Tool | Purpose | API |
|------|---------|-----|
| `echo` | Testing | None |
| `task` | Get Linear task details | Linear GraphQL |
| `tree` | Get repo file structure | GitHub REST |
| `read` | Read file contents | GitHub REST |

This works! The AI can now:
- Look up Linear tasks
- Explore GitHub repositories
- Read source code files

But there's a **big problem**...

---

## Phase 3: The Security Problem

### What's Wrong?

Look at the code above. Those API tokens are:

1. **Hardcoded** - Anyone with the code has your credentials
2. **Single-user** - Everyone uses YOUR tokens, not their own
3. **Over-privileged** - Your personal token has access to everything you have access to
4. **Unauditable** - No way to know who did what

### The "Environment Variable" Non-Solution

```python
token = os.getenv("LINEAR_TOKEN")  # Still bad!
```

This is marginally better, but still:
- Still single-user (shared token)
- Still no audit trail
- Token sits in plaintext in your deployment config
- If you're running this for a team, whose token do you use?

### What We Actually Need

```
┌─────────────┐                           ┌─────────────┐
│   Alice     │──→ Alice's GitHub token ──→│             │
├─────────────┤                           │  MCP Server │
│    Bob      │──→ Bob's GitHub token ────→│             │
├─────────────┤                           │             │
│   Carol     │──→ Carol's GitHub token ──→│             │
└─────────────┘                           └─────────────┘
```

Each user should authenticate with their own identity, and the server should fetch tokens on their behalf. This is what **OAuth** is for.

---

## Phase 4: Adding Keycard

### What is Keycard?

Keycard is an identity and access management layer for MCP servers. It handles:

1. **User Authentication** - Who is making the request?
2. **OAuth Token Exchange** - Get API tokens for authenticated users
3. **Resource Access Control** - Which APIs can this server access?
4. **Audit Logging** - Track all token grants

### Architecture with Keycard

```
┌─────────────┐         ┌─────────────────┐         ┌─────────────┐
│  AI Client  │──JWT───→│  Keycard Zone   │         │             │
│  (Claude)   │         │                 │         │  MCP Server │
│             │         │ - Okta/Google   │         │             │
│             │         │ - GitHub OAuth  │──token─→│             │
│             │         │ - Linear OAuth  │         │             │
└─────────────┘         └─────────────────┘         └─────────────┘
```

### Setting Up Keycard

1. **Create a Zone** at keycard.cloud
2. **Add Credential Providers** (GitHub OAuth app, Linear OAuth app)
3. **Define Resources** (https://api.github.com, https://api.linear.app)
4. **Register your Application** (your MCP server)

### Updating the Server

Install the Keycard SDK:

```bash
pip install keycardai-mcp-fastmcp
```

Update `server.py`:

```python
from fastmcp import FastMCP, Context
from keycardai.mcp.integrations.fastmcp import AuthProvider, AccessContext, ClientSecret

# Create Keycard auth provider
auth_provider = AuthProvider(
    zone_id="your-zone-id",
    mcp_server_name="Linear-GitHub MCP Server",
    mcp_server_url="https://your-server.com/",
    application_credential=ClientSecret((
        os.getenv("KEYCARD_CLIENT_ID"),
        os.getenv("KEYCARD_CLIENT_SECRET")
    ))
)

# Get the auth handler for FastMCP
auth = auth_provider.get_remote_auth_provider()

# Initialize MCP with Keycard auth
mcp = FastMCP("Linear-GitHub Automation", auth=auth)
```

### Using `@auth_provider.grant()`

The magic decorator that handles OAuth:

```python
@mcp.tool(name="task")
@auth_provider.grant("https://api.linear.app")  # ← Request Linear access
async def get_linear_task(ctx: Context, identifier: str) -> dict:
    """Get a Linear task by identifier."""

    # Get the access context from Keycard
    access_ctx: AccessContext = ctx.get_state("keycardai")

    # Check for auth errors
    if access_ctx.has_errors():
        return {"error": "Authentication required", "details": access_ctx.get_errors()}

    # Get the user's Linear token (fetched by Keycard!)
    token = access_ctx.access("https://api.linear.app").access_token

    # Use it...
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.linear.app/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": query, "variables": {"identifier": identifier}}
        )
        return response.json()
```

### What Just Happened?

1. User calls the `task` tool from Claude/Cursor
2. Their request includes a JWT (from Keycard)
3. `@auth_provider.grant()` sees they need Linear access
4. Keycard exchanges the JWT for a Linear OAuth token
5. The token is available via `access_ctx.access(...).access_token`
6. The tool uses the user's own token to call Linear

**No hardcoded tokens. Each user gets their own. Full audit trail.**

### Multiple Resources

Need both Linear AND GitHub?

```python
@mcp.tool(name="research")
@auth_provider.grant(["https://api.linear.app", "https://api.github.com"])
async def research_task(ctx: Context, task_id: str, repo: str) -> dict:
    access_ctx: AccessContext = ctx.get_state("keycardai")

    linear_token = access_ctx.access("https://api.linear.app").access_token
    github_token = access_ctx.access("https://api.github.com").access_token

    # Use both tokens...
```

---

## Phase 5: Multi-Agent AI with CrewAI

### Why CrewAI?

Single tools are useful, but complex tasks need multiple steps:

1. Read the Linear task
2. Explore the codebase to find relevant files
3. Research best practices
4. Synthesize into an implementation plan

This is a lot for one tool. Enter **CrewAI**: a framework for orchestrating multiple AI agents that work together.

### CrewAI Concepts

```
┌─────────────────────────────────────────────────────────────┐
│                          CREW                                │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       │
│  │ Task Analyst│──→│ Code Analyst│──→│   Planner   │       │
│  │   Agent     │   │   Agent     │   │   Agent     │       │
│  └─────────────┘   └─────────────┘   └─────────────┘       │
│        │                 │                                   │
│        ▼                 ▼                                   │
│   [Linear Tool]    [GitHub Tools]                           │
└─────────────────────────────────────────────────────────────┘
```

- **Agent**: An AI persona with a specific role (e.g., "Code Analyst")
- **Tool**: Something an agent can use (e.g., read a file)
- **Task**: A specific goal for an agent
- **Crew**: A group of agents working together

### Setting Up CrewAI

Install:

```bash
pip install crewai crewai-tools
```

Define agents (`agents.py`):

```python
from crewai import Agent

def create_task_analyst(tools):
    return Agent(
        role="Task Requirements Analyst",
        goal="Understand what needs to be built from the Linear task",
        backstory="Expert at reading task descriptions and extracting requirements",
        tools=tools,
        verbose=True
    )

def create_code_analyst(tools):
    return Agent(
        role="Code Analyst",
        goal="Understand the codebase structure and find relevant files",
        backstory="Expert at navigating codebases and understanding architecture",
        tools=tools,
        verbose=True
    )

def create_planner():
    return Agent(
        role="Implementation Planner",
        goal="Create a detailed implementation plan",
        backstory="Expert at breaking down tasks into actionable steps",
        verbose=True
    )
```

Define tasks (`tasks.py`):

```python
from crewai import Task

def create_task_analysis_task(agent, task_identifier):
    return Task(
        description=f"Analyze Linear task '{task_identifier}' and extract requirements",
        expected_output="Structured summary of task requirements",
        agent=agent
    )
```

### First Attempt: Pass Tokens to Crew (Insecure!)

```python
# ❌ DON'T DO THIS - tokens visible to crew code
def run_research_crew(linear_token: str, github_token: str, task_id: str):

    # Tokens passed directly - exposed!
    linear_tool = LinearTool(token=linear_token)
    github_tool = GitHubTool(token=github_token)

    # ... create agents with tools
    crew = Crew(agents=[...], tasks=[...])
    return crew.kickoff()
```

This works but defeats the purpose of Keycard. The tokens are visible in the crew code!

---

## Phase 6: Tool-Secured Mode

### The Goal

Agents should **never see tokens**. They call tools, and the tools handle auth transparently.

```
Agent calls "get_linear_task"
         │
         ▼
    Tool Wrapper (no token visible)
         │
         ▼
    MCP Tool Function
         │
         ▼
    @auth_provider.grant() ← Keycard fetches token here
         │
         ▼
    Linear API (with token)
```

### The Challenge: Async Context

CrewAI runs synchronously by default. Our MCP server is async. The auth context needs to flow through both.

**What breaks:**

```python
# This loses async context:
loop.run_in_executor(None, sync_crew_function)  # ← Thread pool loses context
asyncio.run(async_tool())  # ← New event loop, no auth context
```

### The Solution: Fully Async CrewAI

CrewAI supports `crew.kickoff_async()`. We can make everything async:

```python
from crewai.tools import BaseTool
from pydantic import Field

class LinearTaskTool(BaseTool):
    """Async tool wrapper for MCP Linear function."""

    name: str = "get_linear_task"
    description: str = "Get Linear task details by identifier"

    # These are passed in, not hardcoded
    ctx: Any = Field(default=None, exclude=True)
    fn: Any = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    async def _run(self, identifier: str) -> str:
        """Async - CrewAI handles this natively."""
        # Call the MCP tool function (which has @auth_provider.grant)
        result = await self.fn.fn(self.ctx, identifier)
        return str(result)
```

### Wiring It Together

The research crew function:

```python
async def run_research_crew(
    ctx: Context,                # Auth context (NOT tokens!)
    task_identifier: str,
    owner: str,
    repo: str,
    linear_task_fn: Callable,    # MCP tool function reference
    github_tree_fn: Callable,
    github_read_fn: Callable,
) -> str:
    """
    Run research crew - FULLY ASYNC, Tool-Secured Mode.

    Agents call async tool wrappers that delegate to MCP functions.
    Tokens are handled by @auth_provider.grant() - never visible here.
    """

    # Create async tool instances
    linear_tool = LinearTaskTool(ctx=ctx, fn=linear_task_fn)
    tree_tool = RepoStructureTool(ctx=ctx, fn=github_tree_fn, owner=owner, repo=repo)
    read_tool = ReadFileTool(ctx=ctx, fn=github_read_fn, owner=owner, repo=repo)

    # Create agents with tools
    task_analyst = create_task_analyst([linear_tool])
    code_analyst = create_code_analyst([tree_tool, read_tool])
    planner = create_planner()

    # Create and run crew - ASYNC!
    crew = Crew(
        agents=[task_analyst, code_analyst, planner],
        tasks=[create_task_analysis_task(task_analyst, task_identifier)],
        process=Process.sequential,
        verbose=True
    )

    result = await crew.kickoff_async()  # ← Native async!
    return str(result)
```

The MCP tool that starts it all:

```python
@mcp.tool(name="research")
@auth_provider.grant(["https://api.linear.app", "https://api.github.com"])
async def research_task(ctx: Context, task_identifier: str, owner: str, repo: str) -> dict:
    """Run research crew to analyze task and produce implementation plan."""

    # Check auth
    access_ctx: AccessContext = ctx.get_state("keycardai")
    if access_ctx.has_errors():
        return {"error": "Authentication required", "details": access_ctx.get_errors()}

    # Run the crew - pass ctx and tool functions, NOT tokens
    plan = await run_research_crew(
        ctx=ctx,
        task_identifier=task_identifier,
        owner=owner,
        repo=repo,
        linear_task_fn=get_linear_task,      # MCP tool function
        github_tree_fn=get_repo_structure,   # MCP tool function
        github_read_fn=read_file,            # MCP tool function
    )

    return {"success": True, "implementation_plan": plan}
```

### Why This Works

1. **No thread pools** - Crew runs in same async context as MCP server
2. **`crew.kickoff_async()`** - CrewAI's native async support
3. **Async `_run()` methods** - CrewAI awaits async tool implementations
4. **`await self.fn.fn(ctx, ...)`** - Properly awaits the MCP tool function
5. **Auth context preserved** - Same event loop, `@auth_provider.grant()` works

### The Complete Flow

```
User: "Analyze PLA-5 for the playthis-3 repo"
         │
         ▼
┌─ AI Client (Claude/Cursor) ─────────────────────────────────────┐
│  Calls research_task tool with user's JWT                       │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ MCP Server ────────────────────────────────────────────────────┐
│  @auth_provider.grant() exchanges JWT for Linear + GitHub tokens│
│  Tokens stored in ctx (never visible to user code)              │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ CrewAI (run_research_crew) ────────────────────────────────────┐
│  Task Analyst Agent                                              │
│    └─ Calls LinearTaskTool.run("PLA-5")                         │
│         └─ await fn.fn(ctx, "PLA-5")                            │
│              └─ get_linear_task() uses ctx to get token         │
│                   └─ Linear API returns task data               │
│                                                                  │
│  Code Analyst Agent                                              │
│    └─ Calls RepoStructureTool.run("")                           │
│         └─ await fn.fn(ctx, owner, repo, "")                    │
│              └─ get_repo_structure() uses ctx to get token      │
│                   └─ GitHub API returns file tree               │
│                                                                  │
│  Planner Agent                                                   │
│    └─ Synthesizes findings into implementation plan             │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ Response ──────────────────────────────────────────────────────┐
│  {"success": true, "implementation_plan": "..."}                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Summary: What We Built

| Phase | What | Why |
|-------|------|-----|
| 1 | Basic MCP server | Foundation - expose tools to AI |
| 2 | Linear + GitHub tools | Real functionality |
| 3 | Identified security problem | Hardcoded tokens are bad |
| 4 | Added Keycard | Per-user OAuth, audit trail |
| 5 | Added CrewAI | Multi-agent orchestration |
| 6 | Tool-Secured Mode | Tokens never visible to agents |

### Key Takeaways

1. **MCP** lets AI use external tools via a standard protocol
2. **Keycard** handles identity and OAuth so you don't have to
3. **`@auth_provider.grant()`** is the magic that fetches user tokens
4. **CrewAI** orchestrates multiple agents for complex tasks
5. **Tool-Secured Mode** means agents never see credentials
6. **Fully async** is key - no thread pools, no `asyncio.run()`

### Files in This Project

```
linear-github-mcp-server/
├── src/
│   ├── server.py           # MCP server with Keycard auth
│   └── crew/
│       ├── agents.py       # CrewAI agent definitions
│       ├── tasks.py        # CrewAI task definitions
│       └── research.py     # Async crew orchestration
├── requirements.txt
├── .env.example
└── BUILDING_THE_SERVER.md  # This guide!
```

---

## Next Steps

1. **Add more tools** - PR creation, task status updates, etc.
2. **Add more agents** - Security reviewer, test writer, etc.
3. **Deploy to production** - Render, Railway, or your own infrastructure
4. **Connect to more APIs** - Slack, Notion, Jira via Keycard providers

Happy building! 🚀
