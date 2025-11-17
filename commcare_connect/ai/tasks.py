"""
Celery tasks for Pydantic AI demo.
"""
import logging
import time

from commcare_connect.utils.celery import set_task_progress
from config import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def simple_echo_task(self, prompt: str):
    """
    Simple Celery task that echoes back a message.
    This is a placeholder before we add Pydantic AI.
    """
    set_task_progress(self, "Processing your prompt...")

    # Simulate some work
    time.sleep(2)

    # Simple echo response
    response = f"You said: {prompt}"

    set_task_progress(self, "Complete!", is_complete=True)

    return response
