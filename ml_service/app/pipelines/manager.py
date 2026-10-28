"""
Pipeline Manager re-export conforming to MASTER_PROMPT.md §3 layout:
ml_service/app/pipelines/manager.py
"""

from ml_service.app.models.manager import ModelManager, model_manager

__all__ = ["ModelManager", "model_manager"]
