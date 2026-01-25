#!/usr/bin/env python3
"""
SKUEL Main Application - Composition Root Pattern
=================================================

Simplified main.py that uses the composition root bootstrap.
Eliminates the 300+ line Application class in favor of clean composition.

This demonstrates the evolution from:
- Complex Application class with service registry globals
- To clean composition root with explicit dependencies
"""

import argparse
import asyncio
import sys
import traceback

import uvicorn
from dotenv import load_dotenv

from core.config.settings import get_api_config
from core.utils.logging import get_logger
from scripts.dev.bootstrap import bootstrap_skuel

__version__ = "1.0"

# Load .env for local dev convenience (env vars read lazily by get_settings())
load_dotenv()

logger = get_logger("skuel.main")


async def main() -> None:
    """Clean main function using composition root pattern."""
    # Get API config for CLI defaults (same cached instance as container.config)
    api_config = get_api_config()

    parser = argparse.ArgumentParser(description="SKUEL Application")
    parser.add_argument("--port", type=int, default=api_config.port, help="Port to run on")
    parser.add_argument("--host", type=str, default=api_config.host, help="Host to bind to")
    args = parser.parse_args()

    logger.info("🚀 Starting SKUEL with composition root pattern")

    # Bootstrap the entire application (single composition point)
    container = await bootstrap_skuel()
    logger.info("✅ Application bootstrapped successfully")

    # Configure uvicorn server with lifespan support
    config = container.config

    uvicorn_config = uvicorn.Config(
        container.app,
        host=args.host,
        port=args.port,
        reload=config.application.debug,
        log_level=(config.application.log_level or "info").lower(),
        access_log=config.application.debug,  # Enable in dev for route debugging
        lifespan="on",  # Enable lifespan for proper startup/shutdown
    )

    server = uvicorn.Server(uvicorn_config)
    # Let Uvicorn handle signal management - no manual handlers needed

    logger.info(f"🌟 SKUEL starting on http://{args.host}:{args.port}")
    logger.info("📋 Architecture: Composition Root (no service registry globals)")
    if config.application.debug:
        logger.info("🔁 Uvicorn reload enabled (development mode)")

    # Run server - lifespan will handle cleanup
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Application interrupted by user")
    except Exception as e:
        logger.error(f"💥 Application crashed: {e}")
        traceback.print_exc()
        sys.exit(1)
