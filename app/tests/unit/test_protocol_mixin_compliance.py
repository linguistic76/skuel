"""
Protocol-Mixin Compliance Test Suite
======================================

Automated verification that all 7 mixins satisfy their corresponding protocols.

This test suite ensures that:
1. Each mixin has all methods defined in its protocol
2. Method signatures match between mixin and protocol
3. TYPE_CHECKING verification blocks are present in all mixins

When a test fails, it means the mixin and protocol are out of sync.
Run MyPy to get detailed type errors: `poetry run mypy core/services/mixins/<mixin>.py`

See: /docs/investigations/PROTOCOL_MIXIN_ALIGNMENT_SOLUTIONS.md
"""

import inspect
import pathlib

import pytest

from core.services.mixins import (
    ContextOperationsMixin,
    ConversionHelpersMixin,
    CrudOperationsMixin,
    RelationshipOperationsMixin,
    SearchOperationsMixin,
    TimeQueryMixin,
    UserProgressMixin,
)
from core.services.protocols.base_service_interface import (
    ContextOperations,
    ConversionOperations,
    CrudOperations,
    RelationshipOperations,
    SearchOperations,
    TimeQueryOperations,
    UserProgressOperations,
)

# ============================================================================
# TEST DATA: MIXIN-PROTOCOL PAIRS
# ============================================================================

MIXIN_PROTOCOL_PAIRS = [
    ("Conversion", ConversionHelpersMixin, ConversionOperations, "conversion_helpers_mixin.py"),
    ("CRUD", CrudOperationsMixin, CrudOperations, "crud_operations_mixin.py"),
    ("Search", SearchOperationsMixin, SearchOperations, "search_operations_mixin.py"),
    (
        "Relationship",
        RelationshipOperationsMixin,
        RelationshipOperations,
        "relationship_operations_mixin.py",
    ),
    ("TimeQuery", TimeQueryMixin, TimeQueryOperations, "time_query_mixin.py"),
    ("UserProgress", UserProgressMixin, UserProgressOperations, "user_progress_mixin.py"),
    ("Context", ContextOperationsMixin, ContextOperations, "context_operations_mixin.py"),
]


# ============================================================================
# TEST: ALL PROTOCOL METHODS IMPLEMENTED
# ============================================================================


@pytest.mark.parametrize("name,mixin,protocol,filename", MIXIN_PROTOCOL_PAIRS)
def test_mixin_has_all_protocol_methods(name, mixin, protocol, filename):
    """Verify mixin implements all protocol methods."""
    # Get protocol methods (exclude dunder methods and properties)
    protocol_methods = [
        method_name
        for method_name in dir(protocol)
        if not method_name.startswith("__") and callable(getattr(protocol, method_name, None))
    ]

    # Verify mixin has each method
    missing_methods = [
        method_name for method_name in protocol_methods if not hasattr(mixin, method_name)
    ]

    assert not missing_methods, (
        f"{name}: {mixin.__name__} missing methods from {protocol.__name__}:\n"
        + "\n".join(f"  - {m}" for m in missing_methods)
        + f"\n\nFix by adding these methods to core/services/mixins/{filename}"
    )


# ============================================================================
# TEST: METHOD SIGNATURES MATCH
# ============================================================================


@pytest.mark.parametrize("name,mixin,protocol,filename", MIXIN_PROTOCOL_PAIRS)
def test_mixin_method_signatures_match_protocol(name, mixin, protocol, filename):
    """
    Verify mixin method signatures match protocol signatures.

    This test compares parameter names between protocol and mixin.
    Note: Type annotations may differ, but parameter names must match.
    """
    # Get protocol methods
    protocol_methods = [
        method_name
        for method_name in dir(protocol)
        if not method_name.startswith("__") and callable(getattr(protocol, method_name, None))
    ]

    mismatches = []
    for method_name in protocol_methods:
        protocol_method = getattr(protocol, method_name)
        mixin_method = getattr(mixin, method_name, None)

        if mixin_method is None:
            continue  # Already caught by previous test

        # Compare signatures
        try:
            protocol_sig = inspect.signature(protocol_method)
            mixin_sig = inspect.signature(mixin_method)
        except (ValueError, TypeError):
            # Some methods may not have inspectable signatures
            continue

        # Get parameter names
        protocol_params = list(protocol_sig.parameters.keys())
        mixin_params = list(mixin_sig.parameters.keys())

        # Allow 'self' to be in mixin but not protocol
        if "self" in mixin_params and "self" not in protocol_params:
            mixin_params = [p for p in mixin_params if p != "self"]

        if protocol_params != mixin_params:
            mismatches.append(
                f"  {method_name}:\n    Protocol: {protocol_params}\n    Mixin:    {mixin_params}"
            )

    assert not mismatches, (
        f"{name}: Method signature mismatches between "
        f"{mixin.__name__} and {protocol.__name__}:\n"
        + "\n".join(mismatches)
        + f"\n\nFix by updating signatures in:\n"
        f"  - core/services/mixins/{filename}\n"
        f"  - core/services/protocols/base_service_interface.py"
    )


# ============================================================================
# TEST: TYPE_CHECKING BLOCKS EXIST
# ============================================================================


@pytest.mark.parametrize("name,mixin,protocol,filename", MIXIN_PROTOCOL_PAIRS)
def test_mixin_has_type_checking_verification_block(name, mixin, protocol, filename):
    """Verify mixin file has TYPE_CHECKING verification block for protocol compliance."""
    mixin_file = pathlib.Path("core/services/mixins") / filename
    content = mixin_file.read_text()

    # Verify has TYPE_CHECKING block
    assert "if TYPE_CHECKING:" in content, (
        f"{name}: {filename} missing TYPE_CHECKING verification block\n\n"
        f"Add this block at the end of the file:\n\n"
        f"if TYPE_CHECKING:\n"
        f"    from core.services.protocols.base_service_interface import {protocol.__name__}\n\n"
        f"    _protocol_check: type[{protocol.__name__}[Any]] = {mixin.__name__}  # type: ignore[type-arg]"
    )

    # Verify imports protocol
    assert "from core.services.protocols.base_service_interface import" in content, (
        f"{name}: {filename} doesn't import from base_service_interface\n\n"
        f"Add this import inside the TYPE_CHECKING block:\n"
        f"    from core.services.protocols.base_service_interface import {protocol.__name__}"
    )

    # Verify has protocol check assignment
    assert "_protocol_check" in content, (
        f"{name}: {filename} missing _protocol_check assignment\n\n"
        f"Add this line inside the TYPE_CHECKING block:\n"
        f"    _protocol_check: type[{protocol.__name__}[Any]] = {mixin.__name__}  # type: ignore[type-arg]"
    )

    # Verify references the correct protocol
    protocol_name = protocol.__name__
    assert protocol_name in content, (
        f"{name}: {filename} doesn't reference {protocol_name} protocol\n\n"
        f"Make sure the TYPE_CHECKING block imports and uses {protocol_name}"
    )


# ============================================================================
# TEST: COMPLETE COVERAGE
# ============================================================================


def test_all_seven_mixins_are_tested():
    """Ensure all 7 BaseService mixins have test coverage."""
    assert len(MIXIN_PROTOCOL_PAIRS) == 7, (
        "BaseService is composed of 7 mixins. "
        f"Found {len(MIXIN_PROTOCOL_PAIRS)} mixin-protocol pairs in test data. "
        "Update MIXIN_PROTOCOL_PAIRS if mixins were added/removed."
    )


def test_all_mixin_files_exist():
    """Verify all mixin files referenced in tests actually exist."""
    mixin_dir = pathlib.Path("core/services/mixins")

    missing_files = []
    for name, _mixin, _protocol, filename in MIXIN_PROTOCOL_PAIRS:
        file_path = mixin_dir / filename
        if not file_path.exists():
            missing_files.append(f"{name}: {filename}")

    assert not missing_files, "Mixin files referenced in tests don't exist:\n" + "\n".join(
        f"  - {f}" for f in missing_files
    )


# ============================================================================
# INTEGRATION TEST: VERIFY MYPY CAN CHECK COMPLIANCE
# ============================================================================


def test_type_checking_blocks_use_correct_syntax():
    """
    Verify TYPE_CHECKING blocks use correct syntax for MyPy verification.

    The syntax must be:
        if TYPE_CHECKING:
            from core.services.protocols.base_service_interface import ProtocolName
            _protocol_check: type[ProtocolName[Any]] = MixinClass  # type: ignore[type-arg]

    This allows MyPy to verify structural compatibility.
    """
    mixin_dir = pathlib.Path("core/services/mixins")

    for name, mixin, protocol, filename in MIXIN_PROTOCOL_PAIRS:
        file_path = mixin_dir / filename
        content = file_path.read_text()

        # Verify uses type[Protocol[Any]] annotation (correct syntax for MyPy)
        # The exact syntax should be: _protocol_check: type[ProtocolName[Any]] = MixinClass
        protocol_name = protocol.__name__
        mixin_name = mixin.__name__

        # Check for the correct pattern
        expected_pattern = f"type[{protocol_name}[Any]] = {mixin_name}"

        assert expected_pattern in content, (
            f"{name}: {filename} has incorrect TYPE_CHECKING syntax\n\n"
            f"Expected:\n"
            f"    _protocol_check: type[{protocol_name}[Any]] = {mixin_name}  # type: ignore[type-arg]\n\n"
            f"This syntax allows MyPy to verify structural compatibility."
        )


# ============================================================================
# DOCUMENTATION TEST
# ============================================================================


def test_protocol_mixin_alignment_documentation_exists():
    """Verify protocol-mixin alignment solution documentation exists."""
    doc_file = pathlib.Path("docs/investigations/PROTOCOL_MIXIN_ALIGNMENT_SOLUTIONS.md")

    assert doc_file.exists(), (
        "Protocol-mixin alignment documentation missing!\n\n"
        "Expected file: docs/investigations/PROTOCOL_MIXIN_ALIGNMENT_SOLUTIONS.md\n\n"
        "This document explains how to keep protocols and mixins in sync."
    )


# ============================================================================
# USAGE EXAMPLES (FOR DOCUMENTATION)
# ============================================================================


class TestProtocolComplianceExamples:
    """
    Examples demonstrating how protocol compliance works.

    These tests serve as living documentation for the pattern.
    """

    def test_example_structural_subtyping(self):
        """
        Demonstrate Python's Protocol uses structural subtyping.

        ConversionHelpersMixin does NOT inherit from ConversionOperations,
        but it satisfies the protocol structurally (duck typing for types).
        """
        # Verify mixin doesn't inherit from protocol
        assert ConversionOperations not in ConversionHelpersMixin.__bases__, (
            "ConversionHelpersMixin should NOT inherit from ConversionOperations - "
            "it satisfies it structurally via Protocol!"
        )

        # But it still has all the protocol methods
        protocol_methods = [
            "_ensure_exists",
            "_to_domain_model",
            "_to_domain_models",
            "_from_domain_model",
            "_records_to_domain_models",
            "_validate_required_user_uid",
            "_create_and_convert",
        ]

        for method_name in protocol_methods:
            assert hasattr(ConversionHelpersMixin, method_name), (
                f"ConversionHelpersMixin missing {method_name}"
            )

    def test_example_mypy_verification(self):
        """
        Example of what MyPy verifies with TYPE_CHECKING blocks.

        The TYPE_CHECKING block in each mixin:

        ```python
        if TYPE_CHECKING:
            from core.services.protocols.base_service_interface import (
                ConversionOperations,
            )

            _protocol_check: type[ConversionOperations[Any]] = ConversionHelpersMixin
        ```

        How it works:
        1. TYPE_CHECKING is only True during static analysis (MyPy), never at runtime
        2. MyPy tries to assign ConversionHelpersMixin to type[ConversionOperations[Any]]
        3. This only succeeds if the mixin structurally satisfies the protocol
        4. If signatures don't match, MyPy raises a type error
        5. Zero runtime cost - code is never executed

        To verify manually:
            poetry run mypy core/services/mixins/conversion_helpers_mixin.py
        """
        # This test just documents the behavior
        pass

    def test_example_signature_mismatch_detection(self):
        """
        Example of what happens when signatures diverge.

        If ConversionHelpersMixin._to_domain_model signature was:
            def _to_domain_model(self, data: str) -> T:  # Wrong parameter name!

        But ConversionOperations._to_domain_model signature is:
            def _to_domain_model(self, data: Any, dto_class: type[Any], ...) -> T:

        Then:
        1. This test would fail (parameter names don't match)
        2. MyPy would fail (structural compatibility broken)
        3. Developer is immediately alerted to the mismatch

        This prevents the codebase from having mismatched signatures!
        """
        # Verify current signatures match (as of 2026-01-29)
        mixin_sig = inspect.signature(ConversionHelpersMixin._to_domain_model)
        protocol_sig = inspect.signature(ConversionOperations._to_domain_model)

        mixin_params = list(mixin_sig.parameters.keys())
        protocol_params = list(protocol_sig.parameters.keys())

        # Remove 'self' from both for comparison
        mixin_params = [p for p in mixin_params if p != "self"]
        protocol_params = [p for p in protocol_params if p != "self"]

        assert mixin_params == protocol_params, (
            f"Signature mismatch detected!\n"
            f"  Mixin:    {mixin_params}\n"
            f"  Protocol: {protocol_params}\n\n"
            "This is exactly what this test suite prevents!"
        )


# ============================================================================
# SUMMARY
# ============================================================================


def test_protocol_compliance_summary():
    """
    Test suite summary and usage guide.

    What this test suite verifies:
    1. All 7 mixins implement all protocol methods ✓
    2. Method signatures match between mixin and protocol ✓
    3. TYPE_CHECKING blocks exist for MyPy verification ✓
    4. All expected files exist ✓

    How to use:
    - Run full suite: `poetry run pytest tests/unit/test_protocol_mixin_compliance.py`
    - Run specific test: `poetry run pytest tests/unit/test_protocol_mixin_compliance.py -k signatures`
    - Run with verbose: `poetry run pytest tests/unit/test_protocol_mixin_compliance.py -v`

    When a test fails:
    1. Read the assertion message - it tells you exactly what's wrong
    2. Fix either the mixin implementation OR the protocol definition
    3. Re-run tests to verify the fix
    4. Run MyPy to catch any remaining type errors

    See: /docs/investigations/PROTOCOL_MIXIN_ALIGNMENT_SOLUTIONS.md
    """
    # This is a documentation test - always passes
    assert True
