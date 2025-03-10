"""
JSON storage implementation for MetaZebrobot.

This module provides functions for reading and writing data to JSON files.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union, List, TypeVar, Generic

from ..utils.file_operations import (
    load_json_file, save_json_file, list_json_files, 
    ensure_directory, backup_file
)

logger = logging.getLogger(__name__)

T = TypeVar('T')  # Generic type for data


class JsonStorage(Generic[T]):
    """
    Generic class for storing and retrieving data in JSON files.
    
    This class handles the low-level details of reading and writing JSON files,
    including error handling and backup creation.
    """
    
    def __init__(self, base_directory: Union[str, Path], backup_enabled: bool = True):
        """
        Initialize the JSON storage.
        
        Args:
            base_directory: Base directory for storing JSON files
            backup_enabled: Whether to create backups before modifying files
        """
        self.base_directory = Path(base_directory)
        self.backup_enabled = backup_enabled
        
    def ensure_directory(self) -> bool:
        """
        Ensure the base directory exists.
        
        Returns:
            bool: True if the directory exists or was created, False otherwise
        """
        return ensure_directory(self.base_directory)
        
    def load(self, filename: str) -> Optional[T]:
        """
        Load data from a JSON file.
        
        Args:
            filename: Name of the file to load (relative to base_directory)
            
        Returns:
            Data from the file, or None if the file doesn't exist or there was an error
        """
        file_path = self.base_directory / filename
        return load_json_file(file_path)
        
    def save(self, filename: str, data: T) -> bool:
        """
        Save data to a JSON file.
        
        Args:
            filename: Name of the file to save (relative to base_directory)
            data: Data to save
            
        Returns:
            bool: True if save was successful, False otherwise
        """
        if not self.ensure_directory():
            logger.error(f"Cannot save {filename}: base directory could not be created")
            return False
            
        file_path = self.base_directory / filename
        
        # Create backup if file exists and backup is enabled
        if self.backup_enabled and file_path.exists():
            backup_file(file_path)
            
        return save_json_file(file_path, data)
        
    def list_files(self, pattern: str = "*.json") -> List[Path]:
        """
        List all files in the base directory matching a pattern.
        
        Args:
            pattern: Glob pattern to match files
            
        Returns:
            List of Path objects for matching files
        """
        return list_json_files(self.base_directory, pattern)
        
    def exists(self, filename: str) -> bool:
        """
        Check if a file exists.
        
        Args:
            filename: Name of the file to check (relative to base_directory)
            
        Returns:
            bool: True if the file exists, False otherwise
        """
        file_path = self.base_directory / filename
        return file_path.exists()
        
    def delete(self, filename: str) -> bool:
        """
        Delete a file.
        
        Args:
            filename: Name of the file to delete (relative to base_directory)
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        from ..utils.file_operations import safe_delete_file
        
        file_path = self.base_directory / filename
        return safe_delete_file(file_path, backup=self.backup_enabled)


class CategoryJsonStorage(JsonStorage[Dict[str, Any]]):
    """
    Storage for category-based JSON files where data has the structure:
    { "category_name": { "item_id": {...}, "item_id2": {...} } }
    """
    
    def __init__(self, base_directory: Union[str, Path], category_name: str):
        """
        Initialize category-based JSON storage.
        
        Args:
            base_directory: Base directory for storing JSON files
            category_name: Name of the category (used as key in the JSON)
        """
        super().__init__(base_directory)
        self.category_name = category_name
        
    def load_category(self, filename: str) -> Dict[str, Any]:
        """
        Load a category of items from a JSON file.
        
        Args:
            filename: Name of the file to load
            
        Returns:
            Dictionary of items in the category, empty dict if file doesn't exist or there was an error
        """
        data = self.load(filename)
        if not data:
            return {}
            
        # Return the category data or empty dict if not found
        return data.get(self.category_name, {})
        
    def save_category(self, filename: str, items: Dict[str, Any]) -> bool:
        """
        Save a category of items to a JSON file.
        
        Args:
            filename: Name of the file to save
            items: Dictionary of items to save
            
        Returns:
            bool: True if save was successful, False otherwise
        """
        # Load existing data or create new structure
        data = self.load(filename) or {}
        
        # Update category data
        data[self.category_name] = items
        
        # Save updated data
        return self.save(filename, data)
        
    def get_item(self, filename: str, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific item from a category.
        
        Args:
            filename: Name of the file to load
            item_id: ID of the item to retrieve
            
        Returns:
            Item data or None if not found
        """
        items = self.load_category(filename)
        return items.get(item_id)
        
    def save_item(self, filename: str, item_id: str, item_data: Dict[str, Any]) -> bool:
        """
        Save a specific item to a category.
        
        Args:
            filename: Name of the file to save
            item_id: ID of the item to save
            item_data: Data for the item
            
        Returns:
            bool: True if save was successful, False otherwise
        """
        # Load existing items
        items = self.load_category(filename)
        
        # Update item
        items[item_id] = item_data
        
        # Save updated items
        return self.save_category(filename, items)
        
    def delete_item(self, filename: str, item_id: str) -> bool:
        """
        Delete a specific item from a category.
        
        Args:
            filename: Name of the file to modify
            item_id: ID of the item to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        # Load existing items
        items = self.load_category(filename)
        
        # Check if item exists
        if item_id not in items:
            return True  # Item doesn't exist, so deletion is technically successful
            
        # Remove item
        del items[item_id]
        
        # Save updated items
        return self.save_category(filename, items)