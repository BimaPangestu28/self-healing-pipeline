"""Issue tracking tools for GitHub and Trello integration."""

from typing import Annotated

from agent_framework import ai_function

from src.clients.kube_tools_api import kube_tools_client
from src.tools.utils import truncate_string


@ai_function(
    name="create_github_issue",
    description=(
        "Create a GitHub issue in the appropriate repository for incidents, bugs, "
        "deployments, or changes."
    ),
)
async def create_github_issue(
    issue_type: Annotated[str, "Issue type: 'trx_serv' or 'auth_serv'"],
    title: Annotated[str, "Issue title (under 100 characters)"],
    body: Annotated[str | None, "Issue body/description with context"] = None,
    labels: Annotated[str | None, "Comma-separated labels (e.g., 'bug,critical')"] = None,
    assignees: Annotated[
        str | None, "Comma-separated GitHub usernames to assign"
    ] = None,
) -> str:
    """
    Create a GitHub issue in the appropriate repository.

    Use for:
    - Documenting incidents and outages
    - Creating bug reports
    - Tracking deployments and changes
    - Writing post-mortems
    - Maintaining audit trails
    """
    result = await kube_tools_client.create_github_issue(
        issue_type, title, body, labels, assignees
    )
    # Truncate result to prevent large responses
    result_str = truncate_string(str(result), 2000)
    return f"Created GitHub issue '{title}' (type: {issue_type}): {result_str}"


@ai_function(
    name="create_trello_issue",
    description=(
        "Create a Trello card in the appropriate board for tasks and planning items."
    ),
)
async def create_trello_issue(
    title: Annotated[str, "Card title"],
    description: Annotated[str, "Card description"],
) -> str:
    """
    Create a Trello card in the appropriate board.

    Use for:
    - Non-technical tasks
    - Planning items
    - Team coordination
    - General work tracking
    """
    result = await kube_tools_client.create_trello_issue(title, description)
    # Truncate result to prevent large responses
    result_str = truncate_string(str(result), 2000)
    return f"Created Trello card '{title}': {result_str}"


# Export all tools
issue_tracking_tools = [
    create_github_issue,
    create_trello_issue,
]
