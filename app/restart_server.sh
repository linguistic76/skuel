#!/bin/bash
# SKUEL Server Restart Script - ZOMBIE PROCESS PREVENTION
# Properly shuts down existing server and starts a new one

echo "🔄 Restarting SKUEL Server..."

# Step 1: Graceful shutdown first (SIGTERM)
echo "🛑 Gracefully stopping existing servers..."
pkill -TERM -f "poetry run python main.py" 2>/dev/null || true
pkill -TERM -f "python.*main.py" 2>/dev/null || true

# Give processes time to shut down gracefully
sleep 3

# Step 2: Check what's still running and force kill
echo "🔍 Checking for remaining processes..."
REMAINING=$(pgrep -f "python.*main.py" || true)
if [ ! -z "$REMAINING" ]; then
    echo "⚡ Force killing remaining processes: $REMAINING"
    pkill -KILL -f "poetry run python main.py" 2>/dev/null || true
    pkill -KILL -f "python.*main.py" 2>/dev/null || true
fi

# Step 3: Free port 8000 specifically
echo "🔌 Freeing port 8000..."
PIDS=$(lsof -ti:8000 2>/dev/null || true)
if [ ! -z "$PIDS" ]; then
    echo "🔪 Killing processes using port 8000: $PIDS"
    echo "$PIDS" | xargs kill -9 2>/dev/null || true
fi

# Step 4: Wait and verify port is free
sleep 3
if lsof -ti:8000 >/dev/null 2>&1; then
    echo "❌ Port 8000 still in use after cleanup!"
    echo "💀 This indicates zombie processes. Manual restart recommended."
    exit 1
fi

echo "✅ All processes cleaned up successfully"

# Start the server with proper environment
echo "🚀 Starting SKUEL server..."
cd /home/mike/skuel00
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD='pQm0*.Q35M8#'
export PYTHONPATH=/home/mike/skuel00

# Start server as a background process with proper process group
setsid poetry run python main.py > server.log 2>&1 &
SERVER_PID=$!

# Store PID for future management
echo $SERVER_PID > server.pid
echo "🆔 Server PID: $SERVER_PID stored in server.pid"

# Wait and verify server started
sleep 5
if kill -0 $SERVER_PID 2>/dev/null; then
    echo "✅ Server started successfully with PID: $SERVER_PID"
    echo "📊 Server running on http://localhost:8000"
    echo "📝 Logs available in server.log"
    
    # Quick health check
    if curl -s http://localhost:8000/health >/dev/null 2>&1; then
        echo "🏥 Health check passed"
    else
        echo "⚠️  Server started but health check failed (may be normal during startup)"
    fi
else
    echo "❌ Server failed to start"
    echo "📝 Check server.log for errors"
    exit 1
fi

echo ""
echo "🎯 Pro tip: To stop the server cleanly later, run:"
echo "   kill -TERM $(cat server.pid)"
echo "   This prevents zombie processes!"