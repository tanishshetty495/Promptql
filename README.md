# PromptQL - Schema-Aware Text-to-SQL Engine

A web application that lets users connect their cloud-hosted PostgreSQL databases and ask questions in natural language. The system converts questions into safe, correct SQL queries, executes them, and returns results with the SQL and plain-English summary.

## Backend Implementation

This repository contains the backend implementation for PromptQL. See `backend/PROJECT_OVERVIEW.md` for detailed implementation guidelines.

## Getting Started

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. Initialize the database:
   ```bash
   python -m backend.db.init_db
   ```

4. Run the application:
   ```bash
   uvicorn backend.app.main:app --reload
   ```

## Project Structure

See `backend/PROJECT_OVERVIEW.md` for detailed architecture and implementation approach.