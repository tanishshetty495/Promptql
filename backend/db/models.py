"""
Database models for PromptQL metadata storage.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, JSON
from sqlalchemy.dialects.postgresql import ARRAY, UUID, INET
from sqlalchemy.ext.declarative import declarative_base
from pgvector.sqlalchemy import Vector
import uuid
from datetime import datetime

from backend.db.base import Base


class ConnectionMetadata(Base):
    """Store metadata about user database connections."""
    __tablename__ = "connection_metadata"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(String(36), unique=True, index=True, nullable=False)
    connection_name = Column(String(255), nullable=False)
    encrypted_credentials = Column(Text, nullable=False)  # Encrypted JSON
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used = Column(DateTime, nullable=True)
    use_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class SchemaEmbeddings(Base):
    """Store schema embeddings for vector search."""
    __tablename__ = "schema_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(String(36), index=True, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_metadata = Column(JSON, nullable=False)  # Schema metadata
    embedding = Column(Vector(384), nullable=False)  # all-MiniLM-L6-v2 produces 384-dim vectors
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Create index for vector similarity search
    __table_args__ = (
        # Index for fast vector similarity search
        # Note: Actual index creation would be done via raw SQL or migration
        {},
    )


class QueryHistory(Base):
    """Store history of executed queries for analytics and improvement."""
    __tablename__ = "query_history"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(String(36), index=True, nullable=False)
    question = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=False)
    executed_sql = Column(Text, nullable=True)  # May differ due to corrections
    success = Column(Boolean, nullable=False)
    row_count = Column(Integer, default=0)
    execution_time_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_feedback = Column(Integer, nullable=True)  # 1-5 rating or None