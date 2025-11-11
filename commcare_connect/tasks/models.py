"""
Tasks models using ExperimentRecord architecture.

All task data is stored using the ExperimentRecord model from the labs app.
This file re-exports the TaskRecord proxy model for Django to recognize it.
"""

# Import and re-export the proxy model so Django's migrations system can find it
from commcare_connect.tasks.experiment_models import TaskRecord  # noqa: F401

__all__ = ["TaskRecord"]
