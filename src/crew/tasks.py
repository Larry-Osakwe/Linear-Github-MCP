"""
CrewAI task definitions for research crew.

Tasks are executed in sequence to build up context:
1. Analyze the Linear task
2. Explore relevant code
3. Research best practices
4. Create implementation plan
"""

from crewai import Task, Agent


def create_task_analysis_task(agent: Agent, task_identifier: str) -> Task:
    """Create task for analyzing the Linear issue."""
    return Task(
        description=f"""Analyze the Linear task '{task_identifier}' to understand:

        1. What is being requested (the core feature/fix)
        2. Any specific requirements mentioned
        3. Acceptance criteria (explicit or implied)
        4. Dependencies or blockers mentioned
        5. Related context from comments or linked items

        Use the get_linear_task tool to fetch the task details.

        Provide a structured summary with:
        - Task summary (1-2 sentences)
        - Requirements list
        - Acceptance criteria
        - Potential challenges
        """,
        expected_output="""A structured analysis including:
        - Clear task summary
        - Numbered list of requirements
        - Acceptance criteria checklist
        - Identified challenges or considerations""",
        agent=agent
    )


def create_code_exploration_task(
    agent: Agent,
    owner: str,
    repo: str,
    task_context: str
) -> Task:
    """Create task for exploring relevant code."""
    return Task(
        description=f"""Based on this task analysis:

        {task_context}

        Explore the repository {owner}/{repo} to find:

        1. Files most relevant to implementing this task
        2. Existing patterns and conventions to follow
        3. Related code that the new implementation should integrate with
        4. Test patterns used in similar areas

        Use get_repo_structure to explore directories and read_file to examine
        specific files. Start with the root structure, then navigate to relevant
        areas based on the task requirements.

        Provide code snippets and file paths for relevant examples.
        """,
        expected_output="""A code context report including:
        - List of relevant files with their purpose
        - Key code patterns to follow (with snippets)
        - Integration points for the new code
        - Test patterns to use""",
        agent=agent
    )


def create_research_task(agent: Agent, task_context: str) -> Task:
    """Create task for researching best practices."""
    return Task(
        description=f"""Based on this task:

        {task_context}

        Research best practices and patterns for implementation:

        1. Search for relevant documentation or guides
        2. Find examples of similar implementations
        3. Identify common pitfalls to avoid
        4. Look for testing strategies

        Focus on practical, actionable information that will help
        with the implementation.
        """,
        expected_output="""Research findings including:
        - Best practices for this type of implementation
        - Recommended patterns with rationale
        - Common pitfalls and how to avoid them
        - Testing recommendations""",
        agent=agent
    )


def create_planning_task(
    agent: Agent,
    task_analysis: str,
    code_context: str,
    research: str
) -> Task:
    """Create task for synthesizing an implementation plan."""
    return Task(
        description=f"""Create a detailed implementation plan using this information:

        ## Task Analysis
        {task_analysis}

        ## Code Context
        {code_context}

        ## Research Findings
        {research}

        Create an actionable implementation plan that includes:

        1. **Prerequisites**: Any setup or dependencies needed first
        2. **Implementation Steps**: Numbered steps with specific details
           - Which files to create/modify
           - What code patterns to use
           - Integration points
        3. **Testing Plan**: How to test the implementation
        4. **Edge Cases**: Specific edge cases to handle
        5. **Gotchas**: Potential issues to watch out for

        Be specific enough that a developer can follow this plan
        without needing to ask clarifying questions.
        """,
        expected_output="""A comprehensive implementation plan with:

        ## Summary
        Brief overview of what will be implemented

        ## Prerequisites
        - List of setup steps if needed

        ## Implementation Steps
        1. First step with details
        2. Second step with details
        ...

        ## Files to Create/Modify
        - file/path.py - description of changes

        ## Testing Plan
        - Unit tests to write
        - Integration tests
        - Manual testing steps

        ## Edge Cases
        - Edge case 1 and how to handle

        ## Potential Gotchas
        - Thing to watch out for""",
        agent=agent
    )
