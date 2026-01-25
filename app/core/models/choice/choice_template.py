"""
Choice Template System
======================

Provides pre-designed inspirational choice templates that guide users through
common life decisions with full curriculum backing.

This is SKUEL's differentiation: Other platforms say "here are courses, pick one."
SKUEL says "here are life possibilities, let's explore what each path offers,
then you choose based on your values and interests."

Templates are loaded from YAML files and converted into Choice domain models.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.models.choice.choice import Choice, ChoiceOption, ChoiceStatus, ChoiceType
from core.models.shared_enums import Domain, Priority
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChoiceOptionTemplate:
    """Template for a choice option with curriculum links."""

    title: str
    description: str
    opens_learning_paths: list[str]
    informed_by_knowledge_uids: list[str]
    feasibility_score: float = 0.7
    risk_level: float = 0.3
    potential_impact: float = 0.7
    resource_requirement: float = 0.5
    estimated_duration: int | None = None  # Hours,
    tags: list[str] = None

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []


@dataclass
class ChoiceTemplate:
    """
    Template for an inspirational choice.

    Templates guide users through major life decisions by presenting
    possibilities with full curriculum backing.
    """

    # Identity
    template_id: str  # e.g., "career-web-vs-data"
    title: str
    description: str

    # Inspiration Configuration
    inspiration_type: str  # 'career_path', 'life_direction', 'skill_acquisition', 'project_idea'
    expands_possibilities: bool = True
    vision_statement: str | None = None

    # Options (each opens different learning paths)
    options: list[ChoiceOptionTemplate] = None

    # Context
    decision_criteria: list[str] = (None,)

    constraints: list[str] = None

    # Curriculum Integration
    requires_knowledge_for_decision: list[str] = (None,)

    aligned_with_principles: list[str] = None

    # Metadata
    choice_type: ChoiceType = ChoiceType.MULTIPLE
    domain: Domain = Domain.PERSONAL
    priority: Priority = Priority.HIGH
    tags: list[str] = None

    # Template Metadata
    template_version: str = "1.0"
    created_by: str = "SKUEL"
    category: str = "general"  # 'career', 'education', 'lifestyle', 'skills'

    def __post_init__(self) -> None:
        """Initialize empty lists."""
        if self.options is None:
            self.options = []
        if self.decision_criteria is None:
            self.decision_criteria = []
        if self.constraints is None:
            self.constraints = []
        if self.requires_knowledge_for_decision is None:
            self.requires_knowledge_for_decision = []
        if self.aligned_with_principles is None:
            self.aligned_with_principles = []
        if self.tags is None:
            self.tags = []

    def to_choice(self, user_uid: str, uid_prefix: str = "choice") -> Choice:
        """
        Convert template to actual Choice domain model for a user.

        Args:
            user_uid: UID of the user making the choice
            uid_prefix: Prefix for generated UIDs

        Returns:
            Choice domain model instance
        """
        import uuid
        from datetime import datetime

        # Generate UIDs for options
        choice_options = []
        for _idx, opt_template in enumerate(self.options):
            option_uid = f"opt_{uuid.uuid4().hex[:12]}"
            choice_option = ChoiceOption(
                uid=option_uid,
                title=opt_template.title,
                description=opt_template.description,
                feasibility_score=opt_template.feasibility_score,
                risk_level=opt_template.risk_level,
                potential_impact=opt_template.potential_impact,
                resource_requirement=opt_template.resource_requirement,
                estimated_duration=opt_template.estimated_duration,
                dependencies=(),
                tags=tuple(opt_template.tags),
            )
            choice_options.append(choice_option)

        # Create Choice
        choice_uid = f"{uid_prefix}_{uuid.uuid4().hex[:12]}"

        return Choice(
            uid=choice_uid,
            title=self.title,
            description=self.description,
            user_uid=user_uid,
            choice_type=self.choice_type,
            status=ChoiceStatus.PENDING,
            priority=self.priority,
            domain=self.domain,
            options=tuple(choice_options),
            selected_option_uid=None,
            decision_rationale=None,
            decision_criteria=tuple(self.decision_criteria),
            constraints=tuple(self.constraints),
            stakeholders=(),
            # Curriculum Integration - REMOVED: These are Neo4j graph relationships, not Choice fields
            # informed_by_knowledge_uids, opens_learning_paths, requires_knowledge_for_decision, aligned_with_principles
            # are stored as graph edges and should be created via ChoiceService relationship methods
            # Inspiration
            inspiration_type=self.inspiration_type,
            expands_possibilities=self.expands_possibilities,
            vision_statement=self.vision_statement,
            # Timing
            decision_deadline=None,
            created_at=datetime.now(),
            decided_at=None,
            # Outcome
            satisfaction_score=None,
            actual_outcome=None,
            lessons_learned=(),
        )

    def _collect_all_learning_paths(self) -> tuple[str, ...]:
        """Collect all unique learning paths from all options."""
        all_paths = set()
        for option in self.options:
            all_paths.update(option.opens_learning_paths)
        return tuple(all_paths)

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "ChoiceTemplate":
        """
        Load choice template from YAML file.

        Args:
            yaml_path: Path to YAML template file

        Returns:
            ChoiceTemplate instance

        Expected YAML structure:
        ```yaml
        template_id: career-web-vs-data
        title: "Web Development or Data Science?"
        description: "Choose your tech career path"
        inspiration_type: career_path
        vision_statement: "Build your future in tech"
        options:
          - title: "Web Development"
            description: "Build interactive websites and applications"
            opens_learning_paths:
              - lp:web-dev-foundations
              - lp:frontend-mastery
            informed_by_knowledge_uids:
              - ku:html-basics
              - ku:javascript-intro
            estimated_duration: 500

          - title: "Data Science"
            description: "Analyze data and build ML models"
            opens_learning_paths:
              - lp:python-data-analysis
              - lp:ml-fundamentals
            informed_by_knowledge_uids:
              - ku:python-basics
              - ku:statistics-intro
            estimated_duration: 600

        decision_criteria:
          - "Do you prefer visual/interactive work or analytical work?"
          - "Are you more interested in user experience or data insights?"

        requires_knowledge_for_decision:
          - ku:programming-overview
          - ku:career-paths-tech

        aligned_with_principles:
          - principle:continuous-learning
          - principle:skill-mastery
        ```
        """
        with yaml_path.open("r") as f:
            data = yaml.safe_load(f)

        # Convert option dicts to ChoiceOptionTemplate objects
        options = []
        for opt_data in data.get("options", []):
            option = ChoiceOptionTemplate(
                title=opt_data["title"],
                description=opt_data["description"],
                opens_learning_paths=opt_data.get("opens_learning_paths", []),
                informed_by_knowledge_uids=opt_data.get("informed_by_knowledge_uids", []),
                feasibility_score=opt_data.get("feasibility_score", 0.7),
                risk_level=opt_data.get("risk_level", 0.3),
                potential_impact=opt_data.get("potential_impact", 0.7),
                resource_requirement=opt_data.get("resource_requirement", 0.5),
                estimated_duration=opt_data.get("estimated_duration"),
                tags=opt_data.get("tags", []),
            )
            options.append(option)

        # Convert enums
        choice_type = ChoiceType(data.get("choice_type", "multiple"))
        domain = Domain(data.get("domain", "personal"))
        priority = Priority(data.get("priority", "high"))

        return cls(
            template_id=data["template_id"],
            title=data["title"],
            description=data["description"],
            inspiration_type=data.get("inspiration_type", "career_path"),
            expands_possibilities=data.get("expands_possibilities", True),
            vision_statement=data.get("vision_statement"),
            options=options,
            decision_criteria=data.get("decision_criteria", []),
            constraints=data.get("constraints", []),
            requires_knowledge_for_decision=data.get("requires_knowledge_for_decision", []),
            aligned_with_principles=data.get("aligned_with_principles", []),
            choice_type=choice_type,
            domain=domain,
            priority=priority,
            tags=data.get("tags", []),
            template_version=data.get("template_version", "1.0"),
            created_by=data.get("created_by", "SKUEL"),
            category=data.get("category", "general"),
        )


class ChoiceTemplateLibrary:
    """
    Manager for choice template collection.

    Loads and manages pre-designed choice templates for users.
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        """
        Initialize template library.

        Args:
            templates_dir: Directory containing YAML templates
        """
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"

        self.templates_dir = Path(templates_dir)
        self._templates: dict[str, ChoiceTemplate] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        """Load all YAML templates from templates directory."""
        if not self.templates_dir.exists():
            return

        for yaml_file in self.templates_dir.glob("*.yaml"):
            try:
                template = ChoiceTemplate.from_yaml(yaml_file)
                self._templates[template.template_id] = template
            except Exception as e:
                logger.error("Failed to load template", file=str(yaml_file), error=str(e))

    def get_template(self, template_id: str) -> ChoiceTemplate | None:
        """Get template by ID."""
        return self._templates.get(template_id)

    def list_templates(self, category: str | None = None) -> list[ChoiceTemplate]:
        """
        List available templates, optionally filtered by category.

        Args:
            category: Optional category filter ('career', 'education', 'lifestyle', 'skills')

        Returns:
            List of matching templates
        """
        templates = list(self._templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return templates

    def list_categories(self) -> list[str]:
        """Get all unique template categories."""
        return list(set(t.category for t in self._templates.values()))

    def create_choice_from_template(self, template_id: str, user_uid: str) -> Choice | None:
        """
        Create a Choice instance for a user from a template.

        Args:
            template_id: ID of template to use,
            user_uid: UID of user making choice

        Returns:
            Choice instance, or None if template not found
        """
        template = self.get_template(template_id)
        if not template:
            return None

        return template.to_choice(user_uid)
