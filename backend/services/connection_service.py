"""
Database Connection Pool Manager service.
Handles encrypted credential storage, connection management, and session safety.
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Tuple
from urllib.parse import quote_plus, urlencode

import asyncpg
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os

from backend.core.config import settings
from backend.core.exceptions import DatabaseConnectionError, CredentialEncryptionError
from backend.core.logger import app_logger


class ConnectionService:
    """Manages database connections with credential encryption and safety enforcement."""

    def __init__(self):
        self._connection_pool: Optional[asyncpg.Pool] = None
        self._encryption_key: bytes = self._derive_encryption_key(
            settings.ENCRYPTION_KEY)
        self._cipher = Fernet(self._encryption_key)

    def _derive_encryption_key(self, key: str) -> bytes:
        """Derive a proper encryption key from the provided string."""
        # Use PBKFT2 to derive a 32-byte key for Fernet
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'promptql_salt',  # In production, use a random salt stored separately
            iterations=100000,
        )
        key_bytes = key.encode('utf-8')
        derived_key = base64.urlsafe_b64encode(kdf.derive(key_bytes))
        return derived_key

    def _build_dsn(self, credentials: dict) -> str:
        """
        Build PostgreSQL DSN with appropriate SSL settings for different providers.

        Args:
            credentials: Database connection parameters

        Returns:
            PostgreSQL DSN string
        """
        host = credentials.get('host', '')
        user = credentials.get('username', '')
        password = quote_plus(credentials.get('password', ''))
        port = credentials.get('port', 5432)
        dbname = credentials.get('database', '')

        dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

        if host.endswith('.neon.tech'):
            dsn += "?sslmode=require"

        return dsn

    def encrypt_credentials(self, credentials: dict) -> str:
        """
        Encrypt database credentials for storage.

        Args:
            credentials: Dictionary containing connection parameters

        Returns:
            Encrypted credentials as string
        """
        try:
            credentials_json = json.dumps(credentials)
            encrypted_data = self._cipher.encrypt(
                credentials_json.encode('utf-8'))
            return encrypted_data.decode('utf-8')
        except Exception as e:
            app_logger.error(f"Failed to encrypt credentials: {e}")
            raise CredentialEncryptionError(
                "Failed to encrypt credentials") from e

    def decrypt_credentials(self, encrypted_credentials: str) -> dict:
        """
        Decrypt database credentials from storage.

        Args:
            encrypted_credentials: Encrypted credentials string

        Returns:
            Decrypted credentials dictionary
        """
        try:
            decrypted_data = self._cipher.decrypt(
                encrypted_credentials.encode('utf-8'))
            credentials_json = decrypted_data.decode('utf-8')
            return json.loads(credentials_json)
        except Exception as e:
            app_logger.error(f"Failed to decrypt credentials: {e}")
            raise CredentialEncryptionError(
                "Failed to decrypt credentials") from e

    async def initialize_pool(self, credentials: dict) -> None:
        """
        Initialize the connection pool with given credentials.

        Args:
            credentials: Database connection parameters
        """
        try:
            # Construct connection string with appropriate SSL settings
            dsn = self._build_dsn(credentials)

            # Create connection pool
            self._connection_pool = await asyncpg.create_pool(
                dsn,
                min_size=1,
                max_size=10,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
                setup=self._setup_connection,
                init=self._init_connection,
            )

            app_logger.info(
                "Database connection pool initialized successfully")

        except Exception as e:
            app_logger.error(f"Failed to initialize connection pool: {e}")
            raise DatabaseConnectionError(
                "Failed to initialize connection pool") from e

    async def _setup_connection(self, connection):
        """Setup connection with required parameters."""
        await connection.execute("SET timezone TO 'UTC'")

    async def _init_connection(self, connection):
        """Initialize connection with safety settings."""
        # Enforce read-only transaction and statement timeout
        await connection.execute("SET LOCAL TRANSACTION READ ONLY")
        await connection.execute(f"SET LOCAL statement_timeout = '{settings.STATEMENT_TIMEOUT_MS}ms'")

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """
        Get a database connection from the pool with automatic cleanup.

        Yields:
            asyncpg.Connection: Database connection
        """
        if not self._connection_pool:
            raise DatabaseConnectionError("Connection pool not initialized")

        connection = None
        try:
            connection = await self._connection_pool.acquire()
            yield connection
        except Exception as e:
            app_logger.error(f"Error getting database connection: {e}")
            raise DatabaseConnectionError(
                "Failed to get database connection") from e
        finally:
            if connection:
                await self._connection_pool.release(connection)

    async def close_pool(self) -> None:
        """Close the connection pool."""
        if self._connection_pool:
            await self._connection_pool.close()
            self._connection_pool = None
            app_logger.info("Database connection pool closed")

    async def health_check(self) -> bool:
        """
        Check if the database connection is healthy.

        Returns:
            bool: True if healthy, False otherwise
        """
        if not self._connection_pool:
            return False

        try:
            async with self.get_connection() as connection:
                result = await connection.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            app_logger.warning(f"Database health check failed: {e}")
            return False

    async def test_connection(self, credentials: dict) -> Tuple[bool, Optional[str]]:
        """
        Test a database connection with given credentials.

        Args:
            credentials: Database connection parameters

        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """
        try:
            # Construct connection string with appropriate SSL settings
            dsn = self._build_dsn(credentials)

            # Test connection
            conn = await asyncpg.connect(dsn, timeout=10)
            # Test safety settings
            await conn.execute("SET LOCAL TRANSACTION READ ONLY")
            await conn.execute(f"SET LOCAL statement_timeout = '{settings.STATEMENT_TIMEOUT_MS}ms'")
            # Test basic query
            result = await conn.fetchval("SELECT 1")
            await conn.close()
            return result == 1, None
        except asyncpg.InvalidPasswordError as e:
            app_logger.error(f"Invalid password for database connection: {e}")
            return False, "Invalid password - please check your credentials"
        except asyncpg.InvalidAuthorizationSpecificationError as e:
            app_logger.error(f"Invalid authorization specification: {e}")
            return False, "Authentication failed - please check username and password"
        except asyncpg.CannotConnectNowError as e:
            app_logger.error(f"Cannot connect to server: {e}")
            return False, "Cannot connect to database server - please check host and port"
        except asyncpg.PostgresError as e:
            app_logger.error(f"PostgreSQL error: {e}")
            error_msg = str(e).lower()
            if "ssl" in error_msg or "tls" in error_msg:
                return False, "SSL/TLS connection required - this host may need SSL mode"
            elif "connection" in error_msg and "refused" in error_msg:
                return False, "Connection refused - please check host, port, and network connectivity"
            elif "database" in error_msg and "does not exist" in error_msg:
                return False, "Database does not exist - please check the database name"
            else:
                return False, f"Database connection failed: {str(e)}"
        except Exception as e:
            app_logger.error(f"Connection test failed: {e}")
            return False, f"Connection failed: {str(e)}"


# Global connection service instance
connection_service = ConnectionService()
