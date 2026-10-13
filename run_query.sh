#!/usr/bin/env bash
set -euo pipefail

cd "C:\sql ai agent"

# Load environment variables from .env (only the ones we need)
export DATABASE_URL=$(grep '^DATABASE_URL=' .env | cut -d'=' -f2-)
export SECRET_KEY=$(grep '^SECRET_KEY=' .env | cut -d'=' -f2-)

# Start backend
echo "Starting backend..."
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID $BACKEND_PID"

# Wait for backend to be ready
echo "Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null; then
        echo "Backend is ready."
        break
    fi
    sleep 1
done

# Create a connection
echo "Creating database connection..."
CONNECTION_RESPONSE=$(curl -s -X POST "http://localhost:8000/connections" \
    -H "Authorization: Bearer $SECRET_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "host": "ep-small-art-b4n6xa2q-pooler.c-6.us-east-2.aws.neon.tech",
        "port": 5432,
        "database": "neondb",
        "username": "neondb_owner",
        "password": "npg_zfjV4ep5bTat",
        "connection_name": "NeonDB"
    }')
echo "Connection response: $CONNECTION_RESPONSE"
CONNECTION_ID=$(echo "$CONNECTION_RESPONSE" | grep -o '"connection_id":"[^"]*' | cut -d'"' -f4)
if [ -z "$CONNECTION_ID" ]; then
    echo "Failed to get connection ID"
    echo "Full response: $CONNECTION_RESPONSE"
    kill $BACKEND_PID
    exit 1
fi
echo "Connection ID: $CONNECTION_ID"

# Wait a moment for schema extraction
echo "Waiting for schema extraction..."
sleep 5

# Send the query
echo "Sending query: 'Show me each employee's department name and location'"
QUERY_RESPONSE=$(curl -s -X POST "http://localhost:8000/query" \
    -H "Authorization: Bearer $SECRET_KEY" \
    -H "Content-Type: application/json" \
    -d "{
        \"connection_id\": \"$CONNECTION_ID\",
        \"question\": \"Show me each employee's department name and location\"
    }")
echo "Query response: $QUERY_RESPONSE"

# Kill backend
echo "Stopping backend..."
kill $BACKEND_PID
wait $BACKEND_PID 2>/dev/null || true

# Show relevant backend logs
echo "=== Backend log excerpt ==="
tail -n 50 backend.log
echo "=== End of log ==="