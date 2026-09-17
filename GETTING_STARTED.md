# Getting Started with PromptQL Backend

This guide will help you get the PromptQL backend up and running.

## Prerequisites

- Python 3.9+
- PostgreSQL database (for app metadata)
- Groq API key (for LLM functionality)
- Git

## Installation

1. Clone the repository
   ```bash
   git clone <repository-url>
   cd promptql
   ```

2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

   Required environment variables:
   - `DATABASE_URL`: PostgreSQL connection string for app metadata (e.g., `postgresql+asyncpg://user:password@localhost:5432/promptql_meta`)
   - `ENCRYPTION_KEY`: 32-byte key for credential encryption (generate with `openssl rand -hex 32`)
   - `GROQ_API_KEY`: Your Groq API key
   - `SECRET_KEY`: Secret key for application security (generate with `openssl rand -hex 32`)

4. Initialize the database
   ```bash
   python init_db.py
   ```

## Running Tests

Run the basic functionality tests:
```bash
python test_basic.py
```

This will verify that all modules can be imported and configured correctly.

## Running the Application

Start the backend server:
```bash
python -m backend.app.main
```

Or with uvicorn directly:
```bash
uvicorn backend.app.main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project Structure

```
backend/
├── app/                    # FastAPI application
│   └── main.py             # Application entry point
├── core/                   # Core configuration, logging, exceptions
├── services/               # Business logic services
│   ├── connection_service.py   # DB connection management
│   ├── schema_service.py       # Schema extraction and indexing
│   ├── retrieval_service.py    # Hybrid search and FK traversal
│   ├── validation_service.py   # SQL validation with sqlglot
│   ├── llm_service.py          # LLM integration for SQL generation
│   └── execution_service.py    # Query execution and self-correction
├── utils/                  # Utility functions
├── models/                 # Pydantic models for API
├── db/                     # Database models and initialization
└── ...                     # Other modules
```

## Key Features Implemented

Based on the PromptQL specification, the backend includes:

1. **DB Connection Pool Manager**
   - Encrypted credential storage
   - Connection pooling with asyncpg
   - Session-level safety: `SET LOCAL TRANSACTION READ ONLY` and `statement_timeout`

2. **Schema Extractor & Semantic Indexer**
   - PostgreSQL information_schema introspection
   - Distinct value sampling for low-cardinality columns
   - Business glossary support
   - Embedding generation with sentence-transformers
   - Storage in pgvector for vector search

3. **Local Hybrid Retrieval Engine**
   - Combines pgvector (semantic) and BM25 (keyword) search
   - Uses Reciprocal Rank Fusion (RRF) for ranking
   - Performs FK graph traversal using networkx
   - Limits FK expansions to max 3 tables

4. **AST Validation Guard**
   - Uses sqlglot to parse and validate SQL
   - Ensures only SELECT statements are allowed
   - Deep AST walk to detect hidden mutations
   - Application-level safety layer

5. **LLM Prompt Pipeline**
   - Formats schema chunks with clear delimiters to prevent prompt injection
   - Integrates with LiteLLM/Groq for SQL generation
   - Structured prompt engineering for reliable SQL output

6. **Execution & Self-Correction Loop**
   - Executes validated SQL with safety overrides
   - Implements deterministic error repair (e.g., difflibflib for column suggestions)
   - Retries failed queries up to 3 times
   - Returns results with confidence scores

## Next Steps

After verifying the backend works with the basic tests, you can:

1. Connect to your PostgreSQL database using the `/connections` endpoint
2. Extract and index the schema
3. Ask natural language questions using the `/query` endpoint
4. Review the generated SQL, results, and execution metrics

For production deployment, consider:
- Setting up proper secret management
- Using a managed PostgreSQL service
- Adding rate limiting and authentication
- Implementing comprehensive monitoring and logging
- Adding containerization with Docker