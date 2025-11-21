from datetime import date

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets import FunctionToolset

from commcare_connect.ai.types import UserDependencies
from commcare_connect.solicitations.data_access import SolicitationDataAccess
from commcare_connect.solicitations.models import SolicitationRecord

INSTRUCTIONS = """
You are a helpful assistant for working with solicitations.
You can help users list and find solicitations. Be concise and helpful.

If the user does not specify a filter, just look up all of the solicitations you have access to.
"""


class SolicitationData(BaseModel):
    """Solicitation information."""

    id: int
    title: str
    description: str
    scope_of_work: str
    solicitation_type: str  # 'eoi' or 'rfp'
    status: str  # 'active', 'closed', 'draft'
    is_publicly_listed: bool
    program_name: str
    application_deadline: date | None = None
    expected_start_date: date | None = None
    expected_end_date: date | None = None
    estimated_scale: str
    contact_email: str
    date_created: str | None = None
    date_modified: str | None = None

    @classmethod
    def from_solicitation_record(cls, record: SolicitationRecord) -> "SolicitationData":
        """Create SolicitationData from a SolicitationRecord."""
        return cls(
            id=record.id,
            title=record.title,
            description=record.description,
            scope_of_work=record.scope_of_work,
            solicitation_type=record.solicitation_type,
            status=record.status,
            is_publicly_listed=record.is_publicly_listed,
            program_name=record.program_name,
            application_deadline=record.application_deadline,
            expected_start_date=record.expected_start_date,
            expected_end_date=record.expected_end_date,
            estimated_scale=record.estimated_scale,
            contact_email=record.contact_email,
            date_created=record.date_created,
            date_modified=record.date_modified,
        )


async def list_solicitations(
    ctx: RunContext["UserDependencies"],
    program_id: int | None = None,
    status: str | None = None,
    solicitation_type: str | None = None,
    is_publicly_listed: bool | None = None,
) -> list[SolicitationData]:
    """List solicitations with optional filters.

    Args:
        ctx: The run context with user dependencies.
        program_id: Filter by production program ID (overrides deps.program_id if provided).
        status: Filter by status ('active', 'closed', 'draft').
        solicitation_type: Filter by type ('eoi', 'rfp').
        is_publicly_listed: Filter by public listing status.
    """
    if not ctx.deps.request:
        raise ValueError("Request object is required to access solicitations")

    if ctx.deps.program_id is None:
        raise ValueError(
            "program_id is required in UserDependencies. " "This should have been validated at agent initialization."
        )

    # Use program_id from deps if not explicitly provided
    effective_program_id = program_id if program_id is not None else ctx.deps.program_id

    data_access = SolicitationDataAccess(request=ctx.deps.request, program_id=effective_program_id)

    solicitations = data_access.get_solicitations(
        program_id=program_id,
        status=status,
        solicitation_type=solicitation_type,
        is_publicly_listed=is_publicly_listed,
    )

    return [SolicitationData.from_solicitation_record(sol) for sol in solicitations]


# TODO: Implement create_solicitation function
# def create_solicitation(
#     ctx: RunContext["UserDependencies"], solicitation_data: SolicitationData
# ) -> SolicitationData:
#     """Create a solicitation.
#
#     Args:
#         solicitation_data: The solicitation data.
#     """
#     pass


# TODO: Implement update_solicitation function
# def update_solicitation(
#     ctx: RunContext["UserDependencies"], solicitation_data: SolicitationData
# ) -> SolicitationData:
#     """Update a solicitation.
#
#     Args:
#         solicitation_data: The solicitation data.
#     """
#     pass


# TODO: Implement delete_solicitation function
# def delete_solicitation(
#     ctx: RunContext["UserDependencies"], solicitation_id: int
# ) -> SolicitationData:
#     """Delete a solicitation.
#
#     Args:
#         solicitation_id: The solicitation ID.
#     """
#     pass


solicitation_toolset = FunctionToolset(
    tools=[
        list_solicitations,
        # TODO: Add create_solicitation, update_solicitation, delete_solicitation
    ]
)

# Lazy-loaded agent instance
_agent_instance = None


def get_solicitation_agent() -> Agent:
    """
    Get or create the solicitation agent instance.

    This function lazy-loads the agent to avoid requiring OPENAI_API_KEY
    at import time. The agent is only created when actually needed.

    Returns:
        Agent: The solicitation agent instance

    Raises:
        ValueError: If OPENAI_API_KEY is not set when the agent is first accessed
    """
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = Agent(
            "openai:gpt-4o-mini",
            instructions=INSTRUCTIONS,
            deps_type=UserDependencies,
            toolsets=[solicitation_toolset],
            retries=2,
        )
    return _agent_instance
