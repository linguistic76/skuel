#!/usr/bin/env python3
"""
Export GraphQL Schema to SDL
=============================

Exports the SKUEL GraphQL schema to Schema Definition Language (SDL) format
for TypeScript code generation and documentation.

Usage:
    poetry run python scripts/export_graphql_schema.py
"""

from pathlib import Path

from routes.graphql import create_graphql_schema

# Add parent directory to path for imports


def export_schema():
    """Export GraphQL schema to SDL format."""
    print("\n" + "=" * 70)
    print("Exporting GraphQL Schema to SDL")
    print("=" * 70)

    # Create the schema
    print("\n1. Creating GraphQL schema...")
    schema = create_graphql_schema()
    print("   ✅ Schema created successfully")

    # Convert to SDL (Schema Definition Language)
    print("\n2. Converting to SDL format...")
    schema_sdl = str(schema)
    print(f"   ✅ Schema SDL generated ({len(schema_sdl)} characters)")

    # Write to file
    output_path = Path(__file__).parent.parent / "schema.graphql"
    print(f"\n3. Writing to {output_path}...")

    with output_path.open("w", encoding="utf-8") as f:
        f.write(schema_sdl)

    print(f"   ✅ Schema exported to {output_path}")

    # Show preview
    print("\n" + "=" * 70)
    print("Schema Preview (first 50 lines):")
    print("=" * 70)

    lines = schema_sdl.split("\n")[:50]
    for line in lines:
        print(line)

    if len(schema_sdl.split("\n")) > 50:
        print("...")
        print(f"({len(schema_sdl.split('\n')) - 50} more lines)")

    print("\n" + "=" * 70)
    print("✅ Schema export complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Install GraphQL Code Generator:")
    print("   npm install --save-dev @graphql-codegen/cli @graphql-codegen/typescript")
    print("\n2. Create codegen.yml configuration")
    print("\n3. Run code generation:")
    print("   npm run codegen")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    export_schema()
