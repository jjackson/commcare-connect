"""
Celery tasks for Pydantic AI demo.
"""
import asyncio
import logging

from django.contrib.auth import get_user_model

from commcare_connect.ai.agents.solicitation_agent import get_solicitation_agent
from commcare_connect.ai.session_store import add_message_to_history, get_message_history
from commcare_connect.ai.types import UserDependencies
from commcare_connect.utils.celery import set_task_progress
from config import celery_app

logger = logging.getLogger(__name__)

User = get_user_model()

# Try to import Pydantic AI Message classes if available
try:
    from pydantic_ai.messages import ModelRequest, ModelResponse, SystemPromptPart, TextPart, UserPromptPart

    HAS_MESSAGE_CLASSES = True
except ImportError:
    HAS_MESSAGE_CLASSES = False
    logger.warning("[AI TASK] Pydantic AI Message classes not available, using dict format")


@celery_app.task(bind=True)
def simple_echo_task(
    self,
    prompt: str,
    session_id: str | None = None,
    user_id: int | None = None,
    access_token: str | None = None,
    program_id: int | None = None,
):
    """
    Run the solicitation agent with the user's prompt and optional message history.

    Args:
        prompt: The user's prompt
        session_id: Optional session ID for history tracking
        user_id: The user ID for authentication
        access_token: OAuth access token for API access
        program_id: Optional program ID for API scoping
    """
    set_task_progress(self, "Processing your prompt with AI...")

    # Retrieve message history if session_id is provided
    history = []
    if session_id:
        history = get_message_history(session_id)
        logger.warning(f"[AI TASK] Retrieved {len(history)} messages for session {session_id}")
        if history:
            logger.warning(f"[AI TASK] History sample: {history[:2]}")
    else:
        logger.warning("[AI TASK] No session_id provided, running without history")

    def convert_history_to_pydantic_format(messages: list[dict]) -> list:
        """
        Convert our message format to Pydantic AI format.

        Our format: [{"role": "user|assistant", "content": "..."}]
        Pydantic AI format: List of ModelRequest/ModelResponse objects with parts
        """
        if not HAS_MESSAGE_CLASSES:
            # If Message classes aren't available, return as-is (dict format)
            logger.warning("[AI TASK] Message classes not available, using dict format")
            return messages

        # Convert to Pydantic AI message format
        pydantic_messages = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                pydantic_messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif role == "assistant":
                pydantic_messages.append(ModelResponse(parts=[TextPart(content=content)]))
            elif role in ["system", "developer"]:
                pydantic_messages.append(ModelRequest(parts=[SystemPromptPart(content=content)]))
            else:
                logger.warning(f"[AI TASK] Unknown message role: {role}, skipping")

        return pydantic_messages

    # Get user object and create LabsUser with organization data
    user = None
    labs_user = None
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"[AI TASK] User with ID {user_id} does not exist")
            raise ValueError(f"User with ID {user_id} does not exist")

    # Fetch organization data and create LabsUser if we have an access token
    if access_token:
        from commcare_connect.labs.models import LabsUser
        from commcare_connect.labs.oauth_helpers import fetch_user_organization_data

        # Fetch organization data from production API
        org_data = fetch_user_organization_data(access_token)
        if org_data is None:
            logger.warning("[AI TASK] Failed to fetch organization data, continuing without it")

        # Create session data structure expected by LabsUser
        session_data = {
            "user_profile": {
                "id": user.id if user else 0,
                "username": user.username if user else "unknown",
                "email": user.email if user else "",
                "first_name": user.first_name if user else "",
                "last_name": user.last_name if user else "",
            },
            "organization_data": org_data or {},
        }

        # Create LabsUser with organization data (needed for API scoping)
        try:
            labs_user = LabsUser(session_data)
        except Exception as e:
            logger.warning(f"[AI TASK] Failed to create LabsUser: {e}, falling back to regular user")
            labs_user = user

    # Create a minimal request-like object for OAuth token access
    # We'll create a simple object that has the session data needed
    class MockRequest:
        def __init__(self, access_token, user=None, program_id=None):
            self.session = {}
            self.user = user
            if access_token:
                import time

                # Store token in session format expected by SolicitationDataAccess
                self.session["labs_oauth"] = {
                    "access_token": access_token,
                    "expires_at": time.time() + 3600,  # 1 hour from now
                }
            # Set labs_context for data access classes that check request.labs_context
            if program_id is not None:
                self.labs_context = {"program_id": program_id}
            else:
                self.labs_context = {}

    # Use LabsUser if available (has _org_data), otherwise fall back to regular user
    # This ensures the user has _org_data for API scoping
    request_user = labs_user or user
    mock_request = MockRequest(access_token, user=request_user, program_id=program_id)

    # Create dependencies - use the same user object for consistency
    # program_id is required for UserDependencies
    if program_id is None:
        raise ValueError(
            "program_id is required to run the AI agent. "
            "Please provide program_id in the request or ensure it's set in labs_context."
        )
    deps = UserDependencies(user=request_user, request=mock_request, program_id=program_id)

    async def run_agent():
        # Get the agent instance (lazy-loaded)
        agent = get_solicitation_agent()
        # Pass message_history to maintain conversation context
        if history:
            logger.warning(f"[AI TASK] Running agent with {len(history)} previous messages")
            logger.warning(f"[AI TASK] Prompt: {prompt[:100]}...")
            try:
                # Convert history to Pydantic AI format
                pydantic_history = convert_history_to_pydantic_format(history)
                logger.warning(f"[AI TASK] Converted history format, length: {len(pydantic_history)}")
                result = await agent.run(prompt, message_history=pydantic_history, deps=deps)
                logger.warning("[AI TASK] Agent completed with history")
            except Exception as e:
                logger.error(f"[AI TASK] Error running agent with history: {e}", exc_info=True)
                # Fallback to running without history if there's a format issue
                logger.warning("[AI TASK] Falling back to running without message history")
                result = await agent.run(prompt, deps=deps)
        else:
            logger.warning("[AI TASK] Running agent without message history")
            result = await agent.run(prompt, deps=deps)
        return result.output

    try:
        response = asyncio.run(run_agent())

        # Save messages to history if session_id is provided
        if session_id:
            # Add user message
            add_message_to_history(session_id, "user", prompt)
            # Add assistant response
            add_message_to_history(session_id, "assistant", response)
            logger.warning(f"[AI TASK] Saved messages to history for session {session_id}")

        return response
    except Exception as e:
        logger.error(f"Error running solicitation agent: {e}", exc_info=True)
        set_task_progress(self, f"Error: {str(e)}")
        raise
