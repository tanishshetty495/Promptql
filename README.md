<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/postgresql-%23316192.svg?logo=postgresql&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg">
  <img alt="Contributors" src="https://img.shields.io/badge/contributors-welcome-brightgreen.svg">
</p>

# PromptQL - Schema-Aware Text-to-SQL Engine 🚀

>A web application that lets users connect their cloud-hosted PostgreSQL databases and ask questions in natural language. The system converts questions into safe, correct SQL queries, executes them, and returns results with the SQL and plain-English summary.

## 🏗️ System Architecture

<p align="center">
  <img src="assets/architecture.gif" alt="PromptQL Architecture" width="80%">
</p>

### 🔧 Core Components

PromptQL follows a modular microservices-inspired architecture with clearly separated concerns:

- **Frontend Interface** (`/frontend`): 
  - React-like vanilla JS UI with Bootstrap 5
  - Query input with syntax highlighting
  - Results display with table/chart tabs
  - Connection management panel
  - Query history and saved queries sidebar
  - Theme toggle (dark/light) with localStorage persistence

- **Backend API** (`/backend/app/main.py`): 
  - FastAPI server providing RESTful endpoints
  - JWT-style token authentication (Bearer token matching SECRET_KEY)
  - CORS-enabled for frontend integration
  - Health check and query processing endpoints

- **LLM Service** (`/backend/services/llm_service.py`): 
  - Natural language to SQL translation
  - SQL explanation generation
  - Result summarization (for small result sets)
  - Currently configured for Groq models (mixtral-8x7b-32768 default)
  - Extensible to support other LLM providers

- **Schema Service** (`/backend/services/schema_service.py`): 
  - Database schema introspection and extraction
  - Schema caching for performance
  - Text chunking of schema for semantic search
  - Embedding generation using sentence-transformers

- **Retrieval Service** (`/backend/services/retrieval_service.py`): 
  - Semantic search over schema chunks
  - Golden query caching (successful query→SQL pairs)
  - Similarity-based query routing
  - Few-shot example retrieval for LLM prompting

- **Validation Service** (`/backend/services/validation_service.py`): 
  - SQL safety validation
  - Syntax checking
  - Injection prevention
  - Resource limit validation (statement timeout, row limits)

- **Execution Service** (`/backend/services/execution_service.py`): 
  - Safe SQL execution with connection pooling
  - Result fetching and formatting
  - Execution metadata collection
  - Error handling and reporting

- **Database Layer** (`/backend/db`): 
  - SQLAlchemy ORM with async support
  - Connection metadata storage (encrypted credentials)
  - Migration support for schema evolution

### 🔄 Data Flow Pipeline

1. **Input Reception**: User enters natural language query via frontend
2. **Authentication**: Frontend sends query + Bearer token to backend `/query` endpoint
3. **Connection Lookup**: Backend retrieves connection credentials from database
4. **Schema Retrieval**: 
   - Check schema cache
   - If missing, extract and cache schema from database
   - Generate text chunks for semantic search
5. **Context Enhancement**: 
   - Retrieve relevant schema chunks via semantic search
   - Fetch golden queries for few-shot prompting
6. **LLM Processing**: 
   - Construct prompt with schema context, examples, and user question
   - Call LLM to generate SQL query and optional chart specification
   - Apply complexity routing (simple/complex question handling)
7. **Validation & Correction**: 
   - Validate generated SQL for safety and correctness
   - If invalid, provide error context to LLM for retry (max 3 attempts)
   - Cache successful first-attempt queries as golden queries
8. **Execution & Response**: 
   - Execute validated SQL against database
   - Format results and collect execution metadata
   - Generate summary and explanation (if enabled)
   - Return structured response to frontend
9. **Frontend Rendering**: 
   - Display generated SQL with syntax highlighting
   - Show results in table or chart format
   - Present plain-English explanation
   - Display execution metadata
   - Add query to history
   - Trigger success celebrations (confetti, timing-based fun facts)

## 🛠️ Supported Technologies

### 💾 Databases
- **Primary**: PostgreSQL (tested with versions 12+)
- **Connection**: Asynchronous asyncpg driver
- **Authentication**: Username/password with SSL support
- **Future**: Designed for extensibility to other SQL databases

### 🤖 Language Models
- **Default**: Groq mixtral-8x7b-32768 (fast, efficient, open weights)
- **Compatibility**: Any OpenAI-compatible API endpoint
- **Configuration**: Via environment variables:
  - `GROQ_API_KEY`: API key for Groq service
  - `LLM_MODEL`: Model identifier (e.g., `groq/mistral-saba-24b`)
  - `LLM_MAX_RETRIES`: Retry attempts for failed requests
  - `LLM_TIMEOUT`: Request timeout in seconds

### ⚡ Performance Optimizations
- **Schema Caching**: Extracted schema cached in-memory per connection
- **Golden Query Caching**: Successful (question→SQL) pairs cached for reuse
- **Similarity Threshold**: 0.98 similarity for cache hits (configurable)
- **Async Operations**: Non-blocking I/O for database and network operations
- **Connection Pooling**: Efficient reuse of database connections

### 🖥️ Frontend Stack
- **Core**: Vanilla JavaScript with ES6+ features
- **UI**: Bootstrap 5 for responsive, mobile-first design
- **Icons**: Font Awesome 6 for scalable vector icons
- **Charts**: Chart.js with optional Vega-Lite/Vega support
- **Animations**: Canvas-confetti for celebrations, CSS transitions for UI
- **State Management**: LocalStorage for persistence (history, themes, saved queries)
- **HTTP Client**: Axios with automatic interceptors for auth headers

## 🔐 Security Features

### 🛡️ Data Protection
- **Credential Encryption**: Database passwords encrypted using Fernet (AES-128)
- **Key Management**: Encryption key stored in environment variable (`ENCRYPTION_KEY`)
- **Session Security**: Server-side session signing with `SECRET_KEY`
- **Environment Isolation**: `.env` file protected by `.gitignore` (never committed)
- **Minimal Data Storage**: Only connection metadata stored (no query logs by default)

### 🔒 Access Control
- **Token Authentication**: Bearer token required for all API endpoints
- **Token Validation**: Exact match against backend `SECRET_KEY`
- **Header-Based**: `Authorization: Bearer <token>` for HTTP clients
- **No Session Storage**: Stateless API reduces attack surface
- **CORS Configuration**: Restrictable origins via `BACKEND_CORS_ORIGINS`

### 🧪 Query Safety
- **SQL Validation**: Multi-layer validation before execution
- **Allow-List Approach**: Only permits safe SQL operations (SELECT by default)
- **Injection Prevention**: Parameterized queries where applicable
- **Resource Limits**: 
  - `STATEMENT_TIMEOUT_MS`: Query execution timeout (default 10s)
  - `MAX_OUTPUT_ROWS`: Limit result set size (default 100 rows)
  - `SESSION_READ_ONLY`: Enforce read-only transactions (default true)
- **Error Handling**: Structured error responses without leaking system details

### 🌐 Network Security
- **HTTPS Ready**: Works behind TLS-terminating proxies/load balancers
- **No Hardcoded Secrets**: All sensitive values via environment variables
- **Audit Ready**: Structured JSON logging for security events
- **Dependency Management**: Regular updates via `requirements.txt`

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- PostgreSQL database (version 12+ recommended)
- Git (for cloning the repository)
- API key for Groq service (optional for limited functionality)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/promptql.git
   cd promptql
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   # NEVER commit your .env file - it's protected by .gitignore
   ```

4. Initialize the database:
   ```bash
   python -m backend.db.init_db
   ```

5. Run the application:
   ```bash
   uvicorn backend.app.main:app --reload
   ```

### 💡 Usage Tips

- Use the **Save Query** feature (⭐ icon) to save frequently used queries with custom names
- Access your saved queries from the connection panel
- Use the query history panel to revisit and re-run previous queries
- Toggle between light and dark themes using the theme switch in the header
- Export results in CSV, JSON, or Excel formats using the export dropdown
- Try the example questions to see PromptQL in action immediately
- Monitor execution time celebrations for performance insights (⚡ Lightning fast! to ☕ Time for a coffee break!)

## 🔐 Environment Configuration

The application requires the following environment variables:
- `DATABASE_URL`: PostgreSQL connection string (format: `postgresql+asyncpg://user:password@host:port/dbname`)
- `GROQ_API_KEY`: API key for LLM services (get one at [groq.com](https://groq.com))
- `SECRET_KEY`: Secret key for session security (generate a random 32+ hex string)
- `ENCRYPTION_KEY`: Key for encrypting sensitive data (32-byte hex string)
- `LLM_MODEL`: LLM to use (default: `mixtral-8x7b-32768`)
- `LLM_MAX_RETRIES`: Max LLM retry attempts (default: 3)
- `LLM_TIMEOUT`: LLM request timeout in seconds (default: 30)
- `EMBEDDING_MODEL`: Sentence transformer for schema embeddings (default: `all-MiniLM-L6-v2`)
- `EMBEDDING_BATCH_SIZE`: Batch size for embedding generation (default: 32)
- `STATEMENT_TIMEOUT_MS`: Database query timeout in milliseconds (default: 10000)
- `MAX_OUTPUT_ROWS`: Maximum rows to return from queries (default: 100)
- `SESSION_READ_ONLY`: Enforce read-only database sessions (default: true)
- `LOG_LEVEL`: Logging level (default: INFO)
- `ENVIRONMENT`: Deployment environment (default: development)
- `API_V1_STR`: API version prefix (default: `/api/v1`)
- `PROJECT_NAME`: Application name (default: PromptQL)
- `BACKEND_CORS_ORIGINS`: List of allowed CORS origins (default: `[http://localhost:3000, http://localhost:8080]`)
- `RATE_LIMIT_PER_MINUTE`: API rate limit per IP (default: 60)

**Important**: Your `.env` file containing these secrets is automatically ignored by Git (via `.gitignore`) and should never be committed to the repository.

## 📁 Project Structure

```
promptql/
├── backend/              # Backend application
│   ├── app/              # FastAPI application
│   │   └── main.py       # Application entry point and API routes
│   ├── core/             # Core utilities (config, logger, exceptions)
│   ├── db/               # Database models, initialization, and session management
│   │   ├── base.py       # Database session configuration
│   │   ├── models.py     # SQLAlchemy models (ConnectionMetadata, etc.)
│   │   └── init_db.py    # Database initialization script
│   ├── services/         # Business logic services
│   │   ├── connection_service.py  # Database connection handling and encryption
│   │   ├── schema_service.py      # Database schema extraction and caching
│   │   ├── retrieval_service.py   # Semantic search and golden query caching
│   │   ├── llm_service.py         # Natural language processing and SQL generation
│   │   ├── validation_service.py  # SQL validation and safety checking
│   │   └── execution_service.py   # Safe SQL query execution
│   └── utils/            # Utility helper functions
├── frontend/             # Frontend web interface
│   ├── index.html        # Main application (HTML/CSS/JS)
│   └── assets/           # Static assets directory (for GIFs, images, etc.)
│       ├── architecture.gif      ← System architecture diagram (add your own)
│       ├── demo.gif              ← Main demonstration GIF (add your own)
│       └── README.md             ← Instructions for asset files
├── migrations/           # Database migration scripts (Alembic format)
├── .gitignore            # Git ignore rules (protects secrets and temp files)
├── .env.example          # Environment variables template (copy to .env)
├── requirements.txt      # Python dependencies for production
└── README.md             # This file
```

### Assets Directory
Place your visual assets in the `assets/` directory:
- `architecture.gif` - System architecture diagram (referenced in Architecture section)
- `demo.gif` - Main demonstration GIF (showcasing key features)
- `feature-query-history.gif` - Shows query history sidebar in action
- `feature-theme-toggle.gif` - Demonstrates dark/light theme switching
- `feature-export-formats.gif` - Highlights CSV/JSON/Excel export options
- `feature-success-celebration.gif` - Captures confetti animation on successful queries
- `feature-query-time.gif` - Shows fun facts based on query execution speed
- Any other images or animations you'd like to showcase

## 🔒 Security (Expanded)

### 🔐 Authentication & Authorization
- **Bearer Token Authentication**: Simple but effective token validation
- **Token Source**: Must match `SECRET_KEY` environment variable exactly
- **Header Transmission**: `Authorization: Bearer <token>` for all API requests
- **No Token Storage**: Frontend only holds token temporarily for requests
- **Stateless Design**: No server-side session storage reduces attack surface

### 🛡️ Data Protection & Privacy
- **At-Rest Encryption**: Database credentials encrypted using Fernet symmetric encryption
- **Key Rotation Support**: Change `ENCRYPTION_KEY` and re-encrypt credentials as needed
- **Minimal Data Persistence**: Only essential connection metadata stored
- **Purpose Limitation**: Data used solely for connection management (no secondary use)
- **Secure Defaults**: Read-only transactions, statement timeouts, row limits

### 🧪 Input Validation & Sanitization
- **Multi-Stage Validation**: 
  1. Input sanitization at API boundary
  2. SQL syntax validation via parser
  3. Semantic validation for safety (no DROP, DELETE, etc. by default)
  4. Resource limit validation (timeout, row counts)
- **Parameterized Queries**: Where applicable, uses proper parameter binding
- **Error Message Sanitization**: Prevents information leakage through error responses
- **Prepared Statements**: Database driver handles proper escaping when possible

### 🌐 Network & Transport Security
- **HTTPS Compatibility**: Works correctly behind TLS proxies/load balancers
- **CORS Protection**: Configurable origin restrictions prevent unauthorized browser access
- **Header Validation**: Strict validation of required headers (Authorization, Content-Type)
- **Request Size Limits**: Prevents oversized payloads from causing resource exhaustion
- **Connection Limits**: Database connection pool sizing prevents resource exhaustion

### 📝 Audit & Monitoring
- **Structured Logging**: JSON-formatted logs for security-relevant events
- **Error Tracking**: Structured error responses without internal details
- **Access Logging**: Successful and failed authentication attempts logged
- **Performance Monitoring**: Query execution timing available in metadata
- **Dependency Scanning**: Regular updates via `pip list --outdated` and `safety check`

## 🤝 Contributing

We welcome contributions that enhance functionality, improve documentation, fix bugs, or add new features!

### 📝 Contribution Guidelines
1. Fork the repository on GitHub
2. Create a new branch for your feature or fix (`git checkout -b feature/amazing-feature`)
3. Make your changes, ensuring they follow the existing code style
4. Add or update tests as appropriate
5. Ensure all existing tests still pass
6. Commit your changes with a clear, descriptive message
7. Push to your branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request against the `main` branch
9. Please include a clear description of the changes and their purpose

### 🐛 Reporting Issues
When reporting bugs, please include:
- PromptQL version (from `README.md` or `git log`)
- Environment details (Python version, PostgreSQL version, OS)
- Steps to reproduce the issue
- Expected behavior vs. actual behavior
- Any relevant error messages or logs
- Minimal reproduction case if possible

### 💡 Suggesting Features
Feature suggestions should include:
- Clear use case description
- Potential benefits to users
- Any relevant technical considerations
- Whether you're willing to help implement it

### 🏗️ Development Setup
For contributors wanting to run a development environment:
1. Follow the [Getting Started](#-getting-started) section above
2. Install development dependencies: `pip install -r requirements-dev.txt` (if applicable)
3. Run tests: `pytest` or `python -m pytest`
4. Run linter: `flake8` or `black --check .`
5. Use pre-commit hooks: `pre-commit install` (if configured)

### 📄 Pull Request Process
1. Ensure your PR description clearly explains the changes
2. Reference any related issues (`#issue-number`)
3. Include screenshots or GIFs for UI changes (place in `assets/` and reference)
4. Ensure code follows existing style and conventions
5. Add tests for new functionality
6. Update documentation if affected
7. Maintainers will review and provide feedback
8. Once approved, maintainers will merge the PR

## 📜 License

This project is licensed under the [MIT License](LICENSE) - see the [LICENSE](LICENSE) file for details.

### 📄 License Summary
```
MIT License

Copyright (c) 2026 [Your Name or Organization]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY.
```

---

<p align="center">
  <i>Made with ❤️ for data enthusiasts who want to explore their databases without writing SQL</i>
</p>

<p align="center">
  <a href="https://github.com/yourusername/promptql/stargazers">
    <img alt="GitHub Stars" src="https://img.shields.io/github/stars/yourusername/promptql?style=social">
  </a>
  <a href="https://github.com/yourusername/promptql/network/members">
    <img alt="GitHub Forks" src="https://img.shields.io/github/forks/yourusername/promptql?style=social">
  </a>
  <a href="https://github.com/yourusername/promptql/subscription">
    <img alt="GitHub Watchers" src="https://img.shields.io/github/subscriptions/yourusername/promptql?style=social">
  </a>
</p>