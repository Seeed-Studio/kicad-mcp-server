"""File handling utilities."""

from pathlib import Path


def validate_kicad_file(file_path: str, expected_extension: str) -> Path:
    """Validate that a file exists and has the correct extension.

    Args:
        file_path: Path to the file
        expected_extension: Expected file extension (e.g., '.kicad_sch')

    Returns:
        Resolved Path object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file has wrong extension
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if path.suffix.lower() != expected_extension.lower():
        raise ValueError(
            f"Expected {expected_extension} file, got {path.suffix}: {file_path}"
        )

    return path


def resolve_project_path(file_path: str, search_paths: list[str] | None = None) -> Path:
    """Resolve a file path, optionally searching project directories.

    Args:
        file_path: Relative or absolute file path
        search_paths: List of directories to search if file_path is relative

    Returns:
        Resolved Path object

    Raises:
        FileNotFoundError: If file cannot be found
    """
    path = Path(file_path)

    # If absolute path, just resolve it
    if path.is_absolute():
        if path.exists():
            return path.resolve()
        raise FileNotFoundError(f"File not found: {file_path}")

    # If relative path, try current directory first
    if path.exists():
        return path.resolve()

    # Search in provided paths
    if search_paths:
        for search_dir in search_paths:
            search_path = Path(search_dir) / path
            if search_path.exists():
                return search_path.resolve()

    raise FileNotFoundError(f"File not found: {file_path}")
