"""
Celery tasks for Pydantic AI demo.
"""
import asyncio
import logging

from httpx import AsyncClient

from commcare_connect.ai.agents.weather_agent import Deps, weather_agent
from commcare_connect.utils.celery import set_task_progress
from config import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def simple_echo_task(self, prompt: str):
    """
    Run the weather agent with the user's prompt.
    """
    set_task_progress(self, "Processing your prompt with AI...")

    async def run_agent():
        async with AsyncClient() as client:
            deps = Deps(client=client)
            result = await weather_agent.run(prompt, deps=deps)
            return result.output

    try:
        response = asyncio.run(run_agent())
        return response
    except Exception as e:
        logger.error(f"Error running weather agent: {e}", exc_info=True)
        set_task_progress(self, f"Error: {str(e)}")
        raise
