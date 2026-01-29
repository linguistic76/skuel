#!/bin/bash
# Interactive guide to enable Neo4j GenAI plugin

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "=========================================="
echo "  Neo4j GenAI Plugin Setup Assistant"
echo "=========================================="
echo -e "${NC}"

echo ""
echo "This script will guide you through enabling the GenAI plugin."
echo ""

# Check if already enabled
echo "Checking current status..."
PLUGIN_STATUS=$(poetry run python -c "
import asyncio
from neo4j import AsyncGraphDatabase
import os

async def check():
    driver = AsyncGraphDatabase.driver(
        os.getenv('NEO4J_URI'),
        auth=('neo4j', os.getenv('NEO4J_PASSWORD'))
    )
    try:
        async with driver.session() as session:
            result = await session.run('RETURN ai.text.embed(\"test\") AS e')
            await result.single()
            return 'ENABLED'
    except Exception as e:
        if 'Unknown function' in str(e) or 'ProcedureNotFound' in str(e):
            return 'NOT_ENABLED'
        return 'ERROR'
    finally:
        await driver.close()

print(asyncio.run(check()))
" 2>&1)

if [ "$PLUGIN_STATUS" == "ENABLED" ]; then
    echo -e "${GREEN}✅ GenAI plugin is already enabled!${NC}"
    echo ""
    echo "You can proceed directly to deployment validation:"
    echo "  ./scripts/production/deploy_checklist.sh"
    exit 0
fi

if [ "$PLUGIN_STATUS" == "ERROR" ]; then
    echo -e "${RED}❌ Error connecting to Neo4j${NC}"
    echo "Check your environment configuration (.env file)"
    exit 1
fi

echo -e "${YELLOW}⚠️  GenAI plugin is NOT enabled${NC}"
echo ""

# Manual steps
echo -e "${BLUE}STEP 1: Open AuraDB Console${NC}"
echo "-------------------------------------------"
echo "URL: https://console.neo4j.io"
echo ""
read -p "Press ENTER when you've opened the console..."

echo ""
echo -e "${BLUE}STEP 2: Navigate to Your Database${NC}"
echo "-------------------------------------------"
echo "Database ID: c3a6c0c8"
echo "URI: neo4j+s://c3a6c0c8.databases.neo4j.io"
echo ""
read -p "Press ENTER when you've selected the database..."

echo ""
echo -e "${BLUE}STEP 3: Go to Plugins Tab${NC}"
echo "-------------------------------------------"
echo "Click on 'Plugins' in the left sidebar"
echo ""
read -p "Press ENTER when you're on the Plugins page..."

echo ""
echo -e "${BLUE}STEP 4: Enable GenAI Plugin${NC}"
echo "-------------------------------------------"
echo "1. Find 'GenAI' in the plugin list"
echo "2. Click 'Enable' button"
echo "3. Wait for status to change to 'Active' (2-3 minutes)"
echo ""
read -p "Press ENTER when the plugin is enabled..."

echo ""
echo -e "${BLUE}STEP 5: Configure OpenAI API Key${NC}"
echo "-------------------------------------------"
echo "The GenAI plugin needs OpenAI credentials."
echo ""
echo "Option A: Via Console (Recommended)"
echo "  1. In GenAI plugin settings, find 'API Keys'"
echo "  2. Add your OpenAI API key"
echo "  3. Save"
echo ""
echo "Option B: Via Cypher Query"
echo "  Run this in Neo4j Browser:"
echo ""
echo "  CALL ai.config.set('openai.apiKey', '\$OPENAI_API_KEY');"
echo ""
read -p "Press ENTER when API key is configured..."

echo ""
echo "Waiting 30 seconds for plugin to fully activate..."
sleep 30

echo ""
echo "Verifying plugin is working..."

VERIFICATION=$(poetry run python -c "
import asyncio
from neo4j import AsyncGraphDatabase
import os

async def verify():
    driver = AsyncGraphDatabase.driver(
        os.getenv('NEO4J_URI'),
        auth=('neo4j', os.getenv('NEO4J_PASSWORD'))
    )
    try:
        async with driver.session() as session:
            result = await session.run('RETURN ai.text.embed(\"test\") AS e')
            record = await result.single()
            if record and record['e']:
                print(f'SUCCESS:{len(record[\"e\"])}')
            else:
                print('FAILED:No embedding returned')
    except Exception as e:
        print(f'FAILED:{str(e)[:100]}')
    finally:
        await driver.close()

asyncio.run(verify())
" 2>&1)

if echo "$VERIFICATION" | grep -q "SUCCESS"; then
    DIM=$(echo "$VERIFICATION" | cut -d: -f2)
    echo -e "${GREEN}✅ GenAI plugin is working!${NC}"
    echo "  Embedding dimension: $DIM"
    echo ""
    echo -e "${GREEN}SETUP COMPLETE!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Run deployment validation:"
    echo "     ./scripts/production/deploy_checklist.sh"
    echo ""
    echo "  2. Start the application:"
    echo "     poetry run python main.py"
    echo ""
    echo "  3. Monitor worker metrics:"
    echo "     curl http://localhost:8000/api/monitoring/embedding-worker"
    echo ""
else
    ERROR=$(echo "$VERIFICATION" | cut -d: -f2)
    echo -e "${RED}❌ GenAI plugin verification failed${NC}"
    echo "Error: $ERROR"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Wait longer (plugin may still be activating)"
    echo "  2. Verify API key in AuraDB console"
    echo "  3. Check Neo4j Browser: RETURN ai.text.embed('test')"
    echo "  4. Review: docs/deployment/ENABLE_GENAI_PLUGIN.md"
    echo ""
    echo "Run this script again when ready to retry."
    exit 1
fi
