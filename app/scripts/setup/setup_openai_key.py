#!/usr/bin/env python3
"""
Quick script to set up OpenAI API key in the encrypted credential store
"""

import getpass
import sys

from dotenv import load_dotenv

from core.config.credential_store import get_credential_store

# Load .env file for master key
load_dotenv()

try:
    store = get_credential_store()
    print("✅ Credential store initialized\n")

    # Check if already set
    existing = store.get("OPENAI_API_KEY")
    if existing and existing != "your-openai-api-key-here":
        print("⚠️  OPENAI_API_KEY is already set in the encrypted store")
        update = input("Do you want to update it? [y/N]: ").strip().lower()
        if update != "y":
            print("✅ Keeping existing key")
            sys.exit(0)

    print("Please enter your OpenAI API key")
    print("(Get it from: https://platform.openai.com/api-keys)")
    print()

    api_key = getpass.getpass("OpenAI API Key: ").strip()

    if not api_key:
        print("❌ No key entered")
        sys.exit(1)

    # Basic validation
    if not api_key.startswith("sk-"):
        print("\n⚠️  Warning: OpenAI API keys usually start with 'sk-'")
        proceed = input("Continue anyway? [y/N]: ").strip().lower()
        if proceed != "y":
            print("❌ Aborted")
            sys.exit(1)

    # Save to encrypted store
    store.set("OPENAI_API_KEY", api_key)
    print("\n✅ OpenAI API key stored securely in encrypted store!")
    print("\nYou can now start SKUEL. The key will be loaded from the encrypted store.")

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
