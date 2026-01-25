"""
Test Fixtures - Service Factories
==================================

Test infrastructure that mirrors production service composition.

This module provides factory functions for creating services in tests
using the same composition pattern as production, while allowing
behavior customization for testing.

Philosophy:
- Tests should use the same composition as production
- Service constructors create sub-components internally
- Factory functions provide mock backends/drivers
- Behavior can be customized per test without breaking encapsulation

Usage:
    from tests.fixtures.service_factories import create_moc_service_for_testing

    def test_something():
        service = create_moc_service_for_testing(
            section_behavior={"add_section": Result.ok(section)}
        )
        # Test using service facade methods
"""
