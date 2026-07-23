"""Tests for the registry-chokepoint template override (ADR-082 D1).

Every PROMPT_REGISTRY template id resolves an optional founder-local
``data/instructions/{template_id}.md`` BEFORE the committed template: silent
miss when absent, blank/whitespace degrades to the committed floor, traversal
is contained, and overrides are read fresh on every access (never cached) so
founder edits land without a restart. Also pins the ``askesis_stance``
committed floor (ADR-082 D1/D3) — present, non-blank, placeholder-free.
"""

from pathlib import Path

import pytest

from core.prompts import PROMPT_REGISTRY
from core.prompts import registry as registry_module
from core.prompts.registry import PromptRegistry
from core.utils.instruction_files import INSTRUCTIONS_DIR

COMMITTED_TEMPLATES_DIR = Path(registry_module.__file__).parent / "templates"


@pytest.fixture
def home(tmp_path: Path) -> tuple[PromptRegistry, Path]:
    """A registry with one committed template and an isolated overrides dir."""
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "greeting.md").write_text("Committed floor for {name}.", encoding="utf-8")
    overrides = tmp_path / "instructions"
    overrides.mkdir()
    return PromptRegistry(templates, overrides_dir=overrides), overrides


class TestOverrideResolution:
    def test_absent_override_serves_committed_floor(
        self, home: tuple[PromptRegistry, Path]
    ) -> None:
        registry, _ = home
        assert registry.render("greeting", name="Mike") == "Committed floor for Mike."

    def test_present_override_replaces_committed(self, home: tuple[PromptRegistry, Path]) -> None:
        registry, overrides = home
        (overrides / "greeting.md").write_text("Authored words for {name}.", encoding="utf-8")
        assert registry.render("greeting", name="Mike") == "Authored words for Mike."

    @pytest.mark.parametrize("blank", ["", "   \n\n\t  "])
    def test_blank_override_degrades_to_floor(
        self, home: tuple[PromptRegistry, Path], blank: str
    ) -> None:
        registry, overrides = home
        (overrides / "greeting.md").write_text(blank, encoding="utf-8")
        assert registry.render("greeting", name="Mike") == "Committed floor for Mike."

    def test_override_is_read_fresh_never_cached(self, home: tuple[PromptRegistry, Path]) -> None:
        registry, overrides = home
        override_file = overrides / "greeting.md"
        override_file.write_text("First words {name}.", encoding="utf-8")
        assert registry.render("greeting", name="M") == "First words M."
        override_file.write_text("Second words {name}.", encoding="utf-8")
        assert registry.render("greeting", name="M") == "Second words M."
        override_file.unlink()
        assert registry.render("greeting", name="M") == "Committed floor for M."

    def test_missing_committed_template_still_raises(
        self, home: tuple[PromptRegistry, Path]
    ) -> None:
        registry, _ = home
        with pytest.raises(FileNotFoundError):
            registry.get("no_such_template")

    def test_singleton_defaults_to_data_instructions(self) -> None:
        assert PROMPT_REGISTRY._overrides_dir == INSTRUCTIONS_DIR


class TestRenderContractGuard:
    """An override replaces the words, not the render contract.

    ``str.format`` ignores extra kwargs, so an override that drops a committed
    placeholder would silently lose the context the caller computed — such an
    override degrades to the committed floor (with a warning), as does one
    that adds unknown placeholders (KeyError at render) or is not a valid
    format string at all.
    """

    def test_override_missing_a_placeholder_degrades_to_floor(
        self, home: tuple[PromptRegistry, Path]
    ) -> None:
        registry, overrides = home
        (overrides / "greeting.md").write_text("Authored words, no slot.", encoding="utf-8")
        assert registry.render("greeting", name="Mike") == "Committed floor for Mike."

    def test_override_adding_a_placeholder_degrades_to_floor(
        self, home: tuple[PromptRegistry, Path]
    ) -> None:
        registry, overrides = home
        (overrides / "greeting.md").write_text("Words for {name} and {extra}.", encoding="utf-8")
        assert registry.render("greeting", name="Mike") == "Committed floor for Mike."

    def test_malformed_override_degrades_to_floor(self, home: tuple[PromptRegistry, Path]) -> None:
        registry, overrides = home
        (overrides / "greeting.md").write_text("Stray { brace for {name}.", encoding="utf-8")
        assert registry.render("greeting", name="Mike") == "Committed floor for Mike."

    def test_override_reordering_and_repeating_placeholders_serves(
        self, home: tuple[PromptRegistry, Path]
    ) -> None:
        registry, overrides = home
        (overrides / "greeting.md").write_text("{name}, yes {name}.", encoding="utf-8")
        assert registry.render("greeting", name="Mike") == "Mike, yes Mike."

    def test_placeholder_free_floor_rejects_placeholder_override(self, tmp_path: Path) -> None:
        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "stance.md").write_text("Plain committed stance.", encoding="utf-8")
        overrides = tmp_path / "instructions"
        overrides.mkdir()
        (overrides / "stance.md").write_text("Authored {surprise}.", encoding="utf-8")
        registry = PromptRegistry(templates, overrides_dir=overrides)
        assert registry.render("stance") == "Plain committed stance."


class TestTraversalContainment:
    def test_traversal_id_cannot_escape_overrides_dir(self, tmp_path: Path) -> None:
        """A traversal template id never reads outside the overrides dir."""
        templates = tmp_path / "tpl"
        templates.mkdir()
        overrides_parent = tmp_path / "ovr"
        overrides = overrides_parent / "inner"
        overrides.mkdir(parents=True)
        (overrides_parent / "evil.md").write_text("escaped content", encoding="utf-8")
        registry = PromptRegistry(templates, overrides_dir=overrides)

        with pytest.raises(FileNotFoundError):
            registry.get("../evil")


class TestFloorCoverage:
    """The committed floors serve with an empty overrides dir — for every template."""

    def test_every_committed_template_loads_non_blank(self, tmp_path: Path) -> None:
        registry = PromptRegistry(COMMITTED_TEMPLATES_DIR, overrides_dir=tmp_path)
        template_files = sorted(COMMITTED_TEMPLATES_DIR.glob("*.md"))
        assert template_files
        for path in template_files:
            assert registry.get(path.stem).content.strip(), path.stem

    def test_stance_floor_is_placeholder_free(self, tmp_path: Path) -> None:
        """askesis_stance renders with no kwargs — no {placeholder} keys, ever."""
        registry = PromptRegistry(COMMITTED_TEMPLATES_DIR, overrides_dir=tmp_path)
        rendered = registry.render("askesis_stance")
        assert rendered == registry.get("askesis_stance").content
        assert "Askesis" in rendered

    def test_stance_floor_carries_the_contract(self, tmp_path: Path) -> None:
        """Study-buddy direction + expertise posture + citation discipline (ADR-082 D1)."""
        registry = PromptRegistry(COMMITTED_TEMPLATES_DIR, overrides_dir=tmp_path)
        stance = registry.render("askesis_stance").lower()
        assert "life path" in stance
        assert "learning path" in stance
        assert "cite" in stance
