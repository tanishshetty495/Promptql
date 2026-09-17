"""
Main application entry point for PromptQL backend.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.logger import app_logger
from backend.services.connection_service import connection_service
from backend.services.schema_service import SchemaService
from backend.services.retrieval_service import RetrievalService
from backend.services.llm_service import LLMService
from backend.services.validation_service import ValidationService
from backend.services.execution_service import ExecutionService


# Global instances (initialized in lifespan)
schema_service: SchemaService = None
retrieval_service: RetrievalService = None
llm_service: LLMService = None
validation_service: ValidationService = None
execution_service: ExecutionService = None


security = HTTPBearer()


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Verify the JWT token.
    For simplicity, we're using a symmetric secret key and expecting a simple token format.
    In a real application, you would use a proper JWT library.
    """
    token = credentials.credentials
    # For now, we'll just check if the token matches the SECRET_KEY (not secure, just for example)
    # In a real app, you would decode the JWT and verify the signature.
    if token != settings.SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.
    Loads the embedding model and initializes services on startup.
    """
    # Load embedding model by initializing SchemaService
    app_logger.info("Starting PromptQL backend application")
    global schema_service, retrieval_service, llm_service, validation_service, execution_service
    schema_service = SchemaService()  # This loads the embedding model
    retrieval_service = RetrievalService()
    llm_service = LLMService()
    validation_service = ValidationService()
    execution_service = ExecutionService(validation_service)
    app_logger.info("Embedding model and services initialized")
    yield
    # Cleanup on shutdown
    app_logger.info("Shutting down PromptQL backend application")
    await connection_service.close_pool()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "ok"}


@app.post("/connections", tags=["connections"])
async def create_connection(
    connection_data: dict,
    token: str = Depends(verify_token),
):
    """
    Store a new database connection.
    """
    connection_id = connection_data.get("connection_id")
    credentials = connection_data.get("credentials")

    if not connection_id or not credentials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="connection_id and credentials are required",
        )

    # Test connection before storing
    app_logger.info(f"Testing connection for {connection_id}")
    is_valid, error_message = await connection_service.test_connection(credentials)
    if not is_valid:
        detail = error_message or "Failed to connect to database with provided credentials"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    # Encrypt and store credentials (in a real app, you would save to database)
    # For now, we just test and return success
    encrypted_credentials = connection_service.encrypt_credentials(credentials)
    # In a real app, you would save encrypted_credentials to your database
    # associated with connection_id and the current user (from token)

    app_logger.info(
        f"Connection {connection_id} validated and ready for storage")
    return {
        "connection_id": connection_id,
        "message": "Connection validated successfully",
    }


@app.post("/query", tags=["query"])
async def execute_query(
    query_data: dict,
    token: str = Depends(verify_token),
):
    """
    Execute a natural language query against a database connection.
    """
    connection_id = query_data.get("connection_id")
    question = query_data.get("question")

    if not connection_id or not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="connection_id and question are required",
        )

    # Retrieve relevant schema chunks
    try:
        schema_chunks = await retrieval_service.search_and_rank(
            connection_id=connection_id,
            query_text=question,
            limit=5,
        )
    except Exception as e:
        app_logger.error(
            f"Failed to retrieve schema for connection {connection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve schema",
        )

    # Generate SQL using LLM
    try:
        sql_query, _ = await llm_service.generate_sql(
            schema_chunks=schema_chunks,
            user_question=question,
        )
    except Exception as e:
        app_logger.error(
            f"Failed to generate SQL for connection {connection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate SQL",
        )

    if not sql_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not generate SQL query from the question",
        )

    # Validate SQL
    try:
        is_valid, validation_errors = validation_service.validate_sql(
            sql_query)
        if not is_valid:
            app_logger.warning(
                f"Generated SQL validation failed: {validation_errors}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Generated SQL is invalid: {validation_errors}",
            )
    except Exception as e:
        app_logger.error(f"SQL validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SQL validation failed",
        )

    # Execute SQL (read-only)
    try:
        results = await execution_service.execute_query(
            connection_id=connection_id,
            query=sql_query,
            readonly=True,
        )
    except Exception as e:
        app_logger.error(
            f"Failed to execute query for connection {connection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query execution failed: {str(e)}",
        )

    return {
        "connection_id": connection_id,
        "question": question,
        "generated_sql": sql_query,
        "results": results,
    }


# Include any additional routers if they existed
# For now, we have defined the routes directly above.
