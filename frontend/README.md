# PromptQL Frontend

A simple web frontend for the PromptQL Schema-Aware Text-to-SQL Engine backend.

## Features

- Manage database connections (add, view, remove)
- Ask natural language questions about your data
- View generated SQL and query results
- Copy SQL to clipboard
- Download results as CSV
- Responsive design with Bootstrap

## Getting Started

### Prerequisites

1. PromptQL backend running (default: http://localhost:8000)
2. Modern web browser

### Usage

1. Start the PromptQL backend (refer to backend documentation)
2. Open `frontend/index.html` in your web browser
3. Add a database connection using the "Add New Connection" button
4. Select your connection from the list
5. Ask a question in natural language in the text area
6. Click "Generate & Execute SQL" to process your query
7. View the generated SQL, results, and query metadata

## API Endpoints Used

The frontend interacts with the following backend endpoints:

- `GET /health` - Check backend status
- `POST /connections` - Create a new database connection
- `POST /query` - Execute a natural language query (main functionality)
- (Indirectly uses other endpoints for connection management)

## Customization

To change the backend URL, edit the `backendUrl` variable in the JavaScript section of `index.html`:

```javascript
this.backendUrl = 'http://your-backend-url:port';
```

## Security Note

This frontend is designed for development and demonstration purposes. For production use:

1. Implement proper authentication (the backend expects a token)
2. Use HTTPS in production
3. Do not store credentials in localStorage (this demo does for simplicity)
4. Implement proper input validation and sanitization
5. Consider using a frontend framework like React or Vue for larger applications

## Development

This frontend uses:
- Bootstrap 5 for styling
- Font Awesome for icons
- Axios for HTTP requests
- Vanilla JavaScript (no build step required)

To modify the styling or functionality, edit `index.html` directly.