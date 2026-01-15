"""
CrewAI agent definitions for research crew.

These agents work together to analyze a Linear task and produce
an implementation plan with code context and best practices.
"""

from crewai import Agent


def create_task_analyst(linear_tools: list) -> Agent:
    """Create agent for analyzing Linear task requirements."""
    return Agent(
        role="Task Requirements Analyst",
        goal="Thoroughly analyze Linear tasks to extract clear, actionable requirements",
        backstory="""You are an expert product analyst who excels at breaking down
        technical tasks into clear requirements. You understand both the explicit
        requests and implicit expectations in task descriptions. You always identify
        acceptance criteria, edge cases, and potential blockers.""",
        tools=linear_tools,
        verbose=True,
        allow_delegation=False
    )


def create_code_analyst(github_tools: list) -> Agent:
    """Create agent for analyzing relevant code in the repository."""
    return Agent(
        role="Codebase Analyst",
        goal="Find and understand relevant code patterns, structures, and conventions in the repository",
        backstory="""You are a senior software engineer with expertise in reading and
        understanding codebases quickly. You can identify relevant files, understand
        existing patterns, and find code that relates to a given task. You excel at
        providing context about how new code should fit into existing architecture.""",
        tools=github_tools,
        verbose=True,
        allow_delegation=False
    )


def create_researcher(search_tools: list) -> Agent:
    """Create agent for researching best practices and solutions."""
    return Agent(
        role="Technical Researcher",
        goal="Find best practices, patterns, and solutions relevant to the implementation task",
        backstory="""You are a technical researcher who stays up-to-date with modern
        software development practices. You know how to find relevant documentation,
        tutorials, and examples. You can synthesize information from multiple sources
        into actionable recommendations.""",
        tools=search_tools,
        verbose=True,
        allow_delegation=False
    )


def create_planner() -> Agent:
    """Create agent for synthesizing findings into an implementation plan."""
    return Agent(
        role="Implementation Planner",
        goal="Create a detailed, actionable implementation plan from research findings",
        backstory="""You are a technical lead who excels at creating clear implementation
        plans. You take input from analysts and researchers and synthesize it into a
        step-by-step plan that any developer can follow. You consider edge cases,
        testing requirements, and potential pitfalls.""",
        tools=[],  # No tools - uses context from other agents
        verbose=True,
        allow_delegation=False
    )
