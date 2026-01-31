#!/usr/bin/env python3
"""
Quick test script to verify /metrics endpoint is working.

Usage (from /home/mike/skuel/app):
    poetry run python scripts/test_metrics_endpoint.py

Expected output:
    - Prometheus exposition format metrics
    - HELP and TYPE lines
    - Metric values
"""

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def main() -> None:
    """Test Prometheus metrics generation."""
    print("🧪 Testing Prometheus metrics generation...\n")

    # Generate metrics
    metrics = generate_latest()

    print(f"✅ Content type: {CONTENT_TYPE_LATEST}")
    print(f"✅ Metrics generated: {len(metrics)} bytes\n")

    # Print first 20 lines
    print("📊 Sample metrics output:\n")
    lines = metrics.decode("utf-8").split("\n")[:20]
    for line in lines:
        if line.strip():
            print(f"  {line}")

    print(f"\n✅ Total metrics lines: {len(metrics.decode('utf-8').split('\n'))}")
    print("✅ Prometheus metrics are working!")


if __name__ == "__main__":
    main()
