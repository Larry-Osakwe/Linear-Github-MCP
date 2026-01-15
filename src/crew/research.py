"""
Research crew orchestration.

This module provides the research_task MCP tool that runs a CrewAI crew
to analyze a Linear task and produce an implementation plan.
"""

import asyncio
from typing import Any

from crewai import Crew, Process
from crewai_tools import SerperDevTool

from .agents import (
    create_task_analyst,
    create_code_analyst,
    create_researcher,
    create_planner,
)
from .tasks import (
    create_task_analysis_task,
    create_code_exploration_task,
    create_research_task,
    create_planning_task,
)


class LinearTool:
    """Wrapper to create CrewAI-compatible Linear tools from token."""

    def __init__(self, token: str):
        self.token = token

    def get_task(self, identifier: str) -> dict:
        """Synchronous wrapper for Linear API call."""
        import httpx

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

        response = httpx.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            },
            json={"query": query, "variables": {"identifier": identifier}},
            timeout=30.0
        )
        return response.json()


class GitHubTool:
    """Wrapper to create CrewAI-compatible GitHub tools from token."""

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

    def get_structure(self, owner: str, repo: str, path: str = "") -> dict:
        """Get repository structure."""
        import httpx

        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        response = httpx.get(url, headers=self.headers, timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return {"files": [{"name": f["name"], "type": f["type"], "path": f["path"]} for f in data]}
            return data
        return {"error": f"Status {response.status_code}"}

    def read_file(self, owner: str, repo: str, path: str, ref: str = "main") -> dict:
        """Read file contents."""
        import httpx
        import base64

        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        response = httpx.get(url, headers=self.headers, params={"ref": ref}, timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data.get("content", "")).decode("utf-8")
            return {"path": path, "content": content}
        return {"error": f"Status {response.status_code}"}


def run_research_crew(
    task_identifier: str,
    owner: str,
    repo: str,
    linear_token: str,
    github_token: str,
    enable_web_search: bool = True
) -> str:
    """
    Run the research crew to analyze a task and produce an implementation plan.

    Args:
        task_identifier: Linear task ID (e.g., "ENG-123")
        owner: GitHub repo owner
        repo: GitHub repo name
        linear_token: OAuth token for Linear API
        github_token: OAuth token for GitHub API
        enable_web_search: Whether to enable web search (requires SERPER_API_KEY)

    Returns:
        Implementation plan as string
    """
    # Create tool wrappers with tokens
    linear_tool = LinearTool(linear_token)
    github_tool = GitHubTool(github_token)

    # For now, create simple function-based tools
    # CrewAI can use these directly

    from crewai.tools import tool

    @tool("get_linear_task")
    def get_linear_task_tool(identifier: str) -> str:
        """Get Linear task details by identifier (e.g., 'ENG-123')."""
        result = linear_tool.get_task(identifier)
        return str(result)

    @tool("get_repo_structure")
    def get_repo_structure_tool(path: str = "") -> str:
        """Get GitHub repository structure. Path is optional subdirectory."""
        result = github_tool.get_structure(owner, repo, path)
        return str(result)

    @tool("read_file")
    def read_file_tool(path: str) -> str:
        """Read file contents from GitHub repository."""
        result = github_tool.read_file(owner, repo, path)
        return str(result)

    # Create agents with tools
    linear_tools = [get_linear_task_tool]
    github_tools = [get_repo_structure_tool, read_file_tool]

    search_tools = []
    if enable_web_search:
        try:
            search_tools = [SerperDevTool()]
        except Exception:
            # SERPER_API_KEY not set - skip web search
            pass

    task_analyst = create_task_analyst(linear_tools)
    code_analyst = create_code_analyst(github_tools)
    researcher = create_researcher(search_tools) if search_tools else None
    planner = create_planner()

    # Create tasks
    task_analysis = create_task_analysis_task(task_analyst, task_identifier)

    # We'll run this sequentially and pass context between tasks
    crew_agents = [task_analyst, code_analyst, planner]
    crew_tasks = [task_analysis]

    if researcher:
        crew_agents.insert(2, researcher)

    # Create crew
    crew = Crew(
        agents=crew_agents,
        tasks=[task_analysis],
        process=Process.sequential,
        verbose=True
    )

    # Run first task to get analysis
    result = crew.kickoff()

    # Now create follow-up tasks with context
    task_analysis_output = str(result)

    code_task = create_code_exploration_task(
        code_analyst,
        owner,
        repo,
        task_analysis_output
    )

    code_crew = Crew(
        agents=[code_analyst],
        tasks=[code_task],
        process=Process.sequential,
        verbose=True
    )
    code_result = code_crew.kickoff()
    code_context = str(code_result)

    # Research task (if enabled)
    research_output = "No web research performed."
    if researcher and search_tools:
        research_task = create_research_task(researcher, task_analysis_output)
        research_crew = Crew(
            agents=[researcher],
            tasks=[research_task],
            process=Process.sequential,
            verbose=True
        )
        research_result = research_crew.kickoff()
        research_output = str(research_result)

    # Final planning task
    planning_task = create_planning_task(
        planner,
        task_analysis_output,
        code_context,
        research_output
    )

    planning_crew = Crew(
        agents=[planner],
        tasks=[planning_task],
        process=Process.sequential,
        verbose=True
    )
    final_result = planning_crew.kickoff()

    return str(final_result)


async def run_research_crew_async(
    task_identifier: str,
    owner: str,
    repo: str,
    linear_token: str,
    github_token: str,
    enable_web_search: bool = True
) -> str:
    """Async wrapper for running research crew."""
    # Run in thread pool to not block event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        run_research_crew,
        task_identifier,
        owner,
        repo,
        linear_token,
        github_token,
        enable_web_search
    )
