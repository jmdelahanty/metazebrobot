"""
File operation utilities for MetaZebrobot.

This module provides common file and directory operations used across the application.
"""

import os
import json
import shutil
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union, List

logger = logging.getLogger(__name__)


def ensure_directory(directory_path: Union[str, Path]) -> bool:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        directory_path: Path to the directory to ensure
        
    Returns:
        bool: True if the directory exists or was created, False otherwise
    """
    try:
        path = Path(directory_path)
        path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {directory_path}: {str(e)}")
        return False


def load_json_file(file_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """
    Load and parse JSON from a file.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        Dict or None: Parsed JSON data, or None if the file doesn't exist or there was an error
    """
    path = Path(file_path)
    
    if not path.exists():
        logger.warning(f"File does not exist: {path}")
        return None
        
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {path}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error loading {path}: {str(e)}")
        return None


def save_json_file(file_path: Union[str, Path], data: Any, indent: int = 2) -> bool:
    """
    Save data to a JSON file.
    
    Args:
        file_path: Path to save the JSON file
        data: Data to serialize to JSON
        indent: Indentation level for the JSON output
        
    Returns:
        bool: True if the file was saved successfully, False otherwise
    """
    path = Path(file_path)
    
    # Create directory if it doesn't exist
    ensure_directory(path.parent)
    
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=indent)
        return True
    except Exception as e:
        logger.error(f"Error saving {path}: {str(e)}")
        return False


def list_json_files(directory_path: Union[str, Path], pattern: str = "*.json") -> List[Path]:
    """
    List all JSON files in a directory matching a pattern.
    
    Args:
        directory_path: Directory to search
        pattern: Glob pattern to match files
        
    Returns:
        List of Path objects for matching files
    """
    path = Path(directory_path)
    
    if not path.exists() or not path.is_dir():
        logger.warning(f"Directory does not exist: {path}")
        return []
        
    return list(path.glob(pattern))


def backup_file(file_path: Union[str, Path], backup_dir: Optional[Union[str, Path]] = None) -> bool:
    """
    Create a backup of a file before modifying it.
    
    Args:
        file_path: Path to the file to back up
        backup_dir: Directory to store backups, if None uses the same directory with .bak extension
        
    Returns:
        bool: True if backup was successful, False otherwise
    """
    path = Path(file_path)
    
    if not path.exists():
        logger.warning(f"Cannot back up non-existent file: {path}")
        return False
        
    try:
        if backup_dir:
            # Create backup directory if it doesn't exist
            backup_path = Path(backup_dir)
            ensure_directory(backup_path)
            backup_file = backup_path / path.name
        else:
            # Use same directory with .bak extension
            backup_file = path.with_suffix(path.suffix + ".bak")
            
        shutil.copy2(path, backup_file)
        return True
    except Exception as e:
        logger.error(f"Error backing up {path}: {str(e)}")
        return False


def safe_delete_file(file_path: Union[str, Path], backup: bool = True) -> bool:
    """
    Safely delete a file, optionally creating a backup first.
    
    Args:
        file_path: Path to the file to delete
        backup: Whether to create a backup before deleting
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    path = Path(file_path)
    
    if not path.exists():
        return True  # File doesn't exist, so deletion is technically successful
        
    try:
        if backup:
            backup_file(path)
            
        os.remove(path)
        return True
    except Exception as e:
        logger.error(f"Error deleting {path}: {str(e)}")
        return False