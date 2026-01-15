"""
Linear-GitHub MCP Server with Keycard Authentication

This server provides MCP tools for:
- Linear: Read/write issues, update task status
- GitHub: Read repo, create branches, write files, create PRs
- CrewAI: Research tool that analyzes tasks and produces implementation plans
"""

from fastmcp import FastMCP, Context
import httpx
import os
import base64
from dotenv import load_dotenv
from starlette.applications import Starlette
from keycardai.mcp.server.auth import AuthProvider
from keycardai.mcp.server.auth.application_credentials import ClientSecret

# Load environment variables
from pathlib import Path
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Create Keycard authentication provider
auth_provider = AuthProvider(
    zone_id=os.getenv("KEYCARD_ZONE_ID"),
    mcp_server_name="Linear-GitHub MCP Server",
    mcp_server_url=os.getenv("MCP_SERVER_URL", "http://localhost:8000/"),
    application_credential=ClientSecret((
        os.getenv("KEYCARD_CLIENT_ID"),
        os.getenv("KEYCARD_CLIENT_SECRET")
    ))
)

# Initialize MCP server
mcp = FastMCP("Linear-GitHub Automation")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_access_context(ctx: Context):
    """Get Keycard access context from MCP context."""
    return ctx.get_state("keycardai")


def get_token(ctx: Context, resource: str) -> str | None:
    """Get exchanged token for a resource, or None if not available."""
    access_ctx = get_access_context(ctx)
    if access_ctx is None or access_ctx.has_errors():
        return None
    try:
        return access_ctx.access(resource).access_token
    except Exception:
        return None


# =============================================================================
# ECHO TOOL (for testing)
# =============================================================================

@mcp.tool(name="echo", description="Echo test tool - use to verify server is running")
async def echo_tool(ctx: Context, message: str) -> str:
    """Simple echo for testing connectivity."""
    return f"Echo: {message}"


# =============================================================================
# LINEAR TOOLS
# =============================================================================

@mcp.tool(
    name="get_linear_issues",
    description="Get Linear issues assigned to the authenticated user. Returns list of issues with id, identifier, title, description, state, and priority."
)
async def get_linear_issues(ctx: Context) -> dict:
    """Fetch Linear issues for the authenticated user."""
    token = get_token(ctx, "https://api.linear.app")
    if not token:
        return {"error": "Authentication required for Linear", "isError": True}

    query = """
    query {
        viewer {
            assignedIssues(first: 50) {
                nodes {
                    id
                    identifier
                    title
                    description
                    state { name }
                    priority
                    project { name }
                }
            }
        }
    }
    """

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={"query": query}
        )
        return response.json()


@mcp.tool(
    name="get_linear_task",
    description="Get details of a specific Linear task by its identifier (e.g., 'ENG-123')."
)
async def get_linear_task(ctx: Context, identifier: str) -> dict:
    """Fetch a specific Linear task by identifier."""
    token = get_token(ctx, "https://api.linear.app")
    if not token:
        return {"error": "Authentication required for Linear", "isError": True}

    query = """
    query($identifier: String!) {
        issue(id: $identifier) {
            id
            identifier
            title
            description
            state { id name }
            priority
            labels { nodes { name } }
            assignee { name email }
            project { name }
            team { id name }
            comments { nodes { body user { name } createdAt } }
        }
    }
    """

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={"query": query, "variables": {"identifier": identifier}}
        )
        return response.json()


@mcp.tool(
    name="get_workflow_states",
    description="Get available workflow states for a Linear team. Useful for knowing which states you can transition a task to."
)
async def get_workflow_states(ctx: Context, team_id: str | None = None) -> dict:
    """Get workflow states for transitions."""
    token = get_token(ctx, "https://api.linear.app")
    if not token:
        return {"error": "Authentication required for Linear", "isError": True}

    # If no team_id, get states for all teams the user has access to
    if team_id:
        query = """
        query($teamId: String!) {
            team(id: $teamId) {
                states { nodes { id name type } }
            }
        }
        """
        variables = {"teamId": team_id}
    else:
        query = """
        query {
            teams {
                nodes {
                    id
                    name
                    states { nodes { id name type } }
                }
            }
        }
        """
        variables = {}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={"query": query, "variables": variables}
        )
        return response.json()


@mcp.tool(
    name="update_task_status",
    description="Update the status of a Linear task. Requires issue_id and state_id (get state_id from get_workflow_states)."
)
async def update_task_status(ctx: Context, issue_id: str, state_id: str) -> dict:
    """Update Linear task status."""
    token = get_token(ctx, "https://api.linear.app")
    if not token:
        return {"error": "Authentication required for Linear", "isError": True}

    mutation = """
    mutation($id: String!, $stateId: String!) {
        issueUpdate(id: $id, input: { stateId: $stateId }) {
            success
            issue { id identifier state { name } }
        }
    }
    """

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={"query": mutation, "variables": {"id": issue_id, "stateId": state_id}}
        )
        return response.json()


# =============================================================================
# GITHUB TOOLS
# =============================================================================

@mcp.tool(
    name="get_repo_structure",
    description="Get the file structure of a GitHub repository. Parameters: owner (repo owner), repo (repo name), path (optional subdirectory)."
)
async def get_repo_structure(ctx: Context, owner: str, repo: str, path: str = "") -> dict:
    """Fetch repository file structure."""
    token = get_token(ctx, "https://api.github.com")
    if not token:
        return {"error": "Authentication required for GitHub", "isError": True}

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Simplify output - just name, type, path
            if isinstance(data, list):
                return {
                    "files": [
                        {"name": f["name"], "type": f["type"], "path": f["path"]}
                        for f in data
                    ]
                }
            return data
        return {"error": f"Status {response.status_code}", "message": response.text}


@mcp.tool(
    name="read_file",
    description="Read contents of a file from a GitHub repository. Returns the file content as text."
)
async def read_file(ctx: Context, owner: str, repo: str, path: str, ref: str = "main") -> dict:
    """Read file contents from GitHub."""
    token = get_token(ctx, "https://api.github.com")
    if not token:
        return {"error": "Authentication required for GitHub", "isError": True}

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    params = {"ref": ref}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data.get("content", "")).decode("utf-8")
            return {"path": path, "content": content, "sha": data.get("sha")}
        return {"error": f"Status {response.status_code}", "message": response.text}


@mcp.tool(
    name="create_branch",
    description="Create a new branch in a GitHub repository from an existing branch."
)
async def create_branch(ctx: Context, owner: str, repo: str, branch_name: str, from_branch: str = "main") -> dict:
    """Create a new branch."""
    token = get_token(ctx, "https://api.github.com")
    if not token:
        return {"error": "Authentication required for GitHub", "isError": True}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with httpx.AsyncClient() as client:
        # Get SHA of source branch
        ref_response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{from_branch}",
            headers=headers
        )
        if ref_response.status_code != 200:
            return {"error": f"Could not find branch {from_branch}", "details": ref_response.text}

        sha = ref_response.json()["object"]["sha"]

        # Create new branch
        create_response = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/refs",
            headers=headers,
            json={"ref": f"refs/heads/{branch_name}", "sha": sha}
        )

        if create_response.status_code == 201:
            return {"success": True, "branch": branch_name, "sha": sha}
        return {"error": f"Status {create_response.status_code}", "message": create_response.text}


@mcp.tool(
    name="write_file",
    description="Create or update a file in a GitHub repository. For updates, provide the sha from read_file."
)
async def write_file(
    ctx: Context,
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str,
    sha: str | None = None
) -> dict:
    """Create or update a file."""
    token = get_token(ctx, "https://api.github.com")
    if not token:
        return {"error": "Authentication required for GitHub", "isError": True}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    body = {
        "message": message,
        "content": encoded_content,
        "branch": branch
    }
    if sha:
        body["sha"] = sha

    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            headers=headers,
            json=body
        )

        if response.status_code in [200, 201]:
            data = response.json()
            return {
                "success": True,
                "path": path,
                "commit_sha": data.get("commit", {}).get("sha")
            }
        return {"error": f"Status {response.status_code}", "message": response.text}


@mcp.tool(
    name="create_pull_request",
    description="Create a pull request in a GitHub repository."
)
async def create_pull_request(
    ctx: Context,
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main"
) -> dict:
    """Create a pull request."""
    token = get_token(ctx, "https://api.github.com")
    if not token:
        return {"error": "Authentication required for GitHub", "isError": True}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            headers=headers,
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base
            }
        )

        if response.status_code == 201:
            data = response.json()
            return {
                "success": True,
                "pr_number": data.get("number"),
                "url": data.get("html_url")
            }
        return {"error": f"Status {response.status_code}", "message": response.text}


# =============================================================================
# CREWAI RESEARCH TOOL
# =============================================================================

@mcp.tool(
    name="research_task",
    description="""Run a CrewAI research crew to analyze a Linear task and produce a detailed implementation plan.

    This tool runs multiple AI agents that:
    1. Analyze the Linear task requirements
    2. Explore relevant code in the GitHub repository
    3. Research best practices (if SERPER_API_KEY is set)
    4. Synthesize findings into an actionable implementation plan

    Parameters:
    - task_identifier: Linear task ID (e.g., "ENG-123")
    - owner: GitHub repository owner
    - repo: GitHub repository name
    - enable_web_search: Whether to search web for best practices (default: true)

    Returns a detailed implementation plan with:
    - Task requirements analysis
    - Relevant code context
    - Best practices
    - Step-by-step implementation guide
    """
)
async def research_task(
    ctx: Context,
    task_identifier: str,
    owner: str,
    repo: str,
    enable_web_search: bool = True
) -> dict:
    """Run research crew to analyze task and produce implementation plan."""
    # Get tokens for both services
    linear_token = get_token(ctx, "https://api.linear.app")
    github_token = get_token(ctx, "https://api.github.com")

    if not linear_token:
        return {"error": "Authentication required for Linear", "isError": True}
    if not github_token:
        return {"error": "Authentication required for GitHub", "isError": True}

    try:
        from .crew.research import run_research_crew_async

        plan = await run_research_crew_async(
            task_identifier=task_identifier,
            owner=owner,
            repo=repo,
            linear_token=linear_token,
            github_token=github_token,
            enable_web_search=enable_web_search
        )

        return {
            "success": True,
            "task": task_identifier,
            "repo": f"{owner}/{repo}",
            "implementation_plan": plan
        }
    except Exception as e:
        return {
            "error": f"Research crew failed: {str(e)}",
            "isError": True
        }


# =============================================================================
# AUTH TEST TOOL
# =============================================================================

@mcp.tool(
    name="test_auth",
    description="Test authentication status for Linear and GitHub."
)
async def test_auth(ctx: Context) -> dict:
    """Test authentication for both services."""
    access_ctx = get_access_context(ctx)

    if access_ctx is None:
        return {
            "status": "ERROR",
            "message": "No authentication context - server auth may not be configured"
        }

    results = {
        "linear": {"status": "unknown"},
        "github": {"status": "unknown"}
    }

    # Test Linear
    try:
        linear_token = access_ctx.access("https://api.linear.app").access_token
        results["linear"] = {
            "status": "authenticated",
            "token_length": len(linear_token)
        }
    except Exception as e:
        results["linear"] = {"status": "error", "message": str(e)}

    # Test GitHub
    try:
        github_token = access_ctx.access("https://api.github.com").access_token
        results["github"] = {
            "status": "authenticated",
            "token_length": len(github_token)
        }
    except Exception as e:
        results["github"] = {"status": "error", "message": str(e)}

    return results


# =============================================================================
# CREATE APP
# =============================================================================

# Create ASGI app with Keycard authentication
mcp_asgi_app = mcp.http_app()
app = Starlette(routes=auth_provider.get_mcp_router(mcp_asgi_app))
