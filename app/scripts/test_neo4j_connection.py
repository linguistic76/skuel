#!/usr/bin/env python3
"""
Test Neo4j Connection
======================

Test Neo4j connection with credentials from the encrypted store.
"""

import os
import sys
import traceback
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from neo4j import GraphDatabase

from core.config.credential_store import get_credential

load_dotenv()


def test_connection():
    """Test Neo4j connection with stored credentials."""
    print("=" * 60)
    print("Neo4j Connection Test")
    print("=" * 60)
    print()

    # Get connection details
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)

    print(f"URI:      {uri}")
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password) if password else 'NOT SET'}")
    print(f"Password length: {len(password) if password else 0}")
    print()

    if not password:
        print("❌ ERROR: Neo4j password not found in credential store or environment")
        print()
        print("Set password with:")
        print("  poetry run python scripts/set_neo4j_password.py")
        return False

    print("Testing connection...")
    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))

        with driver.session() as session:
            result = session.run("RETURN 1 as num")
            record = result.single()

            if record and record["num"] == 1:
                print("✅ SUCCESS! Connection works!")
                print()
                print("Your Neo4j credentials are correct.")
                print("The application should now start successfully.")
                driver.close()
                return True
            else:
                print("❌ FAILED: Unexpected result from Neo4j")
                driver.close()
                return False

    except Exception as e:
        error_str = str(e)
        print(f"❌ FAILED: {error_str}")
        print()

        if "Unauthorized" in error_str or "authentication failure" in error_str:
            print("The password in the credential store is incorrect.")
            print()
            print("Common issues:")
            print("1. Default Neo4j password is 'neo4j' (must change on first login)")
            print("2. Password may have been changed in Neo4j Desktop")
            print("3. You may have multiple Neo4j databases with different passwords")
            print()
            print("Solutions:")
            print()
            print("Option 1 - Update stored password:")
            print("  poetry run python scripts/set_neo4j_password.py")
            print()
            print("Option 2 - Reset Neo4j password (Neo4j Desktop):")
            print("  - Open Neo4j Desktop")
            print("  - Click on your database")
            print("  - Click 'Reset password'")
            print("  - Then update SKUEL: poetry run python scripts/set_neo4j_password.py")
            print()
            print("Option 3 - Check what password Neo4j Desktop is using:")
            print("  - Neo4j Desktop → Your Database → ... menu → Details")
            print("  - Look for 'Password' or 'Connection details'")

        elif "ServiceUnavailable" in error_str or "connection refused" in error_str:
            print("Neo4j is not running or not accessible.")
            print()
            print("Start Neo4j:")
            print("  - Neo4j Desktop: Click 'Start' on your database")
            print("  - Docker: docker start neo4j")
            print("  - System service: sudo systemctl start neo4j")

        else:
            print("Unexpected error. Full details:")
            traceback.print_exc()

        return False


if __name__ == "__main__":
    success = test_connection()
    print()
    print("=" * 60)
    sys.exit(0 if success else 1)
