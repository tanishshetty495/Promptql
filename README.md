# PromptQL - Schema-Aware Text-to-SQL Engine

A web application that lets users connect their cloud-hosted PostgreSQL databases and ask questions in natural language. The system converts questions into safe, correct SQL queries, executes them, and returns results with the SQL and plain-English summary.

## Features

- Natural language to SQL conversion with schema awareness
- Secure database connection handling
- Query execution with result formatting
- Plain English explanations of generated SQL
- Modular backend architecture for extensibility
- Enhanced frontend with:
  - Query history sidebar for revisiting and re-running previous queries
  - Saved queries feature for naming and saving frequently used queries
  - Dark/light theme toggle with user preference persistence
  - Multiple export formats (CSV, JSON, Excel)
  - Enhanced loading states with engaging animations
  - Success celebrations with confetti animations
  - Query time celebrations with fun facts based on execution speed
  - Improved query explanation formatting
  - Interactive connection status indicators
  - Project demonstration GIF (see below) showing the application in action

## Demo

![PromptQL Demo](assets/demo.gif)

*Note: The demo GIF shows the application in action with natural language querying, query history, theme toggle, and export functionality.*

## Backend Implementation

This repository contains the backend implementation for PromptQL. See `backend/PROJECT_OVERVIEW.md` for detailed implementation guidelines.

## Getting Started

### Prerequisites
- Python 3.8+
- PostgreSQL database
- Git (for cloning the repository)

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
   # Never commit your .env file - it's protected by .gitignore
   ```

4. Initialize the database:
   ```bash
   python -m backend.db.init_db
   ```

5. Run the application:
   ```bash
   uvicorn backend.app.main:app --reload
   ```

### Usage Tips

- Use the **Save Query** feature (star icon) to save frequently used queries with custom names
- Access your saved queries from the connection panel
- Use the query history panel to revisit and re-run previous queries
- Toggle between light and dark themes using the theme switch in the header
- Export results in CSV, JSON, or Excel formats using the export dropdown

## Environment Configuration

The application requires the following environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `GROQ_API_KEY`: API key for LLM services (if applicable)
- `SECRET_KEY`: Secret key for session security
- `ENCRYPTION_KEY`: Key for encrypting sensitive data

**Important**: Your `.env` file containing these secrets is automatically ignored by Git (via `.gitignore`) and should never be committed to the repository.

## Project Structure

```
promptql/
├── backend/              # Backend application
│   ├── app/              # FastAPI application
│   ├── core/             # Core utilities (config, logger, etc.)
│   ├── db/               # Database models and initialization
│   ├── services/         # Business logic services
│   └── utils/            # Utility functions
├── frontend/             # Frontend web interface
├── migrations/           # Database migration scripts
├── .gitignore            # Git ignore rules (protects secrets)
├── .env.example          # Environment variables template
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

## Security

- All sensitive configuration is stored in `.env` (never committed)
- The `.gitignore` file explicitly blocks:
  - Environment files (`*.env`)
  - Log files (`*.log`)
  - PID files (`*.pid`)
  - Python bytecode (`__pycache__/`, `*.pyc`)
  - Temporary files and development artifacts
- Never add your actual `.env` file to version control

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.