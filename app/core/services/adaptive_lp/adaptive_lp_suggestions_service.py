"""
Adaptive Learning Path Suggestions Service
==========================================

Handles personalized application suggestions for existing knowledge.

Focuses on:
- Practice suggestions
- Project suggestions
- Teaching suggestions
- Career application suggestions
"""

from collections import defaultdict
from operator import attrgetter
from typing import Any

# Import dataclasses from shared models module (breaks circular dependency)
from core.services.adaptive_lp.adaptive_lp_models import LearningStyle, PersonalizedSuggestion
from core.services.adaptive_lp_types import KnowledgeState
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator


class AdaptiveLpSuggestionsService:
    """
    Service for generating personalized knowledge application suggestions.

    Focuses on:
    - Practice suggestions tailored to learning style
    - Project ideas combining multiple knowledge units
    - Teaching opportunities for mastered knowledge
    - Career application suggestions


    Source Tag: "adaptive_lp_suggestions_service_explicit"
    - Format: "adaptive_lp_suggestions_service_explicit" for user-created relationships
    - Format: "adaptive_lp_suggestions_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from adaptive_lp_suggestions metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self) -> None:
        """Initialize the suggestions service."""
        self.logger = get_logger("skuel.adaptive_lp_suggestions")

    @with_error_handling(error_type="system", uid_param="user_uid")
    async def generate_personalized_application_suggestions(
        self,
        user_uid: str,
        knowledge_state: KnowledgeState,
        learning_style: LearningStyle,
        context: dict[str, Any] | None = None,
    ) -> Result[list[PersonalizedSuggestion]]:
        """
        Generate personalized suggestions for applying existing knowledge.

        Args:
            user_uid: User to generate suggestions for,
            knowledge_state: Current knowledge state analysis,
            learning_style: User's detected learning style,
            context: Additional context for personalization

        Returns:
            Result containing list of PersonalizedSuggestion objects
        """
        applied_knowledge = knowledge_state.applied_knowledge
        mastery_levels = knowledge_state.mastery_levels

        if not applied_knowledge:
            return Result.ok([])

        suggestions = []

        # Generate different types of application suggestions
        practice_suggestions = await self._generate_practice_suggestions(
            applied_knowledge, mastery_levels, learning_style, user_uid
        )
        suggestions.extend(practice_suggestions)

        project_suggestions = await self._generate_project_suggestions(
            applied_knowledge, knowledge_state, user_uid
        )
        suggestions.extend(project_suggestions)

        teaching_suggestions = await self._generate_teaching_suggestions(
            applied_knowledge, mastery_levels, user_uid
        )
        suggestions.extend(teaching_suggestions)

        career_suggestions = await self._generate_career_application_suggestions(
            applied_knowledge, user_uid, context
        )
        suggestions.extend(career_suggestions)

        # Score and personalize suggestions
        personalized_suggestions = await self._personalize_and_score_suggestions(
            suggestions, user_uid, knowledge_state, learning_style
        )

        self.logger.info(
            f"Generated {len(personalized_suggestions)} personalized application suggestions "
            f"for user {user_uid}"
        )

        return Result.ok(personalized_suggestions[:15])  # Return top 15

    async def _generate_practice_suggestions(
        self,
        applied_knowledge: set[str],
        mastery_levels: dict[str, float],
        learning_style: LearningStyle,
        _user_uid: str,
    ) -> list[PersonalizedSuggestion]:
        """Generate suggestions for practicing existing knowledge."""
        suggestions = []

        for ku_uid in applied_knowledge:
            mastery = mastery_levels.get(ku_uid, 0.5)

            # Focus on knowledge with room for improvement
            if mastery < 0.8:
                domain = ku_uid.split(".")[1] if "." in ku_uid else "general"
                topic = ku_uid.split(".")[-1] if "." in ku_uid else ku_uid

                # Tailor practice to learning style
                if learning_style == LearningStyle.PRACTICAL:
                    practice_activities = [
                        f"Build small projects using {topic}",
                        f"Solve real-world problems with {topic}",
                        f"Create a portfolio piece showcasing {topic}",
                    ]
                elif learning_style == LearningStyle.THEORETICAL:
                    practice_activities = [
                        f"Study advanced concepts in {topic}",
                        f"Research best practices for {topic}",
                        f"Analyze case studies using {topic}",
                    ]
                else:
                    practice_activities = [
                        f"Practice {topic} through exercises",
                        f"Join {topic} communities and discussions",
                        f"Find mentorship opportunities in {topic}",
                    ]

                suggestion = PersonalizedSuggestion(
                    suggestion_id=UIDGenerator.generate_random_uid("practice"),
                    title=f"Strengthen {topic.title()} Skills",
                    description=f"Improve your {topic} proficiency through targeted practice",
                    knowledge_to_apply=[ku_uid],
                    application_context=f"Skill improvement in {domain}",
                    expected_outcomes=[
                        f"Increased {topic} proficiency",
                        f"Better {topic} problem-solving abilities",
                        f"More confidence applying {topic}",
                    ],
                    personalization_factors={
                        "current_mastery": mastery,
                        "learning_style": learning_style.value,
                        "improvement_potential": 1.0 - mastery,
                    },
                    user_readiness_score=0.9,  # High readiness for practice
                    timing_appropriateness=0.8,
                    concrete_steps=practice_activities,
                    resources_needed=[
                        f"{topic.title()} practice materials",
                        "Time for regular practice sessions",
                        f"Access to {topic} development environment",
                    ],
                    time_investment=60,  # 1 hour practice session
                    success_indicators=[
                        f"Completed {topic} practice exercises",
                        f"Built working {topic} examples",
                        f"Improved {topic} skill assessment scores",
                    ],
                    priority_score=1.0 - mastery,  # Higher priority for lower mastery
                )
                suggestions.append(suggestion)

        return suggestions[:5]  # Limit practice suggestions

    async def _generate_project_suggestions(
        self, applied_knowledge: set[str], _knowledge_state: KnowledgeState, _user_uid: str
    ) -> list[PersonalizedSuggestion]:
        """Generate suggestions for knowledge application through projects."""
        suggestions = []

        # Group knowledge by domain
        domain_knowledge = defaultdict(list)
        for ku_uid in applied_knowledge:
            if "." in ku_uid:
                domain = ku_uid.split(".")[1]
                domain_knowledge[domain].append(ku_uid)

        # Generate project suggestions for each domain
        for domain, knowledge_list in domain_knowledge.items():
            if len(knowledge_list) >= 2:  # Need multiple knowledge units for project
                project_idea = await self._create_domain_project_idea(domain, knowledge_list)

                if project_idea:
                    suggestion = PersonalizedSuggestion(
                        suggestion_id=UIDGenerator.generate_random_uid("project"),
                        title=project_idea["title"],
                        description=project_idea["description"],
                        knowledge_to_apply=knowledge_list,
                        application_context=f"{domain.title()} project development",
                        expected_outcomes=project_idea["outcomes"],
                        personalization_factors={
                            "domain_focus": domain,
                            "knowledge_integration": len(knowledge_list),
                            "project_complexity": project_idea["complexity"],
                        },
                        user_readiness_score=0.7,  # Projects require more preparation
                        timing_appropriateness=0.6,
                        concrete_steps=project_idea["steps"],
                        resources_needed=project_idea["resources"],
                        time_investment=project_idea["time_hours"] * 60,
                        success_indicators=project_idea["success_indicators"],
                        priority_score=len(knowledge_list)
                        * 0.1,  # Priority based on knowledge integration
                    )
                    suggestions.append(suggestion)

        return suggestions

    async def _create_domain_project_idea(
        self, domain: str, _knowledge_list: list[str]
    ) -> dict[str, Any] | None:
        """Create a project idea for a specific domain."""
        project_templates = {
            "programming": {
                "title": "Personal Automation Tool",
                "description": "Build a tool that automates repetitive tasks in your daily workflow",
                "outcomes": [
                    "A working automation tool",
                    "Improved programming project management skills",
                    "Portfolio piece demonstrating programming proficiency",
                ],
                "steps": [
                    "Identify repetitive tasks to automate",
                    "Design the tool architecture",
                    "Implement core functionality",
                    "Test and refine the tool",
                    "Document and share your work",
                ],
                "resources": [
                    "Programming development environment",
                    "Version control system (Git)",
                    "Testing framework",
                    "Documentation tools",
                ],
                "time_hours": 20,
                "complexity": 6,
                "success_indicators": [
                    "Tool successfully automates target tasks",
                    "Code is well-organized and documented",
                    "Tool can be shared and used by others",
                ],
            },
            "web": {
                "title": "Interactive Web Portfolio",
                "description": "Create a personal portfolio website showcasing your skills and projects",
                "outcomes": [
                    "Professional web presence",
                    "Demonstration of web development skills",
                    "Platform for showcasing future projects",
                ],
                "steps": [
                    "Plan portfolio content and structure",
                    "Design responsive layout and user interface",
                    "Implement interactive features",
                    "Optimize for performance and accessibility",
                    "Deploy and maintain the portfolio",
                ],
                "resources": [
                    "Web development tools and editors",
                    "Hosting platform",
                    "Design assets and content",
                    "Domain name (optional)",
                ],
                "time_hours": 15,
                "complexity": 5,
                "success_indicators": [
                    "Portfolio is live and accessible",
                    "Site is responsive across devices",
                    "Interactive features work smoothly",
                ],
            },
            "data": {
                "title": "Personal Data Analytics Dashboard",
                "description": "Analyze and visualize data from your personal activities or interests",
                "outcomes": [
                    "Insights into personal patterns and trends",
                    "Data analysis and visualization skills",
                    "Understanding of data-driven decision making",
                ],
                "steps": [
                    "Identify interesting personal data sources",
                    "Collect and clean the data",
                    "Perform exploratory data analysis",
                    "Create visualizations and insights",
                    "Build an interactive dashboard",
                ],
                "resources": [
                    "Data analysis tools (Python, R, Excel)",
                    "Visualization libraries",
                    "Data sources (APIs, exports, logs)",
                    "Dashboard platform",
                ],
                "time_hours": 25,
                "complexity": 7,
                "success_indicators": [
                    "Dashboard shows meaningful insights",
                    "Visualizations are clear and informative",
                    "Analysis leads to actionable conclusions",
                ],
            },
        }

        return project_templates.get(domain)

    async def _generate_teaching_suggestions(
        self, applied_knowledge: set[str], mastery_levels: dict[str, float], _user_uid: str
    ) -> list[PersonalizedSuggestion]:
        """Generate suggestions for teaching or sharing knowledge."""
        suggestions = []

        # Focus on knowledge with higher mastery for teaching
        high_mastery_knowledge = [
            ku_uid for ku_uid in applied_knowledge if mastery_levels.get(ku_uid, 0.5) >= 0.7
        ]

        for ku_uid in high_mastery_knowledge[:3]:  # Limit teaching suggestions
            topic = ku_uid.split(".")[-1] if "." in ku_uid else ku_uid

            suggestion = PersonalizedSuggestion(
                suggestion_id=UIDGenerator.generate_random_uid("teaching"),
                title=f"Teach {topic.title()} to Others",
                description=f"Share your {topic} knowledge through teaching or mentoring",
                knowledge_to_apply=[ku_uid],
                application_context="Knowledge sharing and teaching",
                expected_outcomes=[
                    f"Deeper understanding of {topic}",
                    "Improved communication and teaching skills",
                    "Contribution to the learning community",
                ],
                personalization_factors={
                    "mastery_level": mastery_levels.get(ku_uid, 0.5),
                    "teaching_potential": True,
                    "community_impact": True,
                },
                user_readiness_score=mastery_levels.get(ku_uid, 0.5),
                timing_appropriateness=0.7,
                concrete_steps=[
                    f"Write a blog post or tutorial about {topic}",
                    f"Mentor someone learning {topic}",
                    f"Create educational content (videos, guides) for {topic}",
                    f"Answer questions about {topic} in online communities",
                    f"Give a presentation or workshop on {topic}",
                ],
                resources_needed=[
                    "Platform for sharing content (blog, video, etc.)",
                    "Time for content creation",
                    "Community or audience to teach",
                ],
                time_investment=120,  # 2 hours for content creation
                success_indicators=[
                    f"Published {topic} educational content",
                    f"Helped others learn {topic}",
                    "Received positive feedback on teaching",
                ],
                priority_score=mastery_levels.get(ku_uid, 0.5) * 0.8,  # Priority based on mastery
            )
            suggestions.append(suggestion)

        return suggestions

    async def _generate_career_application_suggestions(
        self, applied_knowledge: set[str], _user_uid: str, _context: dict[str, Any] | None
    ) -> list[PersonalizedSuggestion]:
        """Generate suggestions for applying knowledge in career contexts."""
        suggestions = []

        # Group knowledge by domain for career opportunities
        domain_knowledge = defaultdict(list)
        for ku_uid in applied_knowledge:
            if "." in ku_uid:
                domain = ku_uid.split(".")[1]
                domain_knowledge[domain].append(ku_uid)

        # Generate career application suggestions
        career_opportunities = {
            "programming": {
                "roles": ["Software Developer", "Backend Engineer", "Full-Stack Developer"],
                "applications": [
                    "Contribute to open source projects",
                    "Build and deploy personal applications",
                    "Participate in coding challenges and hackathons",
                ],
            },
            "web": {
                "roles": ["Frontend Developer", "Web Designer", "UI/UX Developer"],
                "applications": [
                    "Create responsive websites for local businesses",
                    "Freelance web development projects",
                    "Build web applications for personal use",
                ],
            },
            "data": {
                "roles": ["Data Analyst", "Business Intelligence Developer", "Data Scientist"],
                "applications": [
                    "Analyze public datasets and share insights",
                    "Build data dashboards for organizations",
                    "Participate in data science competitions",
                ],
            },
        }

        for domain, knowledge_list in domain_knowledge.items():
            if domain in career_opportunities and len(knowledge_list) >= 2:
                career_info = career_opportunities[domain]

                suggestion = PersonalizedSuggestion(
                    suggestion_id=UIDGenerator.generate_random_uid("career"),
                    title=f"Apply {domain.title()} Skills Professionally",
                    description=f"Leverage your {domain} knowledge in professional contexts",
                    knowledge_to_apply=knowledge_list,
                    application_context=f"Professional {domain} development",
                    expected_outcomes=[
                        f"Professional experience in {domain}",
                        "Career advancement opportunities",
                        "Industry connections and networking",
                    ],
                    personalization_factors={
                        "career_domain": domain,
                        "professional_readiness": len(knowledge_list) / 5.0,
                        "market_demand": 0.8,  # Assume high demand for tech skills
                    },
                    user_readiness_score=len(knowledge_list)
                    / 5.0,  # Readiness based on knowledge breadth
                    timing_appropriateness=0.6,
                    concrete_steps=career_info["applications"]
                    + [
                        f"Update resume to highlight {domain} skills",
                        f"Build a portfolio showcasing {domain} projects",
                        f"Network with {domain} professionals",
                    ],
                    resources_needed=[
                        "Professional portfolio or resume",
                        "Networking opportunities",
                        "Time for professional development",
                    ],
                    time_investment=180,  # 3 hours for career development activities
                    success_indicators=[
                        f"Completed professional {domain} projects",
                        f"Gained recognition for {domain} skills",
                        f"Advanced career opportunities in {domain}",
                    ],
                    priority_score=len(knowledge_list) * 0.15,  # Priority based on domain expertise
                )
                suggestions.append(suggestion)

        return suggestions

    async def _personalize_and_score_suggestions(
        self,
        suggestions: list[PersonalizedSuggestion],
        _user_uid: str,
        _knowledge_state: KnowledgeState,
        learning_style: LearningStyle,
    ) -> list[PersonalizedSuggestion]:
        """Personalize and score suggestions based on user context."""
        for suggestion in suggestions:
            # Adjust scores based on learning style
            style_multiplier = 1.0
            if learning_style == LearningStyle.PRACTICAL:
                if "project" in suggestion.suggestion_id or "practice" in suggestion.suggestion_id:
                    style_multiplier = 1.2
                elif "teaching" in suggestion.suggestion_id:
                    style_multiplier = 0.8
            elif learning_style == LearningStyle.SOCIAL:
                if "teaching" in suggestion.suggestion_id:
                    style_multiplier = 1.3
                elif "project" in suggestion.suggestion_id:
                    style_multiplier = 0.9

            # Apply style adjustment
            suggestion.user_readiness_score *= style_multiplier
            suggestion.timing_appropriateness *= style_multiplier

            # Calculate final priority score
            suggestion.priority_score = (
                suggestion.user_readiness_score * 0.4
                + suggestion.timing_appropriateness * 0.3
                + suggestion.priority_score * 0.3
            )

        # Sort by priority score
        suggestions.sort(key=attrgetter("priority_score"), reverse=True)

        return suggestions
