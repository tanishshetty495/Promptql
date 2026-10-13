# PromptQL: Schema-Aware Text-to-SQL Engine

## Overview
PromptQL is a natural language interface for databases that converts user questions into safe, executable SQL queries. It combines large language models with database schema awareness to provide accurate text-to-SQL capabilities while maintaining strong security guarantees.

## Core Functionality
- **Natural Language to SQL Conversion**: Users ask questions in plain English (e.g., "What is the average salary by department?") and the system generates corresponding SQL queries
- **Schema Awareness**: The system understands database structure (tables, columns, relationships) to generate contextually appropriate SQL
- **Safety-First Design**: Multiple layers of protection ensure only safe, read-only queries can execute
- **Explainable AI**: Provides plain-English explanations of generated SQL to build user trust
- **Result Visualization**: Automatically generates charts from query results when appropriate
- **Self-Correction Loop**: Retries and improves SQL generation when initial attempts fail

## Key Features

### 1. Semantic Understanding
- Uses sentence-transformers (all-MiniLM-L6-v2) for embedding-based similarity search
- Retrieves relevant schema information based on user question
- Implements semantic caching to reuse similar previously answered questions
- Routes questions by complexity (simple vs complex) for optimal model usage

### 2. SQL Generation & Validation
- Generates SQL using LLMs (Groq API with models like mixtral-8x7b or openai/gpt-oss-20b)
- Employs self-correction loop (up to 3 attempts) with error context feedback
- Validates all SQL through strict safety checks:
  - Only SELECT statements allowed (no INSERT/UPDATE/DELETE/DROP)
  - Multi-statement queries blocked
  - Schema-limited generation (no hallucinated tables/columns)
  - Prompt injection prevention via delimiter-based safe prompting

### 3. Security Model
- **Read-only Sessions**: All database connections configured as read-only
- **Statement Timeout**: Configurable timeout (default 10s) prevents long-running queries
- **Credential Security**: AES-256 encryption for stored database credentials
- **Input Validation**: Strict validation of all user inputs and connection parameters
- **Output Sanitization**: Safe rendering of query results in frontend

### 4. Explainable AI
- Generates plain-English, bulleted explanations of what each SQL query does
- Focuses on: data retrieved, processing steps (joins, groupings, aggregations), filters applied, and final result
- Implemented as lightweight LLM call after successful SQL validation/execution
- Graceful degradation: if explanation fails, main functionality continues unaffected

### 5. Result Presentation
- Tabular display of query results
- Automatic chart generation (bar, line, etc.) based on data characteristics
- Optional natural language summary of results for small result sets
- Export capabilities (CSV download, SQL copy to clipboard)
- Query metadata display (execution time, row count, attempt history)

### 6. Performance Optimizations
- Semantic caching: Reuses SQL from similar past questions (similarity threshold: 0.98)
- Golden query storage: Persists high-quality question-SQL pairs for future reuse
- Connection pooling: Efficient database connection management
- Schema caching: Reduces overhead of repeated schema extraction

## Technical Architecture

### Backend (Python/FastAPI)
- **API Layer**: RESTful endpoints for connections, queries, health checks
- **Services Layer**: Modular services for LLM interaction, schema handling, validation, execution
- **Security**: JWT-based authentication, encrypted credential storage
- **Database**: SQLAlchemy with asyncpg for PostgreSQL async operations
- **LLM Integration**: LiteLLM wrapper for Groq API with retry logic and timeout handling

### Frontend (Vanilla JS/Bootstrap)
- **UI Components**: Connection management, query input, results display, charts
- **Charting**: Chart.js for basic charts, Vega-Lite/Vega for advanced visualizations
- **State Management**: Client-side state tracking for connections, queries, results
- **Responsive Design**: Mobile-friendly Bootstrap layout
- **User Experience**: Loading states, toast notifications, example queries

### Data Flow
1. User submits natural language question via frontend
2. Backend validates question and retrieves connection credentials
3. System fetches relevant schema information (cached or freshly extracted)
4. LLM generates SQL with schema context and few-shot examples
5. SQL undergoes safety validation (read-only, single statement, schema compliance)
6. If invalid, error context provided for self-correction loop (max 3 attempts)
7. Valid SQL executed against database with decrypted credentials
8. Results processed: summary generated (if <20 rows), explanation created, charts prepared
9. Response returned to frontend with SQL, results, metadata, explanation, and visualization specs
10. Frontend renders results, displays explanation prominently, shows charts if applicable

## Security Guarantees
- **Principle of Least Privilege**: Database connections restricted to read-only operations
- **Defense in Depth**: Multiple independent security layers (session restrictions + SQL validation + timeouts + encryption)
- **Zero Trust Execution**: Every query treated as potentially hostile until proven safe
- **Credential Protection**: Encryption at rest with key separation (encryption key != database credentials)
- **Audit Trail**: All connection and query activities logged for monitoring

## Use Cases
- Business intelligence and data exploration for non-technical users
- Rapid prototyping of data queries without SQL expertise
- Educational tool for learning SQL through natural language
- Self-service analytics in secure, governed environments
- Database schema discovery and understanding

## Limitations & Future Considerations
- Currently optimized for PostgreSQL (adaptable to other SQL dialects)
- Single-tenant focus; multi-tenancy would require row-level security implementation
- Limited to read-only operations (no data modification capabilities)
- Dependent on LLM quality for SQL generation accuracy
- Chart generation heuristics may not always match ideal visualization choice

## Getting Started
1. Configure database connection via the UI (host, port, database, username, password)
2. Select the connection from the connections list
3. Enter natural language question in the input box
4. Click "Generate & Execute SQL"
5. View results, explanation (above SQL), and any generated charts
6. Export results or copy SQL as needed

## Example Workflow
**Question**: "Show me the average salary by department"
1. System identifies relevant tables (employees) and columns (department, salary)
2. Generates SQL: `SELECT department, AVG(salary) AS avg_salary FROM employees GROUP BY department ORDER BY department`
3. Validates SQL: read-only, single select, schema-compliant
4. Executes query against database
5. Returns results: department names with corresponding average salaries
6. Generates explanation: "Retrieves department names and average salaries... groups by department..."
7. Creates bar chart: departments on x-axis, average salary on y-axis
8. Displays all components in the results section

---
*PromptQL v0.1.0 - Built for secure, explainable natural language database access*