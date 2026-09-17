"""
Basic functionality test for PromptQL backend.
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_imports():
    """Test that all modules can be imported."""
    try:
        # Test core imports
        from backend.core.config import settings
        from backend.core.exceptions import PromptQLException
        from backend.core.logger import app_logger

        # Test service imports
        from backend.services.connection_service import ConnectionService
        from backend.services.schema_service import SchemaService
        from backend.services.retrieval_service import RetrievalService
        from backend.services.validation_service import ValidationService
        from backend.services.llm_service import LLMService
        from backend.services.execution_service import ExecutionService

        # Test app imports
        from backend.app.main import app

        # Test utils imports
        from backend.utils.encryption import SimpleEncryptor
        from backend.utils.sql_utils import extract_table_names, extract_column_names

        # Test db imports
        from backend.db.base import Base
        from backend.db.models import ConnectionMetadata, SchemaEmbeddings, QueryHistory

        print("All imports successful!")
        return True

    except Exception as e:
        # Safely print error message for Windows console
        error_msg = str(e).encode('ascii', 'replace').decode('ascii')
        print(f"Import failed: {error_msg}")
        return False

async def test_config():
    """Test configuration loading."""
    try:
        from backend.core.config import settings

        print(f"Project name: {settings.PROJECT_NAME}")
        print(f"Environment: {settings.ENVIRONMENT}")
        print(f"LLM model: {settings.LLM_MODEL}")
        print(f"Embedding model: {settings.EMBEDDING_MODEL}")
        print(f"Statement timeout: {settings.STATEMENT_TIMEOUT_MS}ms")
        print(f"Max output rows: {settings.MAX_OUTPUT_ROWS}")

        print("Configuration loaded successfully!")
        return True

    except Exception as e:
        # Safely print error message for Windows console
        error_msg = str(e).encode('ascii', 'replace').decode('ascii')
        print(f"Configuration test failed: {error_msg}")
        return False

def safe_print(text):
    """Safely print text to Windows console by replacing unsupported characters."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace unsupported characters with ASCII equivalents
        safe_text = text.encode('ascii', 'replace').decode('ascii')
        print(safe_text)

async def main():
    """Run all tests."""
    safe_print("Running PromptQL backend basic tests...\n")

    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
    ]

    results = []
    for test_name, test_func in tests:
        safe_print(f"Running {test_name} test...")
        try:
            result = await test_func()
            results.append((test_name, result))
            if result:
                safe_print(f"PASSED: {test_name} test\n")
            else:
                safe_print(f"FAILED: {test_name} test\n")
        except Exception as e:
            # Safely print error message
            error_msg = str(e).encode('ascii', 'replace').decode('ascii')
            safe_print(f"ERROR: {test_name} test: {error_msg}\n")
            results.append((test_name, False))

    # Summary
    passed = sum(1 for _, result in results if result)
    total = len(results)

    safe_print(f"Test Results: {passed}/{total} passed")

    if passed == total:
        safe_print("All tests passed!")
        return True
    else:
        safe_print("Some tests failed.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)