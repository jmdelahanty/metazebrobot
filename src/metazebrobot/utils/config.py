"""
Configuration management for the MetaZebrobot application.

This module handles loading, validating, and accessing the application configuration.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """Manages application configuration."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration manager.
        
        Args:
            config_path: Path to the configuration file. If None, looks for config.json
                         in the current directory and then in parent directories.
        """
        self.config_data: Dict[str, Any] = {}
        self._config_path = config_path
        self._is_initialized = False
        
    def load_config(self) -> bool:
        """Load configuration from file."""
        try:
            config_file = self._find_config_file()
            
            if not config_file or not config_file.exists():
                print(f"Configuration file not found: {config_file}")
                return False
            
            print(f"Loading configuration from: {config_file}")
            with open(config_file, 'r') as f:
                self.config_data = json.load(f)
            
            print(f"Loaded configuration: {self.config_data}")
            self._is_initialized = True
            return True
            
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return False
    
    @property
    def is_initialized(self) -> bool:
        """Check if configuration has been successfully loaded."""
        return self._is_initialized
        
    def _find_config_file(self) -> Optional[Path]:
        """Search for config.json in the current directory and parent directories."""
        # Try looking at the project root (two directories up from this file)
        config_file = Path(__file__).absolute().parent.parent.parent.parent / 'config.json'
        
        print(f"Looking for config file at: {config_file}")
        
        if config_file.exists():
            print(f"Found config file at: {config_file}")
            return config_file
        
        # Fall back to the current directory method if the explicit path doesn't work
        current_dir = Path.cwd()
        
        # Try current directory
        config_file = current_dir / 'config.json'
        if config_file.exists():
            return config_file
        
        # Try up to 3 parent directories
        for _ in range(3):
            current_dir = current_dir.parent
            config_file = current_dir / 'config.json'
            if config_file.exists():
                return config_file
        
        return None
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: The configuration key to retrieve
            default: The default value to return if key is not found
            
        Returns:
            The configuration value, or default if not found
        """
        return self.config_data.get(key, default)
    
    def get_path(self, key: str) -> Optional[Path]:
        """Get a configuration value as a Path object."""
        path_str = self.get(key)
        if not path_str:
            print(f"No path found for key: {key}")
            return None
        
        print(f"Converting path for key '{key}': {path_str}")
        
        try:
            # Handle environment variables in paths
            if '$' in path_str:
                path_str = os.path.expandvars(path_str)
            
            return Path(path_str)
        except Exception as e:
            print(f"Error converting path: {e}")
            return None
    
    @property
    def material_data_dir(self) -> Path:
        """Get the materials data directory."""
        return self.get_path('remote_material_data_directory')
    
    @property
    def dish_data_dir(self) -> Path:
        """Get the dishes data directory."""
        return self.get_path('remote_dish_data_directory')


# Create a singleton instance for global access
config = ConfigManager()