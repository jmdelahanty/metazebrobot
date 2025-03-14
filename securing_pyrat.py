#!/usr/bin/env python3
"""
PyRAT API Encrypted Credentials

A minimal module to store PyRAT API credentials securely using Fernet encryption.
"""

import os
import json
import getpass
import base64
from pathlib import Path
from typing import Dict, Any

# You'll need to install this: pip install cryptography
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class CredentialsManager:
    """Manages encrypted storage and retrieval of API credentials."""
    
    def __init__(self, app_name="pyrat"):
        """Initialize the credentials manager."""
        self.app_name = app_name
        self.config_dir = Path.home() / '.config' / app_name
        self.credentials_file = self.config_dir / 'credentials.enc'
        self.salt_file = self.config_dir / 'salt'
    
    def _get_key(self, password: str) -> bytes:
        """Derive encryption key from password and salt."""
        # Load or create salt
        if self.salt_file.exists():
            with open(self.salt_file, 'rb') as f:
                salt = f.read()
        else:
            # Create a new random salt
            salt = os.urandom(16)
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.salt_file, 'wb') as f:
                f.write(salt)
            # Secure the salt file
            os.chmod(self.salt_file, 0o600)
        
        # Derive key from password and salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def save_credentials(self, credentials: Dict[str, str], password: str) -> bool:
        """
        Encrypt and save credentials to file.
        
        Args:
            credentials: Dictionary with 'base_url', 'client_token', 'user_token'
            password: Password to encrypt the credentials
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create directory if needed
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Get encryption key
            key = self._get_key(password)
            cipher = Fernet(key)
            
            # Encrypt credentials
            data = json.dumps(credentials).encode()
            encrypted_data = cipher.encrypt(data)
            
            # Save to file
            with open(self.credentials_file, 'wb') as f:
                f.write(encrypted_data)
            
            # Secure the file
            os.chmod(self.credentials_file, 0o600)
            
            return True
        except Exception as e:
            print(f"Error saving credentials: {str(e)}")
            return False
    
    def load_credentials(self, password: str = None) -> Dict[str, str]:
        """
        Load and decrypt credentials from file.
        
        Args:
            password: Password to decrypt the credentials
            
        Returns:
            Dictionary with credentials or empty dict if loading fails
        """
        # Check environment variables first
        env_credentials = {
            'base_url': os.environ.get('PYRAT_BASE_URL'),
            'client_token': os.environ.get('PYRAT_CLIENT_TOKEN'),
            'user_token': os.environ.get('PYRAT_USER_TOKEN')
        }
        
        if all(env_credentials.values()):
            print("Using credentials from environment variables")
            return env_credentials
        
        # If no credentials file, return empty dict
        if not self.credentials_file.exists() or not self.salt_file.exists():
            return {}
        
        # Prompt for password if not provided
        if password is None:
            password = getpass.getpass("Enter password to decrypt credentials: ")
        
        try:
            # Get encryption key
            key = self._get_key(password)
            cipher = Fernet(key)
            
            # Load and decrypt credentials
            with open(self.credentials_file, 'rb') as f:
                encrypted_data = f.read()
            
            data = cipher.decrypt(encrypted_data)
            credentials = json.loads(data.decode())
            
            return credentials
        except Exception as e:
            print(f"Error loading credentials: {str(e)}")
            return {}
    
    def setup_credentials(self) -> Dict[str, str]:
        """
        Interactive setup for credentials.
        
        Returns:
            Dictionary with the saved credentials
        """
        print(f"Setting up {self.app_name.upper()} API credentials")
        
        # Get credentials from user
        credentials = {
            'base_url': input("Enter API base URL: "),
            'client_token': getpass.getpass("Enter client token: "),
            'user_token': getpass.getpass("Enter user token: ")
        }
        
        # Get password for encryption
        while True:
            password = getpass.getpass("Create a password to encrypt credentials: ")
            confirm = getpass.getpass("Confirm password: ")
            
            if password == confirm:
                break
            print("Passwords don't match, please try again.")
        
        # Save credentials
        if self.save_credentials(credentials, password):
            print(f"Credentials saved to {self.credentials_file}")
        else:
            print("Failed to save credentials")
        
        return credentials

# Simple usage example
if __name__ == "__main__":
    # Create credentials manager
    manager = CredentialsManager(app_name="metazebrobot")
    
    # Check if credentials exist
    if not manager.credentials_file.exists():
        # Setup new credentials
        credentials = manager.setup_credentials()
    else:
        # Load existing credentials
        credentials = manager.load_credentials()
    
    if credentials:
        print("\nCredentials loaded successfully!")
        print(f"Base URL: {credentials['base_url']}")
        print(f"Client Token: {'*' * 8}")
        print(f"User Token: {'*' * 8}")
    else:
        print("Failed to load credentials")