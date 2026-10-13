"""
Main application entry point for PromptQL backend.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

import uuid
from backend.core.config import settings
from backend.core.logger import app_logger
from backend.services.connection_service import connection_service
from backend.services.schema_service import SchemaService
from backend.services.retrieval_service import RetrievalService
from backend.services.llm_service import LLMService
from backend.services.validation_service import ValidationService
from backend.services.execution_service import ExecutionService
from backend.db.base import AsyncSessionLocal
from backend.db.models import ConnectionMetadata
from sqlalchemy import text


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
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
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
    _: str = Depends(verify_token),
):
    """
    Store a new database connection.
    """
    # Extract flat fields from frontend
    host = connection_data.get("host")
    port = connection_data.get("port")
    database = connection_data.get("database")
    username = connection_data.get("username")
    password = connection_data.get("password")
    connection_name = connection_data.get("connection_name")

    # Validate required fields
    if not all([host, port, database, username, password]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="host, port, database, username, and password are required",
        )

    # Generate connection ID
    connection_id = str(uuid.uuid4())

    # Build credentials dict
    credentials = {
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password": password
    }

    # Test connection before storing
    app_logger.info(f"Testing connection for {connection_id}")
    is_valid, error_message = await connection_service.test_connection(credentials)
    if not is_valid:
        detail = error_message or "Failed to connect to database with provided credentials"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    # Encrypt credentials for storage
    encrypted_credentials = connection_service.encrypt_credentials(credentials)

    # Persist connection metadata to database
    async with AsyncSessionLocal() as db_session:
        connection_metadata = ConnectionMetadata(
            connection_id=connection_id,
            connection_name=connection_name or f"Connection {connection_id[:8]}",
            encrypted_credentials=encrypted_credentials
        )
        db_session.add(connection_metadata)
        await db_session.commit()

    # Extract and store schema for the connection
    try:
        app_logger.info(f"Extracting schema for connection {connection_id}")
        schema_info = await schema_service.extract_schema(connection_id, credentials)
        schema_chunks = await schema_service.get_schema_text_chunks(schema_info)
        # Set connection_id in chunk metadata
        for chunk in schema_chunks:
            chunk['metadata']['connection_id'] = connection_id
        await schema_service.store_schema_embeddings(connection_id, schema_chunks)
        app_logger.info(f"Schema extraction and storage completed for connection {connection_id}")
    except Exception as e:
        app_logger.error(f"Failed to extract and store schema for connection {connection_id}: {e}")
        # Don't fail the connection creation if schema extraction fails
        # The connection is still valid, just without schema search capabilities

    app_logger.info(
        f"Connection {connection_id} ({connection_name}) validated and stored")
    return {
        "connection_id": connection_id,
        "message": "Connection validated and stored successfully",
    }


@app.post("/query", tags=["query"])
async def execute_query(
    query_data: dict,
    _: str = Depends(verify_token),
):
    """
    Execute a natural language query against a database connection with self-correction loop.
    """
    connection_id = query_data.get("connection_id")
    question = query_data.get("question")

    if not connection_id or not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="connection_id and question are required",
        )

    # Get connection credentials from database
    try:
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                text("SELECT encrypted_credentials FROM connection_metadata WHERE connection_id = :connection_id"),
                {"connection_id": connection_id}
            )
            row = result.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Connection not found: {connection_id}"
                )
            encrypted_credentials = row[0]
            credentials = connection_service.decrypt_credentials(encrypted_credentials)
    except Exception as e:
        app_logger.error(f"Failed to retrieve credentials for connection {connection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve connection credentials"
        )

    # Get schema information from cache or extract if not present
    try:
        # Check if schema is cached
        if connection_id in schema_service._schema_cache:
            schema_info = schema_service._schema_cache[connection_id]
            app_logger.debug(f"Using cached schema for connection {connection_id}")
        else:
            # Extract schema
            app_logger.info(f"Extracting schema for connection {connection_id}")
            schema_info = await schema_service.extract_schema(connection_id, credentials, force_refresh=False)
            app_logger.info(f"Schema extracted successfully for connection {connection_id}")
    except Exception as e:
        app_logger.error(f"Failed to extract schema for connection {connection_id}: {e}")
        # If we fail, we will set schema_info to None and fall back to retrieval service for schema chunks
        schema_info = None

    # Convert schema information to a string
    schema_string = None
    if schema_info is not None:
        try:
            # Helper function to convert schema info to string
            def _schema_info_to_string(schema_info: Dict[str, Any]) -> str:
                """
                Convert schema information to a DDL-like string.

                Args:
                    schema_info: Schema information from extract_schema

                Returns:
                    A string containing the schema in a DDL-like format.
                """
                lines = []
                for schema_name, tables in schema_info.items():
                    for table_name, table_info in tables.items():
                        lines.append(f"Table: {schema_name}.{table_name}")
                        lines.append(f"Type: {table_info['table_type']}")
                        if table_info.get('comment'):
                            lines.append(f"Comment: {table_info['comment']}")
                        # Columns
                        column_lines = []
                        for column in table_info['columns']:
                            col_desc = f"  {column['name']}: {column['data_type']}"
                            if not column['is_nullable']:
                                col_desc += " NOT NULL"
                            if column['is_primary_key']:
                                col_desc += " PRIMARY KEY"
                            if column['is_foreign_key']:
                                # Find the foreign key info for this column
                                fk_info = next(
                                    (fk for fk in table_info['foreign_keys']
                                     if fk['column_name'] == column['name']),
                                    None
                                )
                                if fk_info:
                                    col_desc += f" (FK -> {fk_info['foreign_table_schema']}.{fk_info['foreign_table_name']}({fk_info['foreign_column_name']}))"
                            if column.get('comment'):
                                col_desc += f" Comment: {column['comment']}"
                            column_lines.append(col_desc)
                        if column_lines:
                            lines.append("Columns:")
                            lines.extend(column_lines)
                        # Primary key
                        if table_info['primary_key']:
                            lines.append(f"Primary Key: {', '.join(table_info['primary_key'])}")
                        # Indexes
                        if table_info['indexes']:
                            index_lines = []
                            for idx in table_info['indexes']:
                                index_lines.append(f"  {idx['name']}: {idx['definition']}")
                            if index_lines:
                                lines.append("Indexes:")
                                lines.extend(index_lines)
                        lines.append("")  # Empty line between tables
                return "\n".join(lines)

            schema_string = _schema_info_to_string(schema_info)
            app_logger.debug(f"Converted schema to string (length: {len(schema_string)} chars)")
        except Exception as e:
            app_logger.error(f"Failed to convert schema to string for connection {connection_id}: {e}")
            schema_string = None
    else:
        app_logger.warning("Schema information is not available, falling back to retrieval service for schema chunks.")

    # If we have schema_string, we will use it and not retrieve schema chunks.
    # If we don't have schema_string, we will fall back to retrieving schema chunks from retrieval service.
    if schema_string is None:
        # Fallback to retrieval service for schema chunks
        try:
            schema_chunks = await retrieval_service.search_and_rank(
                connection_id=connection_id,
                query_text=question,
                limit=5,
            )
            app_logger.debug(f"Retrieved {len(schema_chunks)} schema chunks from retrieval service (fallback)")
            if schema_chunks:
                first_chunk_preview = schema_chunks[0].get('text', '')[:200] if schema_chunks[0].get('text') else ''
                app_logger.debug(f"First schema chunk preview from retrieval (fallback): {first_chunk_preview}")
            else:
                app_logger.debug("No schema chunks retrieved from retrieval service (fallback)")
        except Exception as e:
            app_logger.error(
                f"Failed to retrieve schema for connection {connection_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve schema",
            )
    else:
        # We have schema_string, so we set schema_chunks to None to indicate we are not using retrieval chunks
        schema_chunks = None

    # Retrieve golden queries for few-shot examples
    try:
        golden_queries = await retrieval_service.retrieve_golden_queries(
            connection_id=connection_id,
            question=question,
            limit=2
        )
        app_logger.debug(f"Retrieved {len(golden_queries)} golden queries for connection {connection_id}")
        if golden_queries:
            for i, gq in enumerate(golden_queries):
                app_logger.debug(f"Golden query {i+1}: Q='{gq['question'][:50]}...' → SQL='{gq['sql'][:50]}...' (similarity: {gq['similarity_score']:.3f})")
    except Exception as e:
        app_logger.error(f"Failed to retrieve golden queries for connection {connection_id}: {e}")
        golden_queries = []  # Continue without golden queries

    # SEMANTIC CACHING: Check if we have a golden query with high similarity score
    cached_sql = None
    if golden_queries:
        # Sort by similarity score descending to get the best match first
        sorted_queries = sorted(golden_queries, key=lambda x: x.get('similarity_score', 0), reverse=True)
        best_match = sorted_queries[0]
        if best_match.get('similarity_score', 0) >= 0.98:
            cached_sql = best_match.get('sql')
            app_logger.info(f"Cache hit: skipping LLM generation, reusing golden query (similarity: {best_match.get('similarity_score'):.3f})")

    # QUERY COMPLEXITY ROUTING: Classify question as simple or complex using small/fast model
    complexity = "unknown"
    if not cached_sql:  # Only classify if we're not using cached SQL
        try:
            # Use a small/fast model for classification
            classification_prompt = f"""Classify the following question as either "simple" or "complex" based on the SQL query complexity it would likely require.

Simple questions: Basic SELECT queries with WHERE, maybe JOINs, basic aggregations (COUNT, SUM, AVG) on single tables.
Complex questions: Involving subqueries, complex JOINs, window functions, CTEs, nested aggregations, or advanced SQL features.

Question: "{question}"

Respond with ONLY "simple" or "complex"."""

            # Use a faster/cheaper model for classification
            classification_response = await asyncio.to_thread(
                completion,
                model="groq/mixtral-8x7b-32768",  # Using a fast Groq model for classification
                messages=[{"role": "user", "content": classification_prompt}],
                temperature=0.1,
                max_tokens=10,
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1"
            )

            classification_text = classification_response.choices[0].message.content.strip().lower()
            if "simple" in classification_text:
                complexity = "simple"
            elif "complex" in classification_text:
                complexity = "complex"
            else:
                # Default to complex if unclear
                complexity = "complex"

            app_logger.info(f"Query complexity classification: {complexity}")
        except Exception as e:
            app_logger.warning(f"Failed to classify query complexity: {e}")
            complexity = "unknown"

    # Initialize attempt history and error context
    attempt_history = []
    error_context = None
    max_attempts = 3
    sql_query = None
    is_valid = False
    validation_errors = None
    execution_error = None
    execution_success = False  # Initialize to False before the loop
    rows = None
    exec_metadata = None
    sql_gen_metadata = None
    chart_spec = None

    # Check if we have cached SQL from semantic caching
    if cached_sql is not None:
        sql_query = cached_sql
        chart_spec = None  # Cached queries don't come with chart specs from LLM
        sql_gen_metadata = {
            'prompt_length': 0,
            'response_length': 0,
            'model_used': 'cached',
            'temperature': 0.0,
            'tokens_used': 0,
            'sql_extracted': True if sql_query else False,
            'raw_response': ''
        }
        app_logger.info(f"Using cached SQL from golden query (similarity >= 0.98)")
        # Skip to validation and execution with attempt 1
        attempt_range = [1]
    else:
        attempt_range = range(1, max_attempts + 1)

    for attempt in attempt_range:
        app_logger.info(f"Attempt {attempt}/{max_attempts if cached_sql is None else 1} for connection {connection_id}")

        # Generate SQL (with error context if available from previous attempt)
        # Skip LLM generation if we're using cached SQL
        if cached_sql is not None and attempt == 1:
            # We already set sql_query above from cached_sql
            gen_error = None
        else:
            try:
                sql_query, chart_spec, sql_gen_metadata = await llm_service.generate_sql(
                    schema_chunks=schema_chunks,
                    schema_string=schema_string,
                    user_question=question,
                    dialect="postgres",  # We can hardcode or get from settings, but for now hardcode
                    error_context=error_context,
                    golden_queries=golden_queries
                )
            except Exception as e:
                app_logger.error(
                    f"LLM generation failed on attempt {attempt}: {e}")
                sql_query = None
                sql_gen_metadata = None
                # Treat as generation error; we'll capture it in the attempt history
                gen_error = str(e)
            else:
                gen_error = None

        # Record attempt details
        attempt_info = {
            'attempt_number': attempt,
            'generated_sql': sql_query,
            'chart_spec': chart_spec,
            'sql_generation_metadata': sql_gen_metadata,
            'validation_errors': None,
            'execution_error': None,
            'is_valid': False,
            'execution_success': False,
            'rows': None,
            'execution_metadata': None,
            'generation_error': gen_error
        }

        # If generation failed, skip validation and execution
        if sql_query is None:
            attempt_info['validation_errors'] = ["LLM generation failed"]
            attempt_info['execution_error'] = "Skipped due to generation failure"
            attempt_history.append(attempt_info)
            error_context = "LLM generation failed. Please check the LLM service logs."
            continue

        # Validate SQL
        try:
            is_valid, validation_errors = validation_service.validate_sql(
                sql_query)
        except Exception as e:
            app_logger.error(f"Validation error on attempt {attempt}: {e}")
            is_valid = False
            validation_errors = [f"Validation exception: {str(e)}"]

        attempt_info['validation_errors'] = validation_errors
        attempt_info['is_valid'] = is_valid

        if not is_valid:
            # Validation failed, prepare error context for next attempt
            error_context = f"Validation error: {validation_errors}. Please fix the SQL."
            attempt_history.append(attempt_info)
            continue

        # Validation passed, now execute SQL
        try:
            # Look up connection metadata from database
            async with AsyncSessionLocal() as db_session:
                result = await db_session.execute(
                    text("SELECT encrypted_credentials FROM connection_metadata WHERE connection_id = :connection_id"),
                    {"connection_id": connection_id}
                )
                row = result.fetchone()
                if not row:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Connection not found: {connection_id}"
                    )
                encrypted_credentials = row[0]

            # Decrypt credentials
            credentials = connection_service.decrypt_credentials(encrypted_credentials)

            # Execute query with decrypted credentials
            rows, exec_metadata = await execution_service.execute_query(
                sql_query,  # SQL query as first parameter
                connection_id,  # Connection ID as second parameter
                credentials   # Credentials as third parameter
            )
            execution_error = None
            execution_success = True
        except HTTPException:
            # Re-raise HTTPException (e.g., connection not found) to be handled by the outer exception handler
            raise
        except Exception as e:
            app_logger.error(f"Execution error on attempt {attempt}: {e}")
            execution_error = str(e)
            execution_success = False
            rows = None
            exec_metadata = None

        attempt_info['execution_error'] = execution_error
        attempt_info['execution_success'] = execution_success
        attempt_info['rows'] = rows
        attempt_info['execution_metadata'] = exec_metadata

        if execution_success:
            # Success! Break out of the loop.
            attempt_history.append(attempt_info)
            break
        else:
            # Execution failed, prepare error context for next attempt
            error_context = f"Execution error: {execution_error}. Please fix the SQL."
            attempt_history.append(attempt_info)
            continue

    # After the loop, check if we succeeded
    if execution_success and rows is not None:
        # Store as golden query if it succeeded on the first attempt
        if attempt_history and attempt_history[-1]['attempt_number'] == 1 and attempt_history[-1]['execution_success']:
            try:
                await retrieval_service.store_golden_query(
                    connection_id=connection_id,
                    question=question,
                    sql=sql_query
                )
                app_logger.info(f"Stored golden query for connection {connection_id} after successful first attempt")
            except Exception as e:
                app_logger.error(f"Failed to store golden query: {e}")
                # Don't fail the main flow if storing golden query fails

        # Get the chart_spec from the successful attempt (last in attempt_history)
        successful_attempt = attempt_history[-1]
        chart_spec_from_attempt = successful_attempt['chart_spec']

        # Generate summary if row count is small
        summary = None
        if len(rows) < 20:
            summary = await llm_service.generate_summary(question, rows)

        # Generate SQL explanation (lightweight LLM call)
        explanation = None
        try:
            explanation = await llm_service.explain_sql(sql_query)
        except Exception as e:
            app_logger.warning(f"Failed to generate SQL explanation: {e}")
            explanation = None

        # Return successful result along with attempt history
        return {
            "sql": sql_query,
            "results": rows,
            "metadata": exec_metadata,
            "row_count": len(rows),
            "attempt_history": attempt_history,
            "chart_spec": chart_spec_from_attempt,
            "summary": summary,
            "explanation": explanation,
            "cached": cached_sql is not None
        }
    else:
        # All attempts failed
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "All attempts failed to generate valid and executable SQL.",
                "attempt_history": attempt_history
            }
        )


# Include any additional routers if they existed
# For now, we have defined the routes directly above.