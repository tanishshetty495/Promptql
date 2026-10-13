"""
Schema Extractor & Semantic Indexer service.
Introspects PostgreSQL information_schema, samples distinct values,
ingests business glossary mappings, and creates embeddings.
"""
import asyncio
import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus

import asyncpg
import numpy as np
from sentence_transformers import SentenceTransformer

from backend.core.config import settings
from backend.core.exceptions import SchemaExtractionError
from backend.core.logger import app_logger
from backend.services.connection_service import connection_service
from backend.db.base import AsyncSessionLocal
from backend.db.models import SchemaEmbeddings
from sqlalchemy import delete, text


class SchemaService:
    """Extracts and indexes database schema information."""

    def __init__(self):
        self.embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        self._schema_cache: Dict[str, Dict] = {}
        self._schema_hashes: Dict[str, str] = {}

    async def extract_schema(
        self,
        connection_id: str,
        credentials: dict,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Extract schema information from a PostgreSQL database.

        Args:
            connection_id: Unique identifier for this connection
            credentials: Database connection parameters
            force_refresh: Whether to force refresh even if cached

        Returns:
            Dictionary containing schema information
        """
        # Check if we need to refresh
        if not force_refresh and connection_id in self._schema_cache:
            current_hash = await self._compute_schema_hash(credentials)
            if self._schema_hashes.get(connection_id) == current_hash:
                app_logger.debug(f"Using cached schema for connection {connection_id}")
                return self._schema_cache[connection_id]

        try:
            app_logger.info(f"Extracting schema for connection {connection_id}")

            # Construct connection string using the shared DSN builder
            dsn = connection_service._build_dsn(credentials)

            # Connect to database
            conn = await asyncpg.connect(dsn)

            try:
                # Extract schema information
                schema_data = await self._extract_schema_info(conn)

                # Perform distinct value sampling for low-cardinality columns
                schema_data = await self._sample_distinct_values(conn, schema_data)

                # Compute hash for change detection
                schema_hash = await self._compute_schema_hash(credentials)
                self._schema_hashes[connection_id] = schema_hash

                # Cache the schema
                self._schema_cache[connection_id] = schema_data

                app_logger.info(f"Schema extracted successfully for connection {connection_id}")
                return schema_data

            finally:
                await conn.close()

        except Exception as e:
            app_logger.error(f"Failed to extract schema for connection {connection_id}: {e}")
            raise SchemaExtractionError(f"Schema extraction failed: {str(e)}") from e

    async def _extract_schema_info(self, conn: asyncpg.Connection) -> Dict[str, Any]:
        """
        Extract basic schema information from information_schema.

        Args:
            conn: Active database connection

        Returns:
            Dictionary containing schema information
        """
        # Query to get tables, columns, types, constraints
        query = """
        SELECT
            t.table_schema,
            t.table_name,
            t.table_type,
            c.column_name,
            c.ordinal_position,
            c.is_nullable,
            c.data_type,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            c.column_default,
            pg_catalog.col_description(
                (SELECT c2.oid FROM pg_catalog.pg_class c2
                 JOIN pg_catalog.pg_namespace n ON n.oid = c2.relnamespace
                 WHERE c2.relname = t.table_name AND n.nspname = t.table_schema),
                c.ordinal_position
            ) as column_comment
        FROM information_schema.tables t
        LEFT JOIN information_schema.columns c
            ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE t.table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
          AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_schema, t.table_name, c.ordinal_position
        """

        rows = await conn.fetch(query)

        # Organize by schema and table
        schema_info: Dict[str, Dict[str, Dict]] = {}

        for row in rows:
            schema_name = row['table_schema']
            table_name = row['table_name']

            if schema_name not in schema_info:
                schema_info[schema_name] = {}

            if table_name not in schema_info[schema_name]:
                schema_info[schema_name][table_name] = {
                    'table_schema': schema_name,
                    'table_name': table_name,
                    'table_type': row['table_type'],
                    'columns': [],
                    'primary_key': [],
                    'foreign_keys': [],
                    'indexes': [],
                    'comment': None
                }

            table_info = schema_info[schema_name][table_name]

            # Add column information if present
            if row['column_name']:
                column_info = {
                    'name': row['column_name'],
                    'ordinal_position': row['ordinal_position'],
                    'is_nullable': row['is_nullable'] == 'YES',
                    'data_type': row['data_type'],
                    'character_maximum_length': row['character_maximum_length'],
                    'numeric_precision': row['numeric_precision'],
                    'numeric_scale': row['numeric_scale'],
                    'column_default': row['column_default'],
                    'comment': row['column_comment'],
                    'is_primary_key': False,  # Will be updated later
                    'is_foreign_key': False   # Will be updated later
                }
                table_info['columns'].append(column_info)

        # Get primary key information
        pk_query = """
        SELECT
            tc.table_schema,
            tc.table_name,
            kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
            AND tc.table_name = kcu.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
        """

        pk_rows = await conn.fetch(pk_query)
        for row in pk_rows:
            schema_name = row['table_schema']
            table_name = row['table_name']
            column_name = row['column_name']

            if (schema_name in schema_info and
                table_name in schema_info[schema_name] and
                'columns' in schema_info[schema_name][table_name]):

                for column in schema_info[schema_name][table_name]['columns']:
                    if column['name'] == column_name:
                        column['is_primary_key'] = True
                        if column_name not in schema_info[schema_name][table_name]['primary_key']:
                            schema_info[schema_name][table_name]['primary_key'].append(column_name)
                        break

        # Get foreign key information
        fk_query = """
        SELECT
            tc.table_schema,
            tc.table_name,
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
            AND tc.table_name = kcu.table_name
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
            AND ccu.table_name = tc.table_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
        """

        fk_rows = await conn.fetch(fk_query)
        for row in fk_rows:
            schema_name = row['table_schema']
            table_name = row['table_name']
            column_name = row['column_name']
            foreign_schema = row['foreign_table_schema']
            foreign_table = row['foreign_table_name']
            foreign_column = row['foreign_column_name']

            if (schema_name in schema_info and
                table_name in schema_info[schema_name] and
                'columns' in schema_info[schema_name][table_name]):

                for column in schema_info[schema_name][table_name]['columns']:
                    if column['name'] == column_name:
                        column['is_foreign_key'] = True
                        fk_info = {
                            'column_name': column_name,
                            'foreign_table_schema': foreign_schema,
                            'foreign_table_name': foreign_table,
                            'foreign_column_name': foreign_column
                        }
                        if fk_info not in schema_info[schema_name][table_name]['foreign_keys']:
                            schema_info[schema_name][table_name]['foreign_keys'].append(fk_info)
                        break

        # Get table comments
        comment_query = """
        SELECT
            n.nspname AS table_schema,
            c.relname AS table_name,
            pg_catalog.obj_description(c.oid, 'pg_class') AS table_comment
        FROM pg_catalog.pg_class c
        LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
        """

        comment_rows = await conn.fetch(comment_query)
        for row in comment_rows:
            schema_name = row['table_schema']
            table_name = row['table_name']
            table_comment = row['table_comment']

            if (schema_name in schema_info and
                table_name in schema_info[schema_name]):

                schema_info[schema_name][table_name]['comment'] = table_comment

        # Get index information (basic)
        index_query = """
        SELECT
            n.nspname AS table_schema,
            c.relname AS table_name,
            i.relname AS index_name,
            pg_get_indexdef(i.oid) AS index_definition
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_index x ON x.indrelid = c.oid
        JOIN pg_catalog.pg_class i ON i.oid = x.indexrelid
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
        """

        index_rows = await conn.fetch(index_query)
        for row in index_rows:
            schema_name = row['table_schema']
            table_name = row['table_name']
            index_name = row['index_name']
            index_definition = row['index_definition']

            if (schema_name in schema_info and
                table_name in schema_info[schema_name]):

                index_info = {
                    'name': index_name,
                    'definition': index_definition
                }
                if index_info not in schema_info[schema_name][table_name]['indexes']:
                    schema_info[schema_name][table_name]['indexes'].append(index_info)

        # Detect implicit foreign keys based on naming and value overlap
        schema_info = await self._detect_implicit_foreign_keys(conn, schema_info)

        return schema_info

    async def _detect_implicit_foreign_keys(
        self,
        conn: asyncpg.Connection,
        schema_info: Dict[str, Dict[str, Dict]]
    ) -> Dict[str, Dict[str, Dict]]:
        """
        Detect implicit foreign keys based on column naming and value overlap.
        This looks for columns that are not already marked as FKs but may reference
        another table via column name matching or value overlap.
        """
        # For each table and column
        for schema_name, tables in schema_info.items():
            for table_name, table_info in tables.items():
                for column in table_info['columns']:
                    # Skip if already a primary key or foreign key
                    if column['is_primary_key'] or column['is_foreign_key']:
                        continue
                    # Only consider text-like columns for value comparison
                    if column['data_type'] not in ('varchar', 'text', 'character varying', 'character'):
                        continue
                    # Heuristic 1: column name matches another table name (case-insensitive)
                    candidate_table_name = column['name']
                    # Look for a table with this name in the same schema
                    if candidate_table_name.lower() in (t.lower() for t in tables.keys()):
                        # Found a table with same name as column
                        target_table_name = candidate_table_name  # preserve case? we need exact match
                        # Find exact case match
                        for tn in tables.keys():
                            if tn.lower() == candidate_table_name.lower():
                                target_table_name = tn
                                break
                        else:
                            continue
                        # Get target table info
                        target_table = tables.get(target_table_name)
                        if not target_table:
                            continue
                        # Determine which column in target table to match against
                        # Prefer primary key column, or column named 'id' or 'name'
                        target_pk_cols = target_table.get('primary_key', [])
                        target_col_name = None
                        if target_pk_cols:
                            target_col_name = target_pk_cols[0]
                        else:
                            # Look for column named 'id' or 'name'
                            for col in target_table['columns']:
                                if col['name'] in ('id', 'name'):
                                    target_col_name = col['name']
                                    break
                        if not target_col_name:
                            # fallback to first column
                            target_col_name = target_table['columns'][0]['name'] if target_table['columns'] else None
                        if not target_col_name:
                            continue
                        # Now sample values from both columns to see if there is overlap
                        # Limit sampling to avoid heavy queries
                        try:
                            # Get up to 10 distinct values from source column
                            source_query = f'''
                                SELECT DISTINCT "{column['name']}"
                                FROM "{schema_name}"."{table_name}"
                                WHERE "{column['name']}" IS NOT NULL
                                LIMIT 10
                            '''
                            source_rows = await conn.fetch(source_query)
                            source_vals = {str(r[column['name']]).strip().lower() for r in source_rows if r[column['name']] is not None}
                            # Get up to 10 distinct values from target column
                            target_query = f'''
                                SELECT DISTINCT "{target_col_name}"
                                FROM "{schema_name}"."{target_table_name}"
                                WHERE "{target_col_name}" IS NOT NULL
                                LIMIT 10
                            '''
                            target_rows = await conn.fetch(target_query)
                            target_vals = {str(r[target_col_name]).strip().lower() for r in target_rows if r[target_col_name] is not None}
                            # If there is any overlap, consider it an FK
                            if source_vals & target_vals:
                                # Mark column as foreign key
                                column['is_foreign_key'] = True
                                fk_info = {
                                    'column_name': column['name'],
                                    'foreign_table_schema': schema_name,
                                    'foreign_table_name': target_table_name,
                                    'foreign_column_name': target_col_name
                                }
                                # Avoid duplicates
                                if fk_info not in table_info['foreign_keys']:
                                    table_info['foreign_keys'].append(fk_info)
                                # Also add sampled_values? Not needed.
                        except Exception as e:
                            app_logger.warning(f"Implicit FK detection failed for {schema_name}.{table_name}.{column['name']} -> {target_table_name}.{target_col_name}: {e}")
                            continue
                    # Heuristic 2: column name ends with '_id' and we can guess the table
                    if column['name'].endswith('_id'):
                        # Guess table name by removing '_id' suffix
                        guessed_table = column['name'][:-3]  # remove '_id'
                        # Look for table with this name (maybe plural? we'll try both)
                        for candidate in [guessed_table, guessed_table + 's']:
                            if candidate.lower() in (t.lower() for t in tables.keys()):
                                for tn in tables.keys():
                                    if tn.lower() == candidate.lower():
                                        target_table_name = tn
                                        break
                                else:
                                    continue
                                target_table = tables.get(target_table_name)
                                if not target_table:
                                    continue
                                # Target table likely has primary key column named 'id'
                                target_pk_cols = target_table.get('primary_key', [])
                                target_col_name = None
                                if target_pk_cols:
                                    # Prefer a column named 'id' if exists
                                    for pk in target_pk_cols:
                                        if pk.lower() == 'id':
                                            target_col_name = pk
                                            break
                                    if not target_col_name:
                                        target_col_name = target_pk_cols[0]
                                else:
                                    for col in target_table['columns']:
                                        if col['name'].lower() == 'id':
                                            target_col_name = col['name']
                                            break
                                    if not target_col_name:
                                        target_col_name = target_table['columns'][0]['name'] if target_table['columns'] else None
                                if not target_col_name:
                                    continue
                                try:
                                    source_query = f'''
                                        SELECT DISTINCT "{column['name']}"
                                        FROM "{schema_name}"."{table_name}"
                                        WHERE "{column['name']}" IS NOT NULL
                                        LIMIT 10
                                    '''
                                    source_rows = await conn.fetch(source_query)
                                    source_vals = {str(r[column['name']]).strip() for r in source_rows if r[column['name']] is not None}
                                    target_query = f'''
                                        SELECT DISTINCT "{target_col_name}"
                                        FROM "{schema_name}"."{target_table_name}"
                                        WHERE "{target_col_name}" IS NOT NULL
                                        LIMIT 10
                                    '''
                                    target_rows = await conn.fetch(target_query)
                                    target_vals = {str(r[target_col_name]).strip() for r in target_rows if r[target_col_name] is not None}
                                    if source_vals & target_vals:
                                        column['is_foreign_key'] = True
                                        fk_info = {
                                            'column_name': column['name'],
                                            'foreign_table_schema': schema_name,
                                            'foreign_table_name': target_table_name,
                                            'foreign_column_name': target_col_name
                                        }
                                        if fk_info not in table_info['foreign_keys']:
                                            table_info['foreign_keys'].append(fk_info)
                                except Exception as e:
                                    app_logger.warning(f"Implicit FK detection (_id) failed for {schema_name}.{table_name}.{column['name']} -> {target_table_name}.{target_col_name}: {e}")
                                    continue
                                break  # only need to find one match
        return schema_info

    async def _sample_distinct_values(
        self,
        conn: asyncpg.Connection,
        schema_info: Dict[str, Dict[str, Dict]]
    ) -> Dict[str, Dict[str, Dict]]:
        """
        Sample distinct values for low-cardinality columns.

        Args:
            conn: Active database connection
            schema_info: Schema information to enhance

        Returns:
            Enhanced schema information with sampled values
        """
        # Identify columns suitable for sampling (low cardinality candidates)
        sample_candidates: List[Tuple[str, str, str]] = []  # (schema, table, column)

        for schema_name, tables in schema_info.items():
            for table_name, table_info in tables.items():
                for column in table_info['columns']:
                    # Sample columns that are:
                    # 1. Not primary keys (usually high cardinality)
                    # 2. Not foreign keys (usually references, high cardinality)
                    # 3. Of suitable types (varchar, text, enum-like)
                    # 4. Have reasonable length limits
                    if (not column['is_primary_key'] and
                        not column['is_foreign_key'] and
                        column['data_type'] in ('varchar', 'text', 'character varying', 'character') and
                        column['character_maximum_length'] and
                        column['character_maximum_length'] <= 50):  # Reasonable limit for sampling

                        sample_candidates.append((schema_name, table_name, column['name']))

        # Sample distinct values for candidates (limit to avoid excessive queries)
        max_samples = 20  # Limit number of columns to sample
        for i, (schema_name, table_name, column_name) in enumerate(sample_candidates[:max_samples]):
            try:
                # Get distinct values (limit to avoid huge result sets)
                query = f'''
                    SELECT DISTINCT "{column_name}"
                    FROM "{schema_name}"."{table_name}"
                    WHERE "{column_name}" IS NOT NULL
                    LIMIT 10
                '''

                rows = await conn.fetch(query)
                distinct_values = [str(row[column_name]) for row in rows]

                # Store sampled values in column info
                for table_info in tables.values():
                    for column in table_info['columns']:
                        if column['name'] == column_name:
                            column['sampled_values'] = distinct_values
                            column['is_sampled'] = True
                            break

            except Exception as e:
                app_logger.warning(f"Failed to sample values for {schema_name}.{table_name}.{column_name}: {e}")
                # Continue with other columns

        return schema_info

    async def _compute_schema_hash(self, credentials: dict) -> str:
        """
        Compute a hash of the schema for change detection.

        Args:
            credentials: Database connection parameters

        Returns:
            Hash string representing current schema state
        """
        try:
            # Construct connection string using the shared DSN builder
            dsn = connection_service._build_dsn(credentials)

            # Connect to database
            conn = await asyncpg.connect(dsn)

            try:
                # Get a simplified representation of the schema for hashing
                query = """
                SELECT
                    table_schema,
                    table_name,
                    column_name,
                    data_type,
                    is_nullable,
                    character_maximum_length
                FROM information_schema.columns
                WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ORDER BY table_schema, table_name, ordinal_position
                """

                rows = await conn.fetch(query)

                # Create a string representation for hashing
                schema_string = ""
                for row in rows:
                    schema_string += f"{row['table_schema']}.{row['table_name']}.{row['column_name']}:" \
                                   f"{row['data_type']}.{row['is_nullable']}.{row['character_maximum_length'] or ''}|"

                # Hash the string
                return hashlib.sha256(schema_string.encode('utf-8')).hexdigest()

            finally:
                await conn.close()

        except Exception as e:
            app_logger.error(f"Failed to compute schema hash: {e}")
            # Return a hash that will trigger refresh on next attempt
            return hashlib.sha256(b"error").hexdigest()

    async def get_schema_text_chunks(
        self,
        schema_info: Dict[str, Dict[str, Dict]],
        include_samples: bool = True,
        include_comments: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Convert schema information into text chunks for embedding.

        Args:
            schema_info: Schema information from extract_schema
            include_samples: Whether to include sampled values in chunks
            include_comments: Whether to include comments in chunks

        Returns:
            List of text chunks with metadata for embedding
        """
        chunks = []

        for schema_name, tables in schema_info.items():
            for table_name, table_info in tables.items():
                # Create a text representation of the table
                text_parts = [
                    f"Table: {schema_name}.{table_name}",
                    f"Type: {table_info['table_type']}"
                ]

                if include_comments and table_info.get('comment'):
                    text_parts.append(f"Comment: {table_info['comment']}")

                # Add column information
                column_parts = []
                for column in table_info['columns']:
                    col_desc = f"{column['name']}: {column['data_type']}"
                    if not column['is_nullable']:
                        col_desc += " NOT NULL"
                    if column['is_primary_key']:
                        col_desc += " PRIMARY KEY"
                    if column['is_foreign_key']:
                        fk_info = next(
                            (fk for fk in table_info['foreign_keys']
                             if fk['column_name'] == column['name']),
                            None
                        )
                        if fk_info:
                            col_desc += f" (FK -> {fk_info['foreign_table_schema']}.{fk_info['foreign_table_name']}({fk_info['foreign_column_name']}))"
                    if include_comments and column.get('comment'):
                        col_desc += f" Comment: {column['comment']}"
                    if include_samples and column.get('sampled_values'):
                        samples = ', '.join(column['sampled_values'][:5])  # Limit samples
                        col_desc += f" Sampled values: [{samples}]"
                    column_parts.append(col_desc)

                if column_parts:
                    text_parts.append("Columns: " + "; ".join(column_parts))

                # Add primary key info
                if table_info['primary_key']:
                    text_parts.append(f"Primary Key: {', '.join(table_info['primary_key'])}")

                # Remove separate foreign key info section since it's now included inline in column descriptions
                pass

                # Add index info
                if table_info['indexes']:
                    index_desc = []
                    for idx in table_info['indexes'][:3]:  # Limit to avoid too long
                        index_desc.append(f"{idx['name']}: {idx['definition']}")
                    if len(table_info['indexes']) > 3:
                        index_desc.append(f"... and {len(table_info['indexes']) - 3} more indexes")
                    text_parts.append("Indexes: " + "; ".join(index_desc))

                # Combine all parts
                chunk_text = "\n".join(text_parts)

                # Create chunk metadata
                chunk = {
                    'text': chunk_text,
                    'metadata': {
                        'connection_id': None,  # Will be set by caller
                        'schema_name': schema_name,
                        'table_name': table_name,
                        'table_type': table_info['table_type'],
                        'column_count': len(table_info['columns']),
                        'has_comment': bool(table_info.get('comment')),
                        'sampled_columns': [
                            col['name'] for col in table_info['columns']
                            if col.get('is_sampled', False)
                        ]
                    }
                }

                chunks.append(chunk)

        return chunks

    async def store_schema_embeddings(
        self,
        connection_id: str,
        schema_chunks: List[Dict[str, Any]]
    ) -> None:
        """
        Store schema embeddings in the application database.

        Args:
            connection_id: Unique identifier for this connection
            schema_chunks: Schema text chunks to embed and store
        """
        try:
            # Generate embeddings for all chunks
            texts = [chunk['text'] for chunk in schema_chunks]
            embeddings = self.embedding_model.encode(texts)

            # Store in application database using SQLAlchemy session
            async with AsyncSessionLocal() as session:
                # Delete existing embeddings for this connection
                await session.execute(
                    delete(SchemaEmbeddings).where(SchemaEmbeddings.connection_id == connection_id)
                )
                # Prepare new embedding objects
                embeddings_objs = []
                for i, (chunk, embedding) in enumerate(zip(schema_chunks, embeddings)):
                    obj = SchemaEmbeddings(
                        connection_id=connection_id,
                        chunk_index=i,
                        chunk_text=chunk['text'],
                        chunk_metadata=chunk['metadata'],
                        embedding=embedding.tolist()  # Store as list for pgvector
                    )
                    embeddings_objs.append(obj)
                session.add_all(embeddings_objs)
                await session.commit()

            app_logger.info(f"Stored {len(schema_chunks)} schema embeddings for connection {connection_id}")

        except Exception as e:
            app_logger.error(f"Failed to store schema embeddings: {e}")
            raise SchemaExtractionError("Failed to store schema embeddings") from e

    async def retrieve_relevant_schema(
        self,
        connection_id: str,
        query_text: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant schema chunks using hybrid search (vector + keyword).

        Args:
            connection_id: Unique identifier for this connection
            query_text: Natural language query to search for
            limit: Maximum number of results to return

        Returns:
            List of relevant schema chunks
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query_text])[0]
            embedding_str = '[' + ','.join(map(str, query_embedding.tolist())) + ']'

            # Search in application database using SQLAlchemy session
            async with AsyncSessionLocal() as session:
                # Get initial results - we'll get extra to allow for FK expansion
                initial_limit = limit * 2  # Get more than we need initially
                results = await session.execute(
                    text("""
                        SELECT
                            chunk_text,
                            chunk_metadata,
                            1 - (embedding <=> :query_embedding) AS similarity_score
                        FROM schema_embeddings
                        WHERE connection_id = :connection_id
                        ORDER BY embedding <=> :query_embedding
                        LIMIT :initial_limit
                    """),
                    {
                        "query_embedding": embedding_str,
                        "connection_id": connection_id,
                        "initial_limit": initial_limit
                    }
                )

                # Convert results
                chunks = []
                for row in results:
                    # chunk_metadata might be a string (JSON) or already a dict
                    metadata = row.chunk_metadata
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    chunk = {
                        'text': row.chunk_text,
                        'metadata': metadata,
                        'similarity_score': float(row.similarity_score)
                    }
                    chunks.append(chunk)

                # Apply FK expansion: for each retrieved table, include FK-related tables
                # up to a reasonable cap (e.g., 3 additional tables)
                if chunks and hasattr(settings, 'MAX_FK_EXPANSIONS'):
                    max_expansions = settings.MAX_FK_EXPANSIONS
                else:
                    max_expansions = 3  # Default cap

                # Extract table information from chunks
                # Each chunk represents one table (based on get_schema_text_chunks)
                table_to_chunk = {}  # Map (schema_name, table_name) -> chunk
                retrieved_tables = set()  # Set of (schema_name, table_name) for initial chunks

                for chunk in chunks:
                    metadata = chunk['metadata']
                    schema_name = metadata.get('schema_name')
                    table_name = metadata.get('table_name')
                    if schema_name and table_name:
                        table_key = (schema_name, table_name)
                        table_to_chunk[table_key] = chunk
                        retrieved_tables.add(table_key)

                # If we have no chunks or no expansions wanted, return initial chunks
                if not retrieved_tables or max_expansions <= 0:
                    # Sort by similarity and return top limit
                    chunks.sort(key=lambda x: x['similarity_score'], reverse=True)
                    return chunks[:limit]

                # Collect FK-related tables from retrieved tables
                fk_candidates = []  # List of (table_key, source_chunk_similarity) for FK-related tables

                # Get full schema cache for this connection
                schema_cache = self._schema_cache.get(connection_id, {})

                # For each retrieved table, find its FK relationships
                processed_tables = set()
                for table_key in retrieved_tables:
                    if table_key in processed_tables:
                        continue
                    processed_tables.add(table_key)

                    schema_name, table_name = table_key
                    # Get table info from schema cache
                    if (schema_name in schema_cache and
                        table_name in schema_cache[schema_name]):
                        table_info = schema_cache[schema_name][table_name]
                        foreign_keys = table_info.get('foreign_keys', [])

                        for fk in foreign_keys:
                            foreign_schema = fk.get('foreign_table_schema')
                            foreign_table = fk.get('foreign_table_name')
                            foreign_column = fk.get('foreign_column_name')

                            if foreign_schema and foreign_table:
                                foreign_key = (foreign_schema, foreign_table)
                                # Only consider if not already in retrieved tables
                                if foreign_key not in retrieved_tables:
                                    # We'll use the similarity of the source table as a proxy
                                    # for ordering FK candidates (though ideally we'd want their own similarity)
                                    source_similarity = table_to_chunk[table_key]['similarity_score']
                                    fk_candidates.append((foreign_key, source_similarity))

                # Sort FK candidates by similarity score (descending) and take top max_expansions
                fk_candidates.sort(key=lambda x: x[1], reverse=True)
                selected_fk_tabs = set()
                for fk_candidate in fk_candidates[:max_expansions]:
                    selected_fk_tabs.add(fk_candidate[0])

                # Now we need to get chunks for the selected FK-related tables
                # We'll query for all of them at once for efficiency
                if selected_fk_tabs:
                    # Build OR conditions for the tables we need
                    or_conditions = []
                    params = {"connection_id": connection_id, "query_embedding": embedding_str}

                    for i, (schema_name, table_name) in enumerate(selected_fk_tabs):
                        or_conditions.append(
                            f"(chunk_metadata->>'schema_name' = :schema_name_{i} "
                            f"AND chunk_metadata->>'table_name' = :table_name_{i})"
                        )
                        params[f"schema_name_{i}"] = schema_name
                        params[f"table_name_{i}"] = table_name

                    if or_conditions:
                        fk_sql = f"""
                            SELECT
                                chunk_text,
                                chunk_metadata,
                                1 - (embedding <=> :query_embedding) AS similarity_score
                            FROM schema_embeddings
                            WHERE connection_id = :connection_id
                                AND ({' OR '.join(or_conditions)})
                            ORDER BY embedding <=> :query_embedding
                        """

                        fk_results = await session.execute(text(fk_sql), params)

                        fk_chunks = []
                        for row in fk_results:
                            metadata = row.chunk_metadata
                            if isinstance(metadata, str):
                                metadata = json.loads(metadata)
                            fk_chunk = {
                                'text': row.chunk_text,
                                'metadata': metadata,
                                'similarity_score': float(row.similarity_score)
                            }
                            fk_chunks.append(fk_chunk)

                        # Combine initial chunks and FK chunks
                        all_chunks = chunks + fk_chunks
                    else:
                        all_chunks = chunks
                else:
                    all_chunks = chunks

                # Sort all chunks by similarity score and return top limit
                all_chunks.sort(key=lambda x: x['similarity_score'], reverse=True)
                return all_chunks[:limit]

        except Exception as e:
            app_logger.error(f"Failed to retrieve schema: {e}")
            raise SchemaExtractionError("Failed to retrieve schema") from e