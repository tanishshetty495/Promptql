"""
AST Validation Guard service.
Uses sqlglot to parse and validate SQL, ensuring only SELECT statements are allowed
and performing deep AST walk to detect hidden mutations.
"""
import sqlglot
from sqlglot import expressions as exp
from typing import Any, Dict, List, Set, Tuple
import re

from backend.core.config import settings
from backend.core.exceptions import QueryValidationError
from backend.core.logger import app_logger


class ValidationService:
    """Validates SQL queries using AST parsing to ensure safety."""

    # Mutations that are never allowed
    MUTATION_NODES = {
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Alter,
        exp.Create,
        # exp.Truncate,  # May not exist in this version
        # exp.Purge,     # May not exist in this version
        # exp.Rename,    # May not exist in this version
        exp.Comment,
        exp.Grant,
        exp.Revoke,
    }

    # Utility expressions that might be problematic in certain contexts
    RESTRICTED_EXPRESSIONS = {
        exp.Execute,  # EXECUTE statements
        # exp.Call,     # Could be used for dangerous stored procedures - may not exist in this version
    }

    def __init__(self):
        pass

    def validate_sql(self, sql: str) -> Tuple[bool, List[str]]:
        """
        Validate SQL query for safety.

        Args:
            sql: SQL query string to validate

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors = []

        try:
            # Parse the SQL
            parsed = sqlglot.parse_one(sql, read="postgres")

            # Check if it's a SELECT statement
            if not isinstance(parsed, exp.Select):
                errors.append("Only SELECT statements are allowed")
                return False, errors

            # Perform deep AST walk to check for mutations
            mutation_errors = self._check_for_mutations(parsed)
            errors.extend(mutation_errors)

            # Check for restricted expressions
            restriction_errors = self._check_restricted_expressions(parsed)
            errors.extend(restriction_errors)

            # Additional safety checks
            safety_errors = self._perform_additional_safety_checks(parsed, sql)
            errors.extend(safety_errors)

            return len(errors) == 0, errors

        except sqlglot.ParseError as e:
            errors.append(f"SQL parsing error: {str(e)}")
            return False, errors
        except Exception as e:
            app_logger.error(f"Unexpected error during SQL validation: {e}")
            errors.append("Validation process encountered an unexpected error")
            return False, errors

    def _check_for_mutations(self, node: exp.Expression) -> List[str]:
        """
        Recursively check AST for mutation operations.

        Args:
            node: Current AST node to check

        Returns:
            List of error messages found
        """
        errors = []

        # Check if current node is a mutation
        for mutation_type in self.MUTATION_NODES:
            if isinstance(node, mutation_type):
                errors.append(f"Mutation operation not allowed: {type(node).__name__}")
                return errors  # Return early on finding a mutation

        # Recursively check child nodes
        for child in node.iter_expressions():
            child_errors = self._check_for_mutations(child)
            errors.extend(child_errors)

        return errors

    def _check_restricted_expressions(self, node: exp.Expression) -> List[str]:
        """
        Check for restricted expressions that might be problematic.

        Args:
            node: Current AST node to check

        Returns:
            List of error messages found
        """
        errors = []

        # Check if current node is restricted
        for restricted_type in self.RESTRICTED_EXPRESSIONS:
            if isinstance(node, restricted_type):
                errors.append(f"Restricted expression not allowed: {type(node).__name__}")

        # Recursively check child nodes
        for child in node.iter_expressions():
            child_errors = self._check_restricted_expressions(child)
            errors.extend(child_errors)

        return errors

    def _perform_additional_safety_checks(
        self,
        parsed: exp.Expression,
        original_sql: str
    ) -> List[str]:
        """
        Perform additional safety checks beyond basic AST validation.

        Args:
            parsed: Parsed SQL AST
            original_sql: Original SQL string

        Returns:
            List of error messages found
        """
        errors = []

        # Check for multiple statements (should be caught by parse_one, but double-check)
        statements = sqlglot.parse(original_sql, read="postgres")
        if len(statements) > 1:
            errors.append("Multiple SQL statements are not allowed")

        # Check for comments that might hide SQL injection
        # This is a basic check - in practice you'd want more sophisticated detection
        if re.search(r'/\\*.*\\*/|--', original_sql, re.IGNORECASE | re.DOTALL):
            # Comments themselves aren't bad, but we'll note them for review
            # In a production system, you might want to strip comments before validation
            pass

        # Check for potentially dangerous functions
        dangerous_functions = {
            'pg_sleep', 'pg_terminate_backend', 'pg_cancel_backend',
            'lo_import', 'lo_export', 'pg_read_file', 'pg_write_file',
            'pg_ls_dir', 'pg_stat_file', 'copy_from', 'copy_to'
        }

        # Find all function calls in the AST
        for func_node in parsed.find_all(exp.Func):
            func_name = func_node.name.lower() if hasattr(func_node, 'name') else ""
            if func_name in dangerous_functions:
                errors.append(f"Potentially dangerous function not allowed: {func_name}")

        # Check for subqueries that might attempt to modify data
        # While SELECT subqueries are generally OK, we want to be cautious
        subquery_count = len(list(parsed.find_all(exp.Subquery)))
        if subquery_count > 10:  # Arbitrary limit to prevent overly complex queries
            errors.append("Too many subqueries (possible obfuscation attempt)")

        # Check for extremely long queries that might cause DoS
        if len(original_sql) > 10000:  # 10K characters limit
            errors.append("Query too long (possible DoS attempt)")

        return errors

    def validate_and_normalize(self, sql: str) -> Tuple[str, bool, List[str]]:
        """
        Validate SQL and return normalized version if valid.

        Args:
            sql: SQL query string to validate

        Returns:
            Tuple of (normalized_sql, is_valid, list_of_error_messages)
        """
        # First, validate
        is_valid, errors = self.validate_sql(sql)

        if not is_valid:
            return sql, False, errors

        # If valid, attempt to normalize (optional)
        try:
            # Parse and re-serialize to normalize formatting
            parsed = sqlglot.parse_one(sql, read="postgres")
            normalized = parsed.sql(dialect="postgres", pretty=True)
            return normalized, True, []
        except Exception as e:
            app_logger.warning(f"Failed to normalize SQL: {e}")
            # Return original if normalization fails
            return sql, True, []

    def suggest_alternatives(
        self,
        error_message: str,
        schema_info: Dict[str, Any]
    ) -> List[str]:
        """
        Suggest alternatives for common SQL errors (used in self-correction).

        Args:
            error_message: Error message from database
            schema_info: Schema information for generating suggestions

        Returns:
            List of suggested alternative queries or corrections
        """
        suggestions = []

        # Handle "column does not exist" errors
        column_not_found_match = re.search(
            r'column ["\']?(\w+)["\']? does not exist',
            error_message,
            re.IGNORECASE
        )
        if column_not_found_match:
            missing_column = column_not_found_match.group(1)
            # In a real implementation, you'd use difflib to find similar column names
            # from the schema_info and suggest them
            suggestions.append(
                f"Column '{missing_column}' not found. Check spelling or use correct column name."
            )

        # Handle "relation does not exist" errors
        relation_not_found_match = re.search(
            r'relation ["\']?(\w+)["\']? does not exist',
            error_message,
            re.IGNORECASE
        )
        if relation_not_found_match:
            missing_table = relation_not_found_match.group(1)
            suggestions.append(
                f"Table '{missing_table}' not found. Check spelling or use correct table name."
            )

        # Handle syntax errors
        if "syntax error" in error_message.lower():
            suggestions.append(
                "Check SQL syntax. Common issues: missing commas, unmatched quotes, incorrect keywords."
            )

        return suggestions