#!/usr/bin/env python3
"""
Quick script to set up Deepgram API key in the encrypted credential store
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
    existing = store.get("DEEPGRAM_API_KEY")
    if existing and existing != "your-deepgram-api-key-here":
        print("⚠️  DEEPGRAM_API_KEY is already set in the encrypted store")
        update = input("Do you want to update it? [y/N]: ").strip().lower()
        if update != "y":
            print("✅ Keeping existing key")
            sys.exit(0)

    print("Please enter your Deepgram API key")
    print("(Get it from: https://console.deepgram.com/)")
    print()

    api_key = getpass.getpass("Deepgram API Key: ").strip()

    if not api_key:
        print("❌ No key entered")
        sys.exit(1)

    # Save to encrypted store
    store.set("DEEPGRAM_API_KEY", api_key)
    print("\n✅ Deepgram API key stored securely in encrypted store!")
    print("\nYou can now start SKUEL. Audio transcription features will be enabled.")

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
