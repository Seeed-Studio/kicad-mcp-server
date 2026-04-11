"""Configuration management for KiCad MCP Server."""

import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration settings for the MCP server."""

    def __init__(self) -> None:
        """Initialize configuration from environment variables."""
        # KiCad project search paths
        project_paths_str = os.getenv("KICAD_PROJECT_PATHS", "")
        self.kicad_project_paths: list[str] = [
            p.strip() for p in project_paths_str.split(",") if p.strip()
        ]

        # Summary settings
        self.default_summary_detail_level: str = os.getenv(
            "DEFAULT_SUMMARY_DETAIL_LEVEL", "standard"
        )
        self.include_nets_in_summary: bool = (
            os.getenv("INCLUDE_NETS_IN_SUMMARY", "true").lower() == "true"
        )
        self.include_power_in_summary: bool = (
            os.getenv("INCLUDE_POWER_IN_SUMMARY", "true").lower() == "true"
        )

        # Test generation settings
        self.default_test_framework: str = os.getenv("DEFAULT_TEST_FRAMEWORK", "pytest")
        self.default_test_type: str = os.getenv("DEFAULT_TEST_TYPE", "connectivity")

    @classmethod
    def get_instance(cls) -> "Config":
        """Get singleton instance of Config."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance


# Global config instance
config = Config.get_instance()
