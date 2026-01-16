"""
Research crew orchestration using Tool-Secured Mode.

This module provides the research_task MCP tool that runs a CrewAI crew
to analyze a Linear task and produce an implementation plan.

Tool-Secured Mode: CrewAI agents call MCP tool function wrappers that
delegate to the actual MCP tools (which have @auth_provider.grant()).
Tokens are NEVER exposed to agent code - auth is handled by the decorators.
"""

import asyncio
from functools import partial
from typing import Callable, Awaitable, Any

from crewai import Crew, Process
from crewai_tools import SerperDevTool
from fastmcp import Context

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


def run_research_crew(
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

    Tool-Secured Mode: Agents call MCP tool functions directly.
    Tokens are handled by @auth_provider.grant() decorators - never exposed to crew.

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
    from crewai.tools import tool

    # Create CrewAI tool wrappers that call MCP functions with auth context
    # The MCP functions have @auth_provider.grant() - tokens handled automatically

    @tool("get_linear_task")
    def get_linear_task_tool(identifier: str) -> str:
        """Get Linear task details by identifier (e.g., 'PLA-5')."""
        # Call the MCP tool function with auth context
        # Use .fn to access the underlying callable (FastMCP's @mcp.tool returns FunctionTool)
        result = asyncio.run(linear_task_fn.fn(ctx, identifier))
        return str(result)

    @tool("get_repo_structure")
    def get_repo_structure_tool(path: str = "") -> str:
        """Get GitHub repository structure. Path is optional subdirectory."""
        # Call the MCP tool function with auth context
        # Use .fn to access the underlying callable
        result = asyncio.run(github_tree_fn.fn(ctx, owner, repo, path))
        return str(result)

    @tool("read_file")
    def read_file_tool(path: str) -> str:
        """Read file contents from GitHub repository."""
        # Call the MCP tool function with auth context
        # Use .fn to access the underlying callable
        result = asyncio.run(github_read_fn.fn(ctx, owner, repo, path))
        return str(result)

    # Create agents with wrapped tools
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
        research_task_obj = create_research_task(researcher, task_analysis_output)
        research_crew = Crew(
            agents=[researcher],
            tasks=[research_task_obj],
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
    Async wrapper for running research crew.

    Tool-Secured Mode: Pass ctx and tool functions instead of tokens.
    """
    # Run in thread pool to not block event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(
            run_research_crew,
            ctx=ctx,
            task_identifier=task_identifier,
            owner=owner,
            repo=repo,
            linear_task_fn=linear_task_fn,
            github_tree_fn=github_tree_fn,
            github_read_fn=github_read_fn,
            enable_web_search=enable_web_search
        )
    )
