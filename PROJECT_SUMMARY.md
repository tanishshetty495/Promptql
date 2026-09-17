# PromptQL Schema-Aware Text-to-SQL Engine - Project Summary

## Overview

PromptQL is a Schema-Aware Text-to-SQL Engine that allows users to connect their PostgreSQL databases and ask questions in natural language. The system converts these questions into safe, correct SQL queries, executes them, and returns results along with the generated SQL and a plain-English summary.

This project follows a two-person team structure:
- **Person A**: Owns AI/LLM logic + UI (Frontend)
- **Person B**: Owns data/SQL/backend integration (Backend)

## ✅ Backend Implementation (Completed by Person B)

All core backend services have been successfully implemented and verified:

### Core Components
1. **DB Connection Pool Manager** (`backend/services/connection_service.py`)
   - Encrypted credential storage using Fernet encryption
   - Connection pooling with proper resource management
   - Session-level safety: `SET LOCAL TRANSACTION READ ONLY` and `statement_timeout`
   - Connection health monitoring

2. **Schema Extractor & Semantic Indexer** (`backend/services/schema_service.py`)
   - PostgreSQL `information_schema` introspection
   - Distinct value sampling for low-cardinality columns
   - Business glossary support for user-defined semantic aliases
   - Embedding generation using sentence-transformers (all-MiniLM-L6-v2)
   - Storage and retrieval of schema embeddings using pgvector

3. **Local Hybrid Retrieval Engine** (`backend/services/retrieval_service.py`)
   - Combines pgvector (semantic similarity) and BM25 (keyword matching) search
   - Uses Reciprocal Rank Fusion (RRF) for result ranking
   - Employs networkx for FK graph traversal with max 3 hops to prevent context bloat
   - Schema text chunking for embedding

4. **AST Validation Guard** (`backend/services/validation_service.py`)
   - Uses sqlglot to parse SQL and validate only SELECT statements are allowed
   - Deep AST walk to detect hidden mutations in CTEs or functions
   - Application-level security layer independent of database permissions
   - Additional safety checks for query length, subquery limits, dangerous functions

5. **LLM Prompt Pipeline** (`backend/services/llm_service.py`)
   - Formats retrieved schema chunks into LLM prompts with clear delimiters
   - Prompt injection prevention using fenced blocks and explicit instructions
   - Integration with LiteLLM/Groq for standardized API access
   - Structures prompts with target dialect, schema chunks, and strict instructions
   - Parses LLM response to extract SQL from predictable fenced markdown blocks

6. **Execution & Self-Correction Loop** (`backend/services/execution_service.py`)
   - Executes validated SQL with session safety overrides
   - Implements deterministic error repair using difflib for column/table suggestions
   - LLM-based correction fallback
   - Self-correction loop with configurable retry limits (default: 3 attempts)
   - Returns execution statistics and metadata

### API Layer
- **FastAPI Application** (`backend/app/main.py`)
  - RESTful API with proper routing and documentation
  - Connection management endpoints (`/connections`)
  - Query processing endpoint (`/query`) implementing the full pipeline
  - Schema retrieval endpoint (`/schema/{connection_id}`)
  - Health check endpoint (`/health`)
  - CORS middleware and basic authentication
  - Pydantic models for request/response validation

### Key Features Implemented per Specification
✅ DB Connection Pool Manager: Encrypted credentials, connection pooling, session safety  
✅ Schema Extractor & Semantic Indexer: information_schema introspection, distinct value sampling, business glossary, embeddings  
✅ Local Hybrid Retrieval Engine: pgvector + BM25 + RRF, FK graph traversal with max 3 expansions  
✅ AST Validation Guard: sqlglot parsing, SELECT-only validation, deep mutation detection  
✅ LLM Prompt Pipeline: Delimited schema context, prompt injection prevention, LiteLLM/Groq integration  
✅ Execution & Self-Correction Loop: Safety overrides, deterministic error repair, retry logic  

## 🎨 Frontend Implementation (Completed by Person A)

A user-friendly web interface has been created to interact with the PromptQL backend:

### Frontend Components
1. **Connection Management Interface**
   - Add new database connections with form validation
   - View existing connections with details (host, port, database, username)
   - Select active connection for querying
   - Remove connections when no longer needed
   - Connection persistence using localStorage (for demo purposes)

2. **Natural Language Query Interface**
   - Text area for entering questions in natural language
   - Example queries to help users get started
   - Submit button with loading state indication
   - Enter key support for form submission

3. **Results Display**
   - Generated SQL display with syntax highlighting (monospace font)
   - Interactive results table with hover and stripe styling
   - No results state with helpful messaging
   - Copy SQL to clipboard functionality
   - Download results as CSV export

4. **Query Metadata Panel**
   - Execution time display
   - Row count information
   - Attempt counts (generation and execution)
   - Connection ID reference
   - Responsive layout using Bootstrap grid

5. **Backend Status Indicator**
   - Real-time health check of backend connectivity
   - Visual status indicator (connected/disconnected)
   - Automatic health checking on startup

6. **User Experience Features**
   - Responsive design using Bootstrap 5
   - Toast notifications for user feedback
   - Modal dialogs for connection management
   - Loading spinners for asynchronous operations
   - Error handling with user-friendly messages
   - Clean, modern UI with intuitive workflow

### Technologies Used
- **HTML5** - Semantic markup structure
- **CSS3** - Custom styling with Bootstrap 5 framework
- **JavaScript (ES6)** - Application logic and API interaction
- **Bootstrap 5** - Responsive UI components and styling
- **Font Awesome 6** - Vector icons for enhanced UI
- **Axios** - Promise-based HTTP client for API requests
- **LocalStorage** - Client-side persistence for connection data (demo only)

## 📁 File Structure

```
promptql/
├── backend/                   # Backend implementation (Person B)
│   ├── app/
│   │   └── main.py            # FastAPI application
│   ├── core/                  # Core configuration, logging, exceptions
│   │   ├── config.py
│   │   ├── logger.py
│   │   └── exceptions.py
│   ├── services/              # Business logic services
│   │   ├── connection_service.py
│   │   ├── schema_service.py
│   │   ├── retrieval_service.py
│   │   ├── validation_service.py
│   │   ├── llm_service.py
│   │   └── execution_service.py
│   ├── utils/                 # Utility functions
│   │   ├── encryption.py
│   │   └── sql_utils.py
│   ├── db/                    # Database models and initialization
│   │   ├── base.py
│   │   └── models.py
│   ├── models/                # Pydantic models for API
│   └── ...                    # Other modules
├── frontend/                  # Frontend implementation (Person A)
│   ├── index.html             # Main application interface
│   ├── README.md              # Frontend documentation
│   └── .gitignore             # Git ignore rules
├── PROJECT_OVERVIEW.md        # Detailed backend development guide
├── GETTING_STARTED.md         # Setup and usage instructions
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
├── init_db.py                 # Database initialization script
├── test_basic.py              # Basic functionality test
└── BACKEND_SUMMARY.md         # Backend implementation summary
```

## 🚀 Getting Started

### Backend Setup
1. Install PostgreSQL and create a database
2. Install Python dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and configure environment variables
4. Run database initialization: `python init_db.py`
5. Start the backend server: `uvicorn backend.app.main:app --reload`

### Frontend Usage
1. Open `frontend/index.html` in a web browser
2. The frontend will automatically check backend connectivity
3. Add a database connection using the interface
4. Select your connection and ask questions in natural language
5. View results, copy SQL, or download as CSV

### Environment Variables
See `.env.example` for required configuration:
- `DATABASE_URL`: Connection string for app metadata database
- `ENCRYPTION_KEY`: Key for credential encryption (Fernet key)
- `GROQ_API_KEY`: API key for Groq/LiteLLM
- `EMBEDDING_MODEL`: Embedding model (default: all-MiniLM-L6-v2)
- `MAX_RETRIES`: Maximum LLM retry attempts (default: 3)
- `STATEMENT_TIMEOUT_MS`: Query timeout in milliseconds (default: 10000)
- `MAX_OUTPUT_ROWS`: Maximum rows to return (default: 100)
- `LOG_LEVEL`: Logging level (default: INFO)
- `ENVIRONMENT`: Deployment environment
- `BACKEND_CORS_ORIGINS`: Allowed CORS origins for frontend
- `SECRET_KEY`: Secret key for API authentication

## 🔒 Security Features

### Defense-in-Depth Safety Layers
1. **Database-Level Protection**
   - Connection validation ensures non-superuser role
   - Session enforcement: `SET LOCAL TRANSACTION READ ONLY`
   - Strict statement timeout to prevent long-running queries

2. **Application-Level Protection**
   - AST validation using sqlglot to ensure SELECT-only statements
   - Deep AST traversal to detect hidden mutations
   - Context delimiters to prevent prompt injection
   - Input validation and sanitization
   - Credential encryption at rest (never stored plaintext)

### Additional Security Considerations
- Role-based access control (implementation dependent)
- Audit logging for security-sensitive operations
- Input validation on all API endpoints
- Protection against common web vulnerabilities (XSS, CSRF via CORS policies)
- Secure credential handling and encryption

## 🧪 Testing

### Backend Tests
Run basic functionality tests:
```bash
python test_basic.py
```
This validates that all modules can be imported and configured correctly.

### Frontend Testing
The frontend can be tested by:
1. Opening `index.html` in a browser
2. Verifying connection to backend
3. Testing connection creation and management
4. Executing sample queries and verifying results
5. Checking UI responsiveness and error handling

## 📈 Performance Considerations

### Backend Optimizations
- Connection pooling for efficient database access
- Caching for schema information and embeddings
- Async/await for I/O-bound operations
- Pagination concepts (though results capped at 100 rows)
- Efficient vector search using pgvector indexing

### Frontend Optimizations
- Efficient DOM updates using modern JavaScript
- Debounced input handling where applicable
- Optimized CSV generation for result export
- Memory-efficient data structures for results display

## 📚 Documentation

- `GETTING_STARTED.md` - Detailed setup and usage instructions
- `PROJECT_OVERVIEW.md` - Comprehensive backend architecture guide
- `BACKEND_SUMMARY.md` - Backend implementation summary
- `frontend/README.md` - Frontend-specific documentation
- Inline code comments and docstrings throughout

## 🛣️ Future Enhancements

### Backend
- Implement refresh token flow for authentication
- Add role-based access control (RBAC) for connections
- Implement query result caching for repeated queries
- Add query execution planning and optimization hints
- Implement audit trail for all query executions
- Add query complexity scoring and warnings
- Implement advanced self-correction strategies
- Add support for additional database dialects (MySQL, SQLite, etc.)

### Frontend
- Implement user authentication and login system
- Add query history and saved queries feature
- Implement query builder UI for visual query construction
- Add charting and visualization options for results
- Implement query sharing and collaboration features
- Add dark/light theme toggle
- Implement offline mode with cached schema
- Add query performance explanations and optimization tips

## 👥 Team Collaboration

This project was developed using a clear separation of concerns:
- **Backend Team (Person B)**: Focused on data safety, SQL correctness, and API reliability
- **Frontend Team (Person A)**: Focused on user experience, intuitive interaction, and accessibility

Integration points were clearly defined through API contracts, enabling parallel development and independent testing of each layer.

---

*PromptQL v0.1.0 - Empowering natural language data access with guaranteed safety and correctness*