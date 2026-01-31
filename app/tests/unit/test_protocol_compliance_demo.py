"""
Protocol Compliance Verification - Demo Test
=============================================

Demonstrates automatic verification that mixins satisfy their protocols.

This test shows how TYPE_CHECKING blocks catch signature mismatches.
"""

import inspect

from core.services.mixins import ConversionHelpersMixin
from core.services.protocols.base_service_interface import ConversionOperations


class TestProtocolComplianceDemonstration:
    """Demonstrate protocol-mixin alignment verification."""

    def test_conversion_mixin_has_all_protocol_methods(self):
        """Verify ConversionHelpersMixin implements all ConversionOperations methods."""
        # Get protocol methods (exclude dunder methods)
        protocol_methods = [
            method_name
            for method_name in dir(ConversionOperations)
            if not method_name.startswith("__")
            and callable(getattr(ConversionOperations, method_name, None))
        ]

        # Verify mixin has each method
        missing_methods = [
            method_name
            for method_name in protocol_methods
            if not hasattr(ConversionHelpersMixin, method_name)
        ]

        assert not missing_methods, (
            f"ConversionHelpersMixin missing methods from ConversionOperations: "
            f"{', '.join(missing_methods)}"
        )

    def test_conversion_mixin_method_signatures_match(self):
        """Verify method signatures match between mixin and protocol."""
        protocol_methods = [
            "_to_domain_model",
            "_from_domain_model",
            "_to_domain_models",
            "_ensure_exists",
            "_records_to_domain_models",
            "_create_and_convert",
        ]

        mismatches = []
        for method_name in protocol_methods:
            # Get methods
            protocol_method = getattr(ConversionOperations, method_name, None)
            mixin_method = getattr(ConversionHelpersMixin, method_name, None)

            # Skip if method doesn't exist (will be caught by previous test)
            if protocol_method is None or mixin_method is None:
                continue

            # Compare parameter names (signatures may differ in annotations)
            protocol_params = list(inspect.signature(protocol_method).parameters.keys())
            mixin_params = list(inspect.signature(mixin_method).parameters.keys())

            # Allow 'self' to be in mixin but not protocol
            if "self" in mixin_params and "self" not in protocol_params:
                mixin_params = [p for p in mixin_params if p != "self"]

            if protocol_params != mixin_params:
                mismatches.append(
                    f"{method_name}: protocol={protocol_params}, mixin={mixin_params}"
                )

        assert not mismatches, (
            "Signature mismatches between ConversionHelpersMixin and ConversionOperations:\n"
            + "\n".join(f"  - {m}" for m in mismatches)
        )

    def test_type_checking_block_exists_in_mixin(self):
        """Verify ConversionHelpersMixin has TYPE_CHECKING verification block."""
        import pathlib

        mixin_file = pathlib.Path("core/services/mixins/conversion_helpers_mixin.py")
        content = mixin_file.read_text()

        # Verify has TYPE_CHECKING block
        assert "if TYPE_CHECKING:" in content, (
            "ConversionHelpersMixin missing TYPE_CHECKING verification block"
        )

        # Verify imports protocol
        assert "from core.services.protocols.base_service_interface import" in content, (
            "ConversionHelpersMixin doesn't import ConversionOperations protocol"
        )

        # Verify has protocol check
        assert "_protocol_check" in content, (
            "ConversionHelpersMixin missing _protocol_check assignment"
        )

        # Verify references ConversionOperations
        assert "ConversionOperations" in content, (
            "ConversionHelpersMixin doesn't reference ConversionOperations protocol"
        )


class TestProtocolComplianceExplanation:
    """
    Explain how protocol compliance works.

    The TYPE_CHECKING block in conversion_helpers_mixin.py:

    ```python
    if TYPE_CHECKING:
        from core.services.protocols.base_service_interface import (
            ConversionOperations,
        )

        # This assignment verifies structural compatibility
        _protocol_check: type[ConversionOperations[Any]] = ConversionHelpersMixin
    ```

    How it works:
    1. `TYPE_CHECKING` is only True during static analysis (MyPy), never at runtime
    2. MyPy tries to assign ConversionHelpersMixin to type[ConversionOperations[Any]]
    3. This only succeeds if ConversionHelpersMixin structurally satisfies the protocol
    4. If signatures don't match, MyPy raises a type error
    5. Zero runtime cost - code is never executed

    Benefits:
    - Automatic verification (no manual checking)
    - Catches mismatches immediately when running MyPy
    - No runtime overhead
    - Works with existing architecture
    """

    def test_protocol_uses_structural_subtyping(self):
        """Demonstrate Python's Protocol uses structural subtyping (duck typing)."""
        # This is how Protocol works - it checks structure, not inheritance!

        # ConversionHelpersMixin does NOT inherit from ConversionOperations
        assert ConversionOperations not in ConversionHelpersMixin.__bases__, (
            "ConversionHelpersMixin should NOT inherit from ConversionOperations - "
            "it satisfies it structurally!"
        )

        # But it still satisfies the protocol structurally
        # (MyPy verifies this at type-check time)
        assert hasattr(ConversionHelpersMixin, "_to_domain_model")
        assert hasattr(ConversionHelpersMixin, "_from_domain_model")
        # ... etc

    def test_example_of_what_mypy_catches(self):
        """
        Example of what MyPy would catch if signatures diverge.

        If ConversionHelpersMixin._to_domain_model signature was:
            def _to_domain_model(self, data: str) -> T:  # Wrong signature!

        But ConversionOperations.to_domain_model signature is:
            def _to_domain_model(self, dto: Any) -> T:  # Correct signature

        Then the TYPE_CHECKING block would fail:
            error: Incompatible types in assignment (expression has type
            "Type[ConversionHelpersMixin]", variable has type
            "Type[ConversionOperations[Any]]")

        This prevents the codebase from having mismatched signatures!
        """
        # This test just documents the behavior - actual verification is in MyPy
        pass
