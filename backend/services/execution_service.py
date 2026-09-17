"""
Execution & Self-Correction Loop service.
Executes validated SQL with safety overrides, implements deterministic error repair,
and manages query execution with timeouts and result limits.
"""
import asyncio
import difflib
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
from asyncpg import exceptions as pg_exceptions

from backend.core.config import settings
from backend.core.exceptions import (
    QueryExecutionError,
    LLMServiceError,
    DatabaseConnectionError
)
from backend.core.logger import app_logger
from backend.services.connection_service import connection_service
from backend.services.validation_service import ValidationService


class ExecutionService:
    """Handles SQL execution with safety overrides and self-correction."""

    def __init__(self, validation_service: ValidationService):
        self.validation_service = validation_service
        self._query_count = 0
        self._error_patterns = {
            # Common error patterns for deterministic repair
            pg_exceptions.UndefinedColumnError: self._handle_undefined_column,
            pg_exceptions.UndefinedTableError: self._handle_undefined_table,
            # Add more as needed
        }

    async def execute_query(
        self,
        sql: str,
        connection_id: str,
        credentials: dict
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Execute a SQL query with safety overrides.

        Args:
            sql: SQL query to execute
            connection_id: Unique identifier for this connection
            credentials: Database connection parameters

        Returns:
            Tuple of (query_results, execution_metadata)
        """
        start_time = time.time()
        self._query_count += 1

        try:
            # Validate SQL first (defense in depth)
            is_valid, validation_errors = self.validation_service.validate_sql(sql)
            if not is_valid:
                raise QueryExecutionError(
                    f"SQL validation failed: {', '.join(validation_errors)}",
                    details={'validation_errors': validation_errors}
                )

            # Get connection from pool
            async with connection_service.get_connection() as conn:
                # Set session-level safety overrides
                await conn.execute("SET LOCAL TRANSACTION READ ONLY")
                await conn.execute(f"SET LOCAL statement_timeout = '{settings.STATEMENT_TIMEOUT_MS}ms'")

                # Execute the query
                result = await conn.fetch(sql)

                # Convert to list of dictionaries
                rows = [dict(row) for row in result]

                execution_time = (time.time() - start_time) * 1000  # milliseconds

                # Prepare metadata
                metadata = {
                    'query_id': self._query_count,
                    'execution_time_ms': round(execution_time, 2),
                    'rows_returned': len(rows),
                    'connection_id': connection_id,
                    'sql': sql,
                    'cached': False
                }

                app_logger.info(
                    f"Query executed successfully: {len(rows)} rows in {execution_time:.2f}ms"
                )

                return rows, metadata

        except asyncpg.PostgresError as e:
            execution_time = (time.time() - start_time) * 1000
            app_logger.warning(f"Query execution failed: {e}")

            # Prepare error metadata
            error_metadata = {
                'query_id': self._query_count,
                'execution_time_ms': round(execution_time, 2),
                'connection_id': connection_id,
                'sql': sql,
                'error_type': type(e).__name__,
                'error_message': str(e),
                'failed': True
            }

            # Re-raise as our exception type
            raise QueryExecutionError(
                f"Query execution failed: {str(e)}",
                details=error_metadata
            ) from e

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            app_logger.error(f"Unexpected error during query execution: {e}")

            error_metadata = {
                'query_id': self._query_count,
                'execution_time_ms': round(execution_time, 2),
                'connection_id': connection_id,
                'sql': sql,
                'error_type': type(e).__name__,
                'error_message': str(e),
                'failed': True
            }

            raise QueryExecutionError(
                f"Query execution failed: {str(e)}",
                details=error_metadata
            ) from e

    async def execute_with_self_correction(
        self,
        initial_sql: str,
        user_question: str,
        connection_id: str,
        credentials: dict,
        llm_service: Any,  # LLMService instance
        schema_chunks: List[Dict[str, Any]],
        max_attempts: int = 3
    ) -> Tuple[
        List[Dict[str, Any]],  # final results
        Dict[str, Any],       # final metadata
        List[Dict[str, Any]]  # attempt history
    ]:
        """
        Execute query with self-correction loop for deterministic error repair.

        Args:
            initial_sql: Initial SQL query to try
            user_question: Original user question
            connection_id: Connection identifier
            credentials: Database credentials
            llm_service: LLM service for generating corrections
            schema_chunks: Schema context for LLM
            max_attempts: Maximum number of attempts

        Returns:
            Tuple of (results, metadata, attempt_history)
        """
        attempt_history = []
        current_sql = initial_sql

        for attempt in range(max_attempts):
            attempt_start = time.time()
            attempt_info = {
                'attempt_number': attempt + 1,
                'timestamp': attempt_start,
                'sql': current_sql
            }

            try:
                # Try to execute the query
                results, execution_metadata = await self.execute_query(
                    current_sql, connection_id, credentials
                )

                # Success!
                attempt_info['outcome'] = 'success'
                attempt_info['execution_metadata'] = execution_metadata
                attempt_history.append(attempt_info)

                # Prepare final metadata
                final_metadata = {
                    'total_attempts': attempt + 1,
                    'successful_attempt': attempt + 1,
                    'final_sql': current_sql,
                    'query_id': execution_metadata.get('query_id'),
                    'execution_time_ms': execution_metadata.get('execution_time_ms'),
                    'rows_returned': execution_metadata.get('rows_returned'),
                    'connection_id': connection_id,
                    'self_correction_used': attempt > 0
                }

                return results, final_metadata, attempt_history

            except QueryExecutionError as e:
                # Query execution failed - try to fix it
                attempt_info['outcome'] = 'execution_failed'
                attempt_info['error'] = str(e)
                attempt_info['error_details'] = getattr(e, 'details', {})
                attempt_history.append(attempt_info)

                # If we have attempts left, try to correct the SQL
                if attempt < max_attempts - 1:
                    corrected_sql = await self._attempt_sql_correction(
                        current_sql,
                        e,
                        user_question,
                        connection_id,
                        credentials,
                        llm_service,
                        schema_chunks
                    )

                    if corrected_sql and corrected_sql != current_sql:
                        attempt_info['corrected_sql'] = corrected_sql
                        current_sql = corrected_sql
                        app_logger.info(f"Attempt {attempt + 1} failed, retrying with corrected SQL")
                        continue
                    else:
                        # Could not correct, break out
                        break
                else:
                    # No more attempts
                    break

            except Exception as e:
                # Unexpected error
                attempt_info['outcome'] = 'unexpected_error'
                attempt_info['error'] = str(e)
                attempt_history.append(attempt_info)
                break

        # If we get here, all attempts failed
        # Return the last attempt's error information
        last_attempt = attempt_history[-1] if attempt_history else {}
        error_metadata = last_attempt.get('error_details', {})

        # Create a minimal error result
        error_result = [{
            'error': last_attempt.get('error', 'Unknown error'),
            'error_type': last_attempt.get('error_details', {}).get('error_type', 'Unknown'),
            'attempts_made': len(attempt_history)
        }]

        final_metadata = {
            'total_attempts': len(attempt_history),
            'successful_attempt': None,
            'final_sql': current_sql,
            'execution_time_ms': 0,
            'rows_returned': 0,
            'connection_id': connection_id,
            'self_correction_used': False,
            'failed': True,
            'error_details': error_metadata
        }

        return error_result, final_metadata, attempt_history

    async def _attempt_sql_correction(
        self,
        failed_sql: str,
        error: QueryExecutionError,
        user_question: str,
        connection_id: str,
        credentials: dict,
        llm_service: Any,
        schema_chunks: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Attempt to correct a failed SQL query using deterministic error repair.

        Args:
            failed_sql: The SQL query that failed
            error: The execution error that occurred
            user_question: Original user question
            connection_id: Connection identifier
            credentials: Database credentials
            llm_service: LLM service
            schema_chunks: Schema context

        Returns:
            Corrected SQL query or None if correction not possible
        """
        try:
            error_details = getattr(error, 'details', {})
            error_type = error_details.get('error_type')
            error_message = error_details.get('error_message', '')

            # Try deterministic repair first based on error type
            corrected_sql = None

            if error_type in self._error_patterns:
                repair_func = self._error_patterns[error_type]
                corrected_sql = await repair_func(
                    failed_sql, error_message, schema_chunks
                )

            # If deterministic repair didn't work, try LLM-based correction
            if not corrected_sql:
                corrected_sql = await self._llm_based_correction(
                    failed_sql, error_message, user_question,
                    connection_id, credentials, llm_service, schema_chunks
                )

            return corrected_sql

        except Exception as e:
            app_logger.warning(f"SQL correction attempt failed: {e}")
            return None

    async def _handle_undefined_column(
        self,
        failed_sql: str,
        error_message: str,
        schema_chunks: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Handle 'column does not exist' errors using difflib to suggest alternatives.

        Args:
            failed_sql: The SQL that failed
            error_message: Error message from database
            schema_chunks: Schema context for finding alternatives

        Returns:
            Corrected SQL or None
        """
        # Extract the missing column name from error message
        # Example: "column \"user_id\" does not exist"
        column_match = re.search(r'column\s*["\']?(\w+)["\']?\s*does not exist', error_message, re.IGNORECASE)
        if not column_match:
            return None

        missing_column = column_match.group(1)
        app_logger.debug(f"Handling undefined column error for: {missing_column}")

        # Extract all column names from schema chunks
        all_columns = set()
        for chunk in schema_chunks:
            metadata = chunk.get('metadata', {})
            # This is simplified - in practice you'd parse the chunk text or have better metadata
            # For now, we'll look for column patterns in the text
            column_matches = re.findall(r'\b(\w+)\s*:', chunk['text'])
            all_columns.update(column_matches)

        # Find close matches using difflib
        close_matches = difflib.get_close_matches(
            missing_column,
            list(all_columns),
            n=3,
            cutoff=0.6
        )

        if not close_matches:
            return None

        # Try replacing the missing column with the best match
        best_match = close_matches[0]
        app_logger.info(f"Suggesting '{best_match}' for missing column '{missing_column}'")

        # Simple replacement - in practice you'd need to be more careful about context
        # This is a basic implementation - a production version would need proper SQL parsing
        corrected_sql = re.sub(
            rf'\b{re.escape(missing_column)}\b',
            best_match,
            failed_sql,
            flags=re.IGNORECASE
        )

        # Validate that the corrected SQL is different and potentially valid
        if corrected_sql != failed_sql:
            # Quick validation - check if it parses
            try:
                import sqlglot
                sqlglot.parse_one(corrected_sql, read="postgres")
                return corrected_sql
            except:
                return None

        return None

    async def _handle_undefined_table(
        self,
        failed_sql: str,
        error_message: str,
        schema_chunks: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Handle 'table does not exist' errors.

        Args:
            failed_sql: The SQL that failed
            error_message: Error message from database
            schema_chunks: Schema context for finding alternatives

        Returns:
            Corrected SQL or None
        """
        # Similar to column handling but for tables
        table_match = re.search(r'relation\s*["\']?(\w+)["\']?\s*does not exist', error_message, re.IGNORECASE)
        if not table_match:
            # Also try "missing FROM-clause entry for table"
            table_match = re.search(r'missing\s+FROM-clause\s+entry\s+for\s+table\s*["\']?(\w+)["\']?', error_message, re.IGNORECASE)

        if not table_match:
            return None

        missing_table = table_match.group(1)
        app_logger.debug(f"Handling undefined table error for: {missing_table}")

        # Extract table names from schema chunks
        all_tables = set()
        for chunk in schema_chunks:
            metadata = chunk.get('metadata', {})
            schema_name = metadata.get('schema_name')
            table_name = metadata.get('table_name')
            if schema_name and table_name:
                full_name = f"{schema_name}.{table_name}"
                all_tables.add(full_name)
                all_tables.add(table_name)  # Also add just table name

        # Find close matches
        close_matches = difflib.get_close_matches(
            missing_table,
            list(all_tables),
            n=3,
            cutoff=0.6
        )

        if not close_matches:
            return None

        best_match = close_matches[0]
        app_logger.info(f"Suggesting '{best_match}' for missing table '{missing_table}'")

        # Simple replacement
        corrected_sql = re.sub(
            rf'\b{re.escape(missing_table)}\b',
            best_match,
            failed_sql,
            flags=re.IGNORECASE
        )

        if corrected_sql != failed_sql:
            # Quick validation
            try:
                import sqlglot
                sqlglot.parse_one(corrected_sql, read="postgres")
                return corrected_sql
            except:
                return None

        return None

    async def _llm_based_correction(
        self,
        failed_sql: str,
        error_message: str,
        user_question: str,
        connection_id: str,
        credentials: dict,
        llm_service: Any,
        schema_chunks: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Use LLM to correct SQL based on error message.

        Args:
            failed_sql: The SQL that failed
            error_message: Error message from database
            user_question: Original user question
            connection_id: Connection identifier
            credentials: Database credentials
            llm_service: LLM service
            schema_chunks: Schema context

        Returns:
            Corrected SQL from LLM or None
        """
        try:
            # Create a correction prompt
            correction_prompt = f"""
            The following SQL query failed to execute with the error provided below.
            Please correct the SQL query to fix the error while still answering the original question.

            ORIGINAL QUESTION: {user_question}

            FAILED SQL:
            ```sql
            {failed_sql}
            ```

            ERROR MESSAGE:
            {error_message}

            INSTRUCTIONS:
            1. Fix the SQL to resolve the error
            2. Ensure it still answers the original question
            3. Only generate SELECT statements
            4. Return ONLY the corrected SQL in a markdown code block
            5. Do not include explanations

            CORRECTED SQL:
            ```sql
            """

            # Get response from LLM
            response_text, _ = await llm_service.generate_sql(
                schema_chunks, correction_prompt, temperature=0.0  # Low temperature for correction
            )

            # Extract SQL from response
            import re
            sql_match = re.search(r'```sql\s*(.*?)\s*```', response_text, re.IGNORECASE | re.DOTALL)
            if sql_match:
                corrected_sql = sql_match.group(1).strip()
                # Basic validation
                if corrected_sql and len(corrected_sql) > 5:
                    try:
                        import sqlglot
                        sqlglot.parse_one(corrected_sql, read="postgres")
                        return corrected_sql
                    except:
                        pass

            return None

        except Exception as e:
            app_logger.warning(f"LLM-based correction failed: {e}")
            return None

    def get_query_stats(self) -> Dict[str, Any]:
        """
        Get execution statistics.

        Returns:
            Dictionary of execution statistics
        """
        return {
            'total_queries_executed': self._query_count,
            'service_uptime': time.time() - getattr(self, '_start_time', time.time())
        }