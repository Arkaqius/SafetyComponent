"""Configure the standalone export of the SafetyComponent safety baseline."""

from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    """Keep trace targets present in the HTML when opened from disk."""
    return ProjectConfig(project_title="SafetyComponent", lazy_document_loading_threshold=0)
