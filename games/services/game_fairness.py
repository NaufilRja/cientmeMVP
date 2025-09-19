import hashlib
import secrets
from cryptography.fernet import Fernet
from django.conf import settings  # import project-wide key

class GameFairness:
    """
    Handles fairness logic for games:
    - Salt generation
    - Hashing winning numbers
    - Encryption/Decryption of winning numbers
    """

    @staticmethod
    def generate_salt() -> str:
        """Generate a random salt for hashing."""
        return secrets.token_hex(16)

    @staticmethod
    def hash_value(winning_numbers: str, salt: str) -> str:
        """
        Compute SHA-256 hash of winning numbers + salt for transparency.
        """
        return hashlib.sha256((winning_numbers + salt).encode()).hexdigest()

    @staticmethod
    def encrypt_numbers(winning_numbers: str, secret_key: bytes = settings.FERNET_SECRET_KEY) -> str:
        """
        Encrypt winning numbers using Fernet.
        Default key is the project-wide FERNET_SECRET_KEY.
        """
        f = Fernet(secret_key)
        return f.encrypt(winning_numbers.encode()).decode()  # store as string

    @staticmethod
    def decrypt_numbers(encrypted_numbers: str, secret_key: bytes = settings.FERNET_SECRET_KEY) -> str:
        """
        Decrypt encrypted winning numbers using Fernet.
        Default key is the project-wide FERNET_SECRET_KEY.
        """
        f = Fernet(secret_key)
        return f.decrypt(encrypted_numbers.encode()).decode()
