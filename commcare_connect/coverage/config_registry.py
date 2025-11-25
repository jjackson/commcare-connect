"""
Analysis config registry for coverage visualization.

Allows coverage views to look up analysis configs by name, enabling URL-based
config selection (e.g., ?config=chc_nutrition) while leveraging cached results.

Usage:
    # Register a config (typically in the analysis module's __init__.py)
    from commcare_connect.coverage.config_registry import register_config
    register_config("chc_nutrition", CHC_NUTRITION_CONFIG)

    # Look up a config by name
    from commcare_connect.coverage.config_registry import get_config
    config = get_config("chc_nutrition")
"""

import logging

from commcare_connect.labs.analysis.config import AnalysisConfig

logger = logging.getLogger(__name__)

# Registry mapping config names to config objects
_CONFIG_REGISTRY: dict[str, AnalysisConfig] = {}


def register_config(name: str, config: AnalysisConfig) -> None:
    """
    Register an analysis config by name.

    Args:
        name: Unique name for the config (used in URL params)
        config: AnalysisConfig object to register
    """
    if name in _CONFIG_REGISTRY:
        logger.warning(f"Overwriting existing config registration: {name}")
    _CONFIG_REGISTRY[name] = config
    logger.info(f"Registered analysis config: {name}")


def get_config(name: str) -> AnalysisConfig | None:
    """
    Look up a config by name.

    Args:
        name: Config name to look up

    Returns:
        AnalysisConfig if found, None otherwise
    """
    return _CONFIG_REGISTRY.get(name)


def list_configs() -> list[str]:
    """
    List all registered config names.

    Returns:
        List of registered config names
    """
    return list(_CONFIG_REGISTRY.keys())
