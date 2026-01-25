#!/bin/bash
# Neo4j Authentication Fix Script
# =================================
# This script helps resolve Neo4j authentication issues

echo "SKUEL Neo4j Authentication Fix"
echo "==============================="
echo ""

# Check if Neo4j is running
echo "1. Checking if Neo4j is running..."
if nc -z localhost 7687 2>/dev/null; then
    echo "   ✅ Neo4j is running on port 7687"
else
    echo "   ❌ Neo4j is NOT running on port 7687"
    echo ""
    echo "   Please start Neo4j first:"
    echo "   - Neo4j Desktop: Click 'Start' on your database"
    echo "   - Docker: docker start neo4j"
    echo "   - System service: sudo systemctl start neo4j"
    exit 1
fi

echo ""
echo "2. Current .env configuration:"
echo "   NEO4J_URI: $(grep NEO4J_URI .env | cut -d= -f2)"
echo "   NEO4J_USERNAME: $(grep NEO4J_USERNAME .env | cut -d= -f2)"
echo "   NEO4J_PASSWORD: $(grep NEO4J_PASSWORD .env | cut -d= -f2)"

echo ""
echo "3. Common Neo4j password issues:"
echo "   - Default Neo4j password is usually 'neo4j' (first login only)"
echo "   - You may need to change password on first login"
echo "   - Check Neo4j Desktop settings for your database password"

echo ""
echo "4. Testing connection with current credentials..."

# Create a simple Python test
python3 << 'PYEOF'
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
username = os.getenv("NEO4J_USERNAME", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "your_password")

print(f"   Attempting connection to {uri}")
print(f"   Username: {username}")
print(f"   Password: {'*' * len(password)}")

try:
    driver = GraphDatabase.driver(uri, auth=(username, password))
    with driver.session() as session:
        result = session.run("RETURN 1 as num")
        record = result.single()
        if record["num"] == 1:
            print("\n   ✅ SUCCESS! Neo4j connection works!")
            print("\n   Your application should now start correctly.")
        driver.close()
except Exception as e:
    print(f"\n   ❌ FAILED: {e}")
    print("\n   Solutions:")
    print("   1. Update NEO4J_PASSWORD in .env with your actual password")
    print("   2. Or reset Neo4j password:")
    print("      - Neo4j Desktop: Database settings → Reset password")
    print("      - Docker: docker exec neo4j cypher-shell -u neo4j -p neo4j")
    print("                Then run: ALTER USER neo4j SET PASSWORD 'your_new_password';")
    print("\n   3. After fixing password, update .env file:")
    print("      NEO4J_PASSWORD=your_actual_password")
PYEOF

echo ""
echo "5. Need to update password?"
read -p "   Would you like to update NEO4J_PASSWORD in .env now? (y/n): " update_password

if [ "$update_password" = "y" ] || [ "$update_password" = "Y" ]; then
    read -sp "   Enter your Neo4j password: " new_password
    echo ""

    # Update .env file
    if grep -q "^NEO4J_PASSWORD=" .env; then
        # Replace existing password
        sed -i "s|^NEO4J_PASSWORD=.*|NEO4J_PASSWORD=$new_password|" .env
        echo "   ✅ Updated NEO4J_PASSWORD in .env"
    else
        # Add password if missing
        echo "NEO4J_PASSWORD=$new_password" >> .env
        echo "   ✅ Added NEO4J_PASSWORD to .env"
    fi

    echo ""
    echo "   Testing new password..."

    # Test again with new password
    export NEO4J_PASSWORD="$new_password"
    python3 << 'PYEOF2'
import os
from neo4j import GraphDatabase

uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
username = os.getenv("NEO4J_USERNAME", "neo4j")
password = os.getenv("NEO4J_PASSWORD")

try:
    driver = GraphDatabase.driver(uri, auth=(username, password))
    with driver.session() as session:
        result = session.run("RETURN 1 as num")
        record = result.single()
        if record["num"] == 1:
            print("   ✅ SUCCESS! Password updated and connection works!")
        driver.close()
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    print("   Please verify your password and try again.")
PYEOF2
fi

echo ""
echo "==============================="
echo "Done! Try starting SKUEL again:"
echo "  poetry run python main.py"
echo "==============================="
