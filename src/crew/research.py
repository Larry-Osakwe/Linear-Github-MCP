"""
Research crew orchestration using Tool-Secured Mode with fully async execution.

This module provides the research_task MCP tool that runs a CrewAI crew
to analyze a Linear task and produce an implementation plan.

Tool-Secured Mode: CrewAI agents call async MCP tool function wrappers that
delegate to the actual MCP tools (which have @auth_provider.grant()).
Tokens are NEVER exposed to agent code - auth is handled by the decorators.

Key architecture:
- BaseTool subclasses with async _run() methods
- crew.kickoff_async() for native async execution
- No thread pools, no asyncio.run() - proper async context propagation
"""

from typing import Callable, Any

from crewai import Crew, Process
from crewai.tools import BaseTool
from crewai_tools import SerperDevTool
from fastmcp import Context
from pydantic import Field

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


class LinearTaskTool(BaseTool):
    """Async tool that calls MCP Linear task function."""
    name: str = "get_linear_task"
    description: str = "Get Linear task details by identifier (e.g., 'PLA-5'). Returns task title, description, status, and other metadata."

    ctx: Any = Field(default=None, exclude=True)
    fn: Any = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    async def _run(self, identifier: str) -> str:
        """Async implementation - CrewAI handles this natively."""
        result = await self.fn.fn(self.ctx, identifier)
        return str(result)


class RepoStructureTool(BaseTool):
    """Async tool that calls MCP GitHub repo structure function."""
    name: str = "get_repo_structure"
    description: str = "Get GitHub repository file/folder structure. Optionally provide a path for a subdirectory."

    ctx: Any = Field(default=None, exclude=True)
    fn: Any = Field(default=None, exclude=True)
    owner: str = Field(default="", exclude=True)
    repo: str = Field(default="", exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    async def _run(self, path: str = "") -> str:
        """Async implementation."""
        result = await self.fn.fn(self.ctx, self.owner, self.repo, path)
        return str(result)


class ReadFileTool(BaseTool):
    """Async tool that calls MCP GitHub read file function."""
    name: str = "read_file"
    description: str = "Read file contents from GitHub repository. Provide the file path relative to repo root."

    ctx: Any = Field(default=None, exclude=True)
    fn: Any = Field(default=None, exclude=True)
    owner: str = Field(default="", exclude=True)
    repo: str = Field(default="", exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    async def _run(self, path: str) -> str:
        """Async implementation."""
        result = await self.fn.fn(self.ctx, self.owner, self.repo, path)
        return str(result)


async def run_research_crew(
    ctx: Context,
    task_identifier: str,
    owner: str,
    repo: str,
    linear_task_fn: Callable,
    github_tree_fn: Callable,
    github_read_fn: Callable,
    enable_web_search: bool = True
) -> str:
    """
    Run the research crew to analyze a task and produce an implementation plan.

    FULLY ASYNC - Tool-Secured Mode:
    - Agents call async MCP tool functions directly
    - No thread pools, no asyncio.run() - proper async context propagation
    - Tokens are handled by @auth_provider.grant() decorators - never exposed to crew
    - Uses crew.kickoff_async() for native async execution

    Args:
        ctx: MCP Context containing AccessContext for authentication
        task_identifier: Linear task ID (e.g., "ENG-123")
        owner: GitHub repo owner
        repo: GitHub repo name
        linear_task_fn: MCP tool function for getting Linear tasks
        github_tree_fn: MCP tool function for getting repo structure
        github_read_fn: MCP tool function for reading files
        enable_web_search: Whether to enable web search (requires SERPER_API_KEY)

    Returns:
        Implementation plan as string
    """
    # Create async tool instances - these use BaseTool with async _run()
    linear_tool = LinearTaskTool(ctx=ctx, fn=linear_task_fn)
    tree_tool = RepoStructureTool(ctx=ctx, fn=github_tree_fn, owner=owner, repo=repo)
    read_tool = ReadFileTool(ctx=ctx, fn=github_read_fn, owner=owner, repo=repo)

    # Create agents with async tools
    linear_tools = [linear_tool]
    github_tools = [tree_tool, read_tool]

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

    # Build crew agents list
    crew_agents = [task_analyst, code_analyst, planner]
    if researcher:
        crew_agents.insert(2, researcher)

    # Create and run first crew - USE ASYNC KICKOFF
    crew = Crew(
        agents=crew_agents,
        tasks=[task_analysis],
        process=Process.sequential,
        verbose=True
    )

    # Native async - no thread pools!
    result = await crew.kickoff_async()
    task_analysis_output = str(result)

    # Code exploration crew
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
    code_result = await code_crew.kickoff_async()
    code_context = str(code_result)

    # Research task (if enabled)
    research_output = "No web research performed."
    if researcher and search_tools:
        research_task_obj = create_research_task(researcher, task_analysis_output)
        research_crew = Crew(
            agents=[researcher],
            tasks=[research_task_obj],
            process=Process.sequential,
            verbose=True
        )
        research_result = await research_crew.kickoff_async()
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
    final_result = await planning_crew.kickoff_async()

    return str(final_result)
