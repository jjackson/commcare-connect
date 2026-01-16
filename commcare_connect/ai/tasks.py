"""
Celery tasks for Pydantic AI demo.
"""
import asyncio
import json
import logging

from django.contrib.auth import get_user_model

from commcare_connect.ai.agents.solicitation_agent import get_solicitation_agent
from commcare_connect.ai.agents.workflow_agent import (
    WorkflowEditResponse,
    build_workflow_prompt,
    get_workflow_agent,
    get_workflow_agent_openai,
)

# Coding agent is optional - only needed for "vibes" agent type
try:
    from commcare_connect.ai.agents.coding_agent import get_coding_agent

    HAS_CODING_AGENT = True
except ImportError:
    HAS_CODING_AGENT = False
    get_coding_agent = None
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
def run_agent(
    self,
    prompt: str,
    agent: str,
    session_id: str | None = None,
    user_id: int | None = None,
    access_token: str | None = None,
    program_id: int | None = None,
    current_code: str | None = None,
):
    """
    Run an AI agent with the user's prompt and optional message history.

    Args:
        prompt: The user's prompt
        agent: The agent type to use (e.g., "solicitations")
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
        from commcare_connect.labs.integrations.connect.oauth import fetch_user_organization_data
        from commcare_connect.labs.models import LabsUser

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
    # program_id is optional for UserDependencies
    deps = UserDependencies(user=request_user, request=mock_request, program_id=program_id)

    # Parse current_code as JSON for workflow agent (it contains workflow definition, render_code, and IDs)
    current_definition = None
    current_render_code = None
    model_provider = None
    definition_id = None
    opportunity_id = None
    if current_code:
        try:
            parsed = json.loads(current_code)
            if isinstance(parsed, dict):
                current_definition = parsed.get("definition")
                current_render_code = parsed.get("render_code")
                model_provider = parsed.get("model_provider", "anthropic")
                definition_id = parsed.get("definition_id")
                opportunity_id = parsed.get("opportunity_id")
        except json.JSONDecodeError:
            pass

    async def run_agent_task():
        # Get the agent instance based on agent parameter
        if agent == "solicitations":
            agent_instance = get_solicitation_agent()
            actual_prompt = prompt
        elif agent == "workflow":
            # Use the appropriate model based on user selection
            if model_provider == "openai":
                agent_instance = get_workflow_agent_openai()
            else:
                agent_instance = get_workflow_agent()

            # Build prompt with current workflow context (definition and render code)
            actual_prompt = build_workflow_prompt(prompt, current_definition, current_render_code)
        elif agent == "vibes":
            if not HAS_CODING_AGENT:
                raise ValueError("Coding agent not available - module not installed")
            agent_instance = get_coding_agent()
            # For coding agent, construct a prompt that includes the current code
            if current_code:
                prompt_with_code = f"""Current code:
```javascript
{current_code}
```

User request: {prompt}

Please modify the code to fulfill the user's request. Return the complete, updated code."""
            else:
                prompt_with_code = f"""User request: {prompt}

Please generate React code to fulfill the user's request. The code should be complete and runnable."""
            # Use the modified prompt for coding agent
            actual_prompt = prompt_with_code
        else:
            # Default to solicitation agent for unknown agent types
            logger.warning(f"[AI TASK] Unknown agent type: {agent}, defaulting to solicitation agent")
            agent_instance = get_solicitation_agent()
            actual_prompt = prompt

        # Pass message_history to maintain conversation context
        # Note: For coding agent with structured output, we may want to handle history differently
        # For now, we'll use the same pattern for all agents
        if history:
            logger.warning(f"[AI TASK] Running agent with {len(history)} previous messages")
            logger.warning(f"[AI TASK] Prompt: {actual_prompt[:100]}...")
            try:
                # Convert history to Pydantic AI format
                pydantic_history = convert_history_to_pydantic_format(history)
                logger.warning(f"[AI TASK] Converted history format, length: {len(pydantic_history)}")
                result = await agent_instance.run(actual_prompt, message_history=pydantic_history, deps=deps)
                logger.warning("[AI TASK] Agent completed with history")
            except Exception as e:
                logger.error(f"[AI TASK] Error running agent with history: {e}", exc_info=True)
                # Fallback to running without history if there's a format issue
                logger.warning("[AI TASK] Falling back to running without message history")
                result = await agent_instance.run(actual_prompt, deps=deps)
        else:
            logger.warning("[AI TASK] Running agent without message history")
            result = await agent_instance.run(actual_prompt, deps=deps)

        # Handle structured output for coding agent
        # result.output will be a CodeResponse instance when using structured output
        if agent == "vibes" and HAS_CODING_AGENT:
            from commcare_connect.ai.agents.coding_agent import CodeResponse

            if isinstance(result.output, CodeResponse):
                # Return as dict with message and code for frontend
                return {
                    "message": result.output.message,
                    "code": result.output.code,
                }

        # Handle structured output for workflow agent
        if agent == "workflow" and isinstance(result.output, WorkflowEditResponse):
            # Debug logging to understand what the AI returned
            logger.warning(
                f"[AI TASK] WorkflowEditResponse received: "
                f"message_len={len(result.output.message)}, "
                f"definition_changed={result.output.definition_changed}, "
                f"render_code_changed={result.output.render_code_changed}, "
                f"has_definition={result.output.definition is not None}, "
                f"has_render_code={result.output.render_code is not None}, "
                f"render_code_len={len(result.output.render_code) if result.output.render_code else 0}"
            )

            response_dict = {
                "message": result.output.message,
                "definition_changed": result.output.definition_changed,
                "render_code_changed": result.output.render_code_changed,
            }
            if result.output.definition:
                response_dict["definition"] = result.output.definition
            if result.output.render_code:
                response_dict["render_code"] = result.output.render_code

            # Validate: if render_code_changed is True but render_code is missing, fix the flag
            if result.output.render_code_changed and not result.output.render_code:
                logger.warning(
                    "[AI TASK] AI claimed render_code_changed=True but didn't provide render_code. "
                    "This may be due to output token limits. Setting render_code_changed=False."
                )
                response_dict["render_code_changed"] = False
                response_dict["message"] += (
                    "\n\n(Note: I tried to update the UI code but the response was too long. "
                    "Please try a simpler request or update the code manually.)"
                )

            # Same validation for definition
            if result.output.definition_changed and not result.output.definition:
                logger.warning("[AI TASK] AI claimed definition_changed=True but didn't provide definition.")
                response_dict["definition_changed"] = False

            return response_dict

        return result.output

    try:
        response = asyncio.run(run_agent_task())

        # Save messages to history
        if agent == "workflow" and definition_id and access_token:
            # For workflow agents, save to LabsRecord via WorkflowDataAccess
            try:
                from commcare_connect.workflow.data_access import WorkflowDataAccess

                workflow_data_access = WorkflowDataAccess(
                    access_token=access_token,
                    program_id=program_id,
                    opportunity_id=opportunity_id,
                )
                # Add user message
                workflow_data_access.add_chat_message(definition_id, "user", prompt)
                # Add assistant response
                if isinstance(response, dict) and "message" in response:
                    workflow_data_access.add_chat_message(definition_id, "assistant", response["message"])
                else:
                    workflow_data_access.add_chat_message(definition_id, "assistant", str(response))
                workflow_data_access.close()
                logger.warning(f"[AI TASK] Saved workflow chat to LabsRecord for definition {definition_id}")
            except Exception as e:
                logger.error(f"[AI TASK] Failed to save workflow chat to LabsRecord: {e}")
                # Fall back to session store
                if session_id:
                    add_message_to_history(session_id, "user", prompt)
                    if isinstance(response, dict) and "message" in response:
                        add_message_to_history(session_id, "assistant", response["message"])
                    else:
                        add_message_to_history(session_id, "assistant", str(response))
        elif session_id:
            # For other agents, use session store
            add_message_to_history(session_id, "user", prompt)
            if isinstance(response, dict) and "message" in response:
                add_message_to_history(session_id, "assistant", response["message"])
            else:
                add_message_to_history(session_id, "assistant", str(response))
            logger.warning(f"[AI TASK] Saved messages to history for session {session_id}")

        return response
    except Exception as e:
        logger.error(f"Error running solicitation agent: {e}", exc_info=True)
        set_task_progress(self, f"Error: {str(e)}")
        raise
