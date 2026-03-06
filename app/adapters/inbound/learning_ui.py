"""
Learning UI Components
======================

Component-based UI routes for learning management.
All pages use BasePage for consistent layout.
"""

from typing import Any

from fasthtml.common import (
    H1,
    H2,
    H3,
    H4,
    H5,
    Div,
    Header,
    Li,
    Option,
    P,
    Span,
    Ul,
)

from core.models.curriculum.curriculum_requests import LearningPathFilterRequest
from core.utils.logging import get_logger
from core.utils.uid_generator import UIDGenerator
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.forms import Label, Select
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.form_generator import FormGenerator
from ui.patterns.relationships import EntityRelationshipsSection
from ui.ui_types import (
    AchievementData,
    ActivePathData,
    LearningPathDetail,
    LearningStatsData,
    LessonData,
    ModuleData,
    UserLearningOverview,
)

logger = get_logger("skuel.ui.learning")


class LearningUIComponents:
    """Reusable component library for learning management interface."""

    @staticmethod
    def render_filter_form() -> Any:
        """Learning path filter form using FormGenerator with custom select widgets."""
        return FormGenerator.from_model(
            LearningPathFilterRequest,
            action="/api/learning/filter-paths",
            method="POST",
            include_fields=["difficulty", "domain", "duration"],
            custom_widgets={
                "difficulty": Div(
                    Label("Difficulty Level", cls="label"),
                    Select(
                        Option("All Levels", value="all", selected=True),
                        Option("Beginner", value="beginner"),
                        Option("Intermediate", value="intermediate"),
                        Option("Advanced", value="advanced"),
                        name="difficulty",
                        cls="select select-bordered w-full",
                    ),
                    cls="form-control",
                ),
                "domain": Div(
                    Label("Domain", cls="label"),
                    Select(
                        Option("All Domains", value="all", selected=True),
                        Option("Programming", value="programming"),
                        Option("Data Science", value="data_science"),
                        Option("Web Development", value="web_dev"),
                        Option("Cloud Computing", value="cloud"),
                        name="domain",
                        cls="select select-bordered w-full",
                    ),
                    cls="form-control",
                ),
                "duration": Div(
                    Label("Time Commitment", cls="label"),
                    Select(
                        Option("Any Duration", value="all", selected=True),
                        Option("Under 20 hours", value="short"),
                        Option("20-50 hours", value="medium"),
                        Option("50+ hours", value="long"),
                        name="duration",
                        cls="select select-bordered w-full",
                    ),
                    cls="form-control",
                ),
            },
            form_attrs={
                "cls": "space-y-4",
                "hx_post": "/api/learning/filter-paths",
                "hx_target": "#learning-paths-grid",
            },
            submit_label="Apply Filters",
        )

    @staticmethod
    def render_learning_path_card(path: ActivePathData) -> Any:
        """Create a learning path card for the dashboard."""
        return Card(
            Div(
                # Path Header
                Div(
                    H3(path.title, cls="text-lg font-semibold"),
                    Span(path.difficulty.title(), cls="badge badge-primary"),
                    cls="flex justify-between items-start mb-2",
                ),
                # Progress Bar
                Div(
                    Div(f"{path.progress:.1f}% Complete", cls="text-sm text-base-content/70 mb-1"),
                    Div(
                        Div(
                            cls="h-2 bg-primary rounded-full transition-all",
                            style=f"width: {path.progress}%",
                        ),
                        cls="w-full bg-base-300 rounded-full h-2",
                    ),
                    cls="mb-3",
                ),
                # Current Step & Time
                Div(
                    P(f"Current: {path.current_step}", cls="text-sm text-base-content/80"),
                    P(f"⏱️ {path.time_invested} invested", cls="text-xs text-base-content/60"),
                    P(
                        f"📅 {path.estimated_completion} to complete",
                        cls="text-xs text-base-content/60",
                    ),
                    cls="space-y-1 mb-4",
                ),
                # Action Button
                Button(
                    "Continue Learning",
                    variant=ButtonT.primary,
                    cls="btn-sm w-full",
                    **{
                        "hx-get": f"/learning/path/{path.uid}/continue",
                        "hx-target": "#main-content",
                    },
                ),
                cls="p-4",
            ),
            cls="hover:shadow-lg transition-shadow",
        )

    @staticmethod
    def render_learning_path_browser_card(path) -> Any:
        """Create a learning path card for the browse page."""
        return Card(
            Div(
                # Path Header
                Div(
                    H3(path["title"], cls="text-lg font-semibold mb-2"),
                    P(path["description"], cls="text-sm text-base-content/70 mb-3"),
                    cls="mb-4",
                ),
                # Path Info
                Div(
                    Div(
                        Span(f"⭐ {path['rating']}", cls="text-sm mr-3"),
                        Span(f"👥 {path['learners']}", cls="text-sm mr-3"),
                        Span(f"⏱️ {path['estimated_hours']}h", cls="text-sm"),
                        cls="text-base-content/60 mb-2",
                    ),
                    Span(path["difficulty"].title(), cls="badge badge-primary mb-3"),
                    cls="mb-4",
                ),
                # Tags
                Div(
                    *[
                        Span(tag, cls="badge badge-outline badge-sm mr-1 mb-1")
                        for tag in path.get("tags", [])[:3]  # Show first 3 tags
                    ],
                    cls="mb-4",
                ),
                # Action Buttons
                Div(
                    Button(
                        "View Details",
                        variant=ButtonT.outline,
                        cls="btn-sm flex-1",
                        **{"hx-get": f"/learning/path/{path['uid']}", "hx-target": "#main-content"},
                    ),
                    Button(
                        "Enroll",
                        variant=ButtonT.primary,
                        cls="btn-sm flex-1",
                        **{
                            "hx-post": f"/api/learning/enroll/{path['uid']}",
                            "hx-target": "#main-content",
                        },
                    ),
                    cls="flex gap-2",
                ),
                cls="p-4",
            ),
            cls="hover:shadow-lg transition-shadow h-full",
        )

    @staticmethod
    def render_curriculum_module(module: ModuleData, index: int) -> Any:
        """Create a curriculum module component."""
        status_colors = {
            "completed": "badge-success",
            "in_progress": "badge-warning",
            "not_started": "badge-outline",
        }

        status_icons = {"completed": "✅", "in_progress": "🔄", "not_started": "⭕"}

        return Div(
            Div(
                # Module Header
                Div(
                    Span(f"Module {index}", cls="badge badge-primary mr-2"),
                    H4(module.title, cls="text-lg font-semibold"),
                    Span(
                        status_icons[module.status],
                        module.status.replace("_", " ").title(),
                        cls=f"badge {status_colors[module.status]}",
                    ),
                    cls="flex items-center justify-between mb-2",
                ),
                # Module Info
                Div(
                    P(module.description, cls="text-base-content/70 mb-2"),
                    P(
                        f"Estimated time: {module.estimated_time}",
                        cls="text-sm text-base-content/60",
                    ),
                    cls="mb-3",
                ),
                # Lessons
                Div(
                    H5("Lessons:", cls="font-medium text-sm mb-2"),
                    Div(
                        *[
                            Div(
                                Span("✅" if lesson.completed else "⭕", cls="mr-2"),
                                Span(lesson.title, cls="flex-1"),
                                Span(lesson.duration, cls="text-xs text-base-content/60 mr-2"),
                                Span(lesson.lesson_type, cls="badge badge-outline badge-xs"),
                                cls="flex items-center py-1",
                            )
                            for lesson in module.lessons
                        ],
                        cls="space-y-1",
                    ),
                    cls="ml-4",
                ),
                cls="p-4",
            ),
            cls="border border-base-300 rounded-lg hover:bg-base-100 transition-colors",
        )

    @staticmethod
    def render_achievement_item(achievement: AchievementData) -> Any:
        """Create an achievement display item."""
        type_icons = {"milestone": "🏆", "streak": "🔥", "mastery": "🎯", "collaboration": "🤝"}

        return Div(
            Span(type_icons.get(achievement.achievement_type, "🏅"), cls="text-xl mr-3"),
            Div(
                P(achievement.title, cls="font-medium"),
                P(achievement.description, cls="text-sm text-base-content/60"),
                cls="flex-1",
            ),
            cls="flex items-start p-3 bg-base-100 rounded-lg",
        )

    @staticmethod
    def render_insight_item(icon, title, description, priority) -> Any:
        """Create a learning insight display item."""
        priority_colors = {"high": "border-error", "medium": "border-warning", "low": "border-info"}

        return Div(
            Span(icon, cls="text-xl mr-3"),
            Div(
                P(title, cls="font-medium"),
                P(description, cls="text-sm text-base-content/60"),
                cls="flex-1",
            ),
            cls=f"flex items-start p-3 border-l-4 {priority_colors.get(priority, 'border-info')} bg-base-100 rounded-r-lg",
        )


def create_learning_ui_routes(_app, rt, _learning_service):
    """Create UI routes for learning management."""

    routes = []

    @rt("/learning")
    async def learning_dashboard(request) -> Any:
        """Main learning dashboard with progress overview and active paths."""

        # Sample data (replace with actual service calls) - using frozen dataclasses for type safety
        user_learning_overview = UserLearningOverview(
            user_uid="user_123",
            active_paths=[
                ActivePathData(
                    uid=UIDGenerator.generate_uid("learning_path", "python_fundamentals"),
                    title="Python Programming Fundamentals",
                    progress=67.5,
                    current_step="Data Structures",
                    estimated_completion="3 days",
                    difficulty="beginner",
                    time_invested="18.5 hours",
                ),
                ActivePathData(
                    uid=UIDGenerator.generate_uid("learning_path", "data_analysis"),
                    title="Data Analysis with Pandas",
                    progress=42.0,
                    current_step="Data Cleaning",
                    estimated_completion="1 week",
                    difficulty="intermediate",
                    time_invested="12.2 hours",
                ),
            ],
            recent_achievements=[
                AchievementData(
                    achievement_type="milestone",
                    title="Completed Python Basics",
                    description="95% mastery in fundamental concepts",
                    earned_at="2024-01-25T16:30:00Z",
                ),
                AchievementData(
                    achievement_type="streak",
                    title="7-Day Learning Streak",
                    description="Consistent daily practice",
                    earned_at="2024-01-26T20:00:00Z",
                ),
            ],
            learning_stats=LearningStatsData(
                total_hours=47.3,
                concepts_mastered=23,
                active_streak=7,
                completion_rate=0.87,
            ),
        )

        content = Div(
            # Header
            Header(
                H1("Learning Dashboard", cls="text-3xl font-bold text-primary"),
                P(
                    "Track your learning journey and discover new knowledge",
                    cls="text-lg text-base-content/70 mt-2",
                ),
                cls="mb-8",
            ),
            # Learning Stats Overview
            Card(
                H2("Learning Overview", cls="text-xl font-semibold mb-4"),
                Div(
                    # Stats Cards
                    Div(
                        Div(
                            Span("Learning Hours", cls="text-sm text-base-content/70"),
                            Span(
                                f"{user_learning_overview.learning_stats.total_hours}",
                                cls="text-2xl font-bold text-primary",
                            ),
                            P("Total time invested", cls="text-xs text-base-content/60"),
                            cls="stat text-center",
                        ),
                        Div(
                            Span("Concepts Mastered", cls="text-sm text-base-content/70"),
                            Span(
                                str(user_learning_overview.learning_stats.concepts_mastered),
                                cls="text-2xl font-bold text-success",
                            ),
                            P("Across all learning paths", cls="text-xs text-base-content/60"),
                            cls="stat text-center",
                        ),
                        Div(
                            Span("Learning Streak", cls="text-sm text-base-content/70"),
                            Span(
                                f"{user_learning_overview.learning_stats.active_streak} Days",
                                cls="text-2xl font-bold text-primary",
                            ),
                            P("Consistent practice", cls="text-xs text-base-content/60"),
                            cls="stat text-center",
                        ),
                        Div(
                            Span("Completion Rate", cls="text-sm text-base-content/70"),
                            Span(
                                f"{user_learning_overview.learning_stats.completion_rate * 100:.0f}%",
                                cls="text-2xl font-bold text-warning",
                            ),
                            P("Started paths finished", cls="text-xs text-base-content/60"),
                            cls="stat text-center",
                        ),
                        cls="stats stats-horizontal shadow w-full",
                    ),
                    cls="mb-6",
                ),
                cls="mb-8",
            ),
            # Active Learning Paths
            Card(
                Div(
                    H2("Active Learning Paths", cls="text-xl font-semibold mb-4"),
                    Button(
                        "📚 Browse Learning Paths",
                        variant=ButtonT.primary,
                        cls="btn-sm",
                        **{"hx-get": "/learning/browse", "hx-target": "#main-content"},
                    ),
                    cls="flex justify-between items-center mb-4",
                ),
                Div(
                    *[
                        LearningUIComponents.render_learning_path_card(path)
                        for path in user_learning_overview.active_paths
                    ],
                    cls="space-y-4",
                ),
                cls="mb-8",
            ),
            # Recent Achievements
            Card(
                H2("Recent Achievements", cls="text-xl font-semibold mb-4"),
                Div(
                    *[
                        LearningUIComponents.render_achievement_item(achievement)
                        for achievement in user_learning_overview.recent_achievements
                    ],
                    cls="space-y-3",
                ),
                cls="mb-8",
            ),
            # Quick Actions
            Card(
                H2("Quick Actions", cls="text-xl font-semibold mb-4"),
                Div(
                    Button(
                        "🎯 Continue Learning",
                        variant=ButtonT.primary,
                        **{"hx-get": "/learning/continue", "hx-target": "#main-content"},
                    ),
                    Button(
                        "📊 View Analytics",
                        variant=ButtonT.secondary,
                        **{"hx-get": "/learning/analytics", "hx-target": "#main-content"},
                    ),
                    Button(
                        "🎲 Discover New Topics",
                        variant=ButtonT.outline,
                        **{"hx-get": "/learning/discover", "hx-target": "#main-content"},
                    ),
                    Button(
                        "👥 Join Study Groups",
                        variant=ButtonT.outline,
                        **{"hx-get": "/learning/community", "hx-target": "#main-content"},
                    ),
                    cls="flex flex-wrap gap-3",
                ),
                cls="mb-8",
            ),
            cls="container mx-auto px-4 py-6",
        )

        return await BasePage(
            content=content,
            title="Learning Dashboard",
            page_type=PageType.STANDARD,
            request=request,
            active_page="learning",
        )

    routes.append(learning_dashboard)

    @rt("/learning/browse")
    async def browse_learning_paths(request) -> Any:
        """Browse available learning paths with filtering and recommendations."""

        # Sample learning paths data
        available_paths = [
            {
                "uid": UIDGenerator.generate_uid("path", "machine_learning"),
                "title": "Machine Learning Fundamentals",
                "description": "Learn the basics of machine learning algorithms and applications",
                "difficulty": "intermediate",
                "estimated_hours": 35,
                "rating": 4.7,
                "learners": 1247,
                "tags": ["python", "algorithms", "data_science"],
                "prerequisites": ["python_fundamentals", "statistics_basics"],
            },
            {
                "uid": UIDGenerator.generate_uid("path", "web_development"),
                "title": "Full-Stack Web Development",
                "description": "Complete guide to building modern web applications",
                "difficulty": "beginner",
                "estimated_hours": 60,
                "rating": 4.5,
                "learners": 2134,
                "tags": ["javascript", "html", "css", "react", "node"],
                "prerequisites": ["basic_programming"],
            },
            {
                "uid": UIDGenerator.generate_uid("path", "cloud_computing"),
                "title": "Cloud Computing with AWS",
                "description": "Master cloud infrastructure and deployment strategies",
                "difficulty": "advanced",
                "estimated_hours": 45,
                "rating": 4.6,
                "learners": 892,
                "tags": ["aws", "cloud", "devops", "infrastructure"],
                "prerequisites": ["linux_basics", "networking", "programming_experience"],
            },
        ]

        content = Div(
            # Header
            Header(
                H1("Browse Learning Paths", cls="text-3xl font-bold text-primary"),
                P(
                    "Discover structured learning paths to achieve your goals",
                    cls="text-lg text-base-content/70 mt-2",
                ),
                cls="mb-8",
            ),
            # Filters Section
            Card(
                H3("Filter Learning Paths", cls="text-lg font-semibold mb-4"),
                Div(
                    LearningUIComponents.render_filter_form(),
                    cls="grid grid-cols-1 md:grid-cols-3 gap-4",
                ),
                cls="mb-8",
            ),
            # Learning Paths Grid
            Div(
                Div(
                    *[
                        LearningUIComponents.render_learning_path_browser_card(path)
                        for path in available_paths
                    ],
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6",
                ),
                id="learning-paths-grid",
                cls="mb-8",
            ),
            cls="container mx-auto px-4 py-6",
        )

        return await BasePage(
            content=content,
            title="Browse Learning Paths",
            page_type=PageType.STANDARD,
            request=request,
            active_page="learning",
        )

    routes.append(browse_learning_paths)

    @rt("/learning/path/{path_uid}")
    async def learning_path_detail(request, path_uid: str) -> Any:
        """Detailed view of a specific learning path with curriculum and progress."""

        # Sample path detail data - using frozen dataclasses for type safety
        path_detail = LearningPathDetail(
            uid=path_uid,
            title="Python Programming Fundamentals",
            description="Master the basics of Python programming with hands-on projects and real-world applications",
            difficulty="beginner",
            estimated_hours=25,
            rating=4.8,
            learners=3247,
            progress=67.5,
            is_enrolled=True,
            curriculum=[
                ModuleData(
                    module_id="module_1",
                    title="Python Basics",
                    description="Variables, data types, and basic operations",
                    estimated_time="3 hours",
                    status="completed",
                    lessons=[
                        LessonData(
                            title="Introduction to Python",
                            duration="15 min",
                            lesson_type="video",
                            completed=True,
                        ),
                        LessonData(
                            title="Variables and Data Types",
                            duration="20 min",
                            lesson_type="interactive",
                            completed=True,
                        ),
                        LessonData(
                            title="Basic Operations",
                            duration="25 min",
                            lesson_type="hands_on",
                            completed=True,
                        ),
                    ],
                ),
                ModuleData(
                    module_id="module_2",
                    title="Control Structures",
                    description="If statements, loops, and functions",
                    estimated_time="4 hours",
                    status="completed",
                    lessons=[
                        LessonData(
                            title="Conditional Statements",
                            duration="30 min",
                            lesson_type="video",
                            completed=True,
                        ),
                        LessonData(
                            title="Loops and Iteration",
                            duration="35 min",
                            lesson_type="interactive",
                            completed=True,
                        ),
                        LessonData(
                            title="Functions and Scope",
                            duration="40 min",
                            lesson_type="hands_on",
                            completed=True,
                        ),
                    ],
                ),
                ModuleData(
                    module_id="module_3",
                    title="Data Structures",
                    description="Lists, dictionaries, and sets",
                    estimated_time="5 hours",
                    status="in_progress",
                    lessons=[
                        LessonData(
                            title="Working with Lists",
                            duration="30 min",
                            lesson_type="video",
                            completed=True,
                        ),
                        LessonData(
                            title="Dictionary Operations",
                            duration="35 min",
                            lesson_type="interactive",
                            completed=False,
                        ),
                        LessonData(
                            title="Sets and Advanced Operations",
                            duration="40 min",
                            lesson_type="hands_on",
                            completed=False,
                        ),
                    ],
                ),
            ],
            prerequisites=["basic_computer_skills"],
            learning_outcomes=[
                "Write Python scripts confidently",
                "Understand core programming concepts",
                "Debug and troubleshoot code",
                "Apply Python to solve real problems",
            ],
        )

        content = Div(
            # Header with Path Info
            Header(
                Div(
                    H1(path_detail.title, cls="text-3xl font-bold text-primary"),
                    P(path_detail.description, cls="text-lg text-base-content/70 mt-2"),
                    Div(
                        Span(f"⭐ {path_detail.rating}", cls="badge badge-warning mr-2"),
                        Span(f"👥 {path_detail.learners} learners", cls="badge badge-info mr-2"),
                        Span(
                            f"⏱️ {path_detail.estimated_hours} hours",
                            cls="badge badge-secondary mr-2",
                        ),
                        Span(f"📊 {path_detail.difficulty.title()}", cls="badge badge-primary"),
                        cls="flex flex-wrap gap-2 mt-4",
                    ),
                    cls="flex-1",
                ),
                Div(
                    # Progress Circle
                    Div(
                        Span(f"{path_detail.progress:.0f}%", cls="text-2xl font-bold"),
                        cls="radial-progress text-primary",
                        style=f"--value:{path_detail.progress}",
                    )
                    if path_detail.is_enrolled
                    else Button(
                        "Enroll Now",
                        variant=ButtonT.primary,
                        cls="btn-lg",
                        **{
                            "hx-post": f"/api/learning/enroll/{path_uid}",
                            "hx-target": "#main-content",
                        },
                    ),
                    cls="flex-shrink-0",
                ),
                cls="flex items-start justify-between mb-8",
            ),
            # Action Buttons
            Div(
                Button(
                    "🎯 Continue Learning",
                    variant=ButtonT.primary,
                    **{
                        "hx-get": f"/learning/path/{path_uid}/continue",
                        "hx-target": "#main-content",
                    },
                )
                if path_detail.is_enrolled
                else None,
                Button(
                    "📊 View Progress",
                    variant=ButtonT.secondary,
                    **{
                        "hx-get": f"/learning/path/{path_uid}/progress",
                        "hx-target": "#main-content",
                    },
                ),
                Button(
                    "💬 Discussion Forum",
                    variant=ButtonT.outline,
                    **{"hx-get": f"/learning/path/{path_uid}/forum", "hx-target": "#main-content"},
                ),
                cls="flex flex-wrap gap-3 mb-8",
            ),
            # Curriculum
            Card(
                H2("Curriculum", cls="text-xl font-semibold mb-4"),
                Div(
                    *[
                        LearningUIComponents.render_curriculum_module(module, index + 1)
                        for index, module in enumerate(path_detail.curriculum)
                    ],
                    cls="space-y-4",
                ),
                cls="mb-8",
            ),
            # Learning Outcomes & Prerequisites
            Div(
                Card(
                    H3("Learning Outcomes", cls="text-lg font-semibold mb-3"),
                    Ul(
                        *[
                            Li(Span("✅", cls="mr-2"), outcome, cls="flex items-start")
                            for outcome in path_detail.learning_outcomes
                        ],
                        cls="space-y-2",
                    ),
                    cls="h-fit",
                ),
                Card(
                    H3("Prerequisites", cls="text-lg font-semibold mb-3"),
                    Div(
                        *[
                            Span(
                                prereq.replace("_", " ").title(),
                                cls="badge badge-outline mr-2 mb-2",
                            )
                            for prereq in path_detail.prerequisites
                        ]
                        if path_detail.prerequisites
                        else [Span("No prerequisites required", cls="text-base-content/60")],
                        cls="flex flex-wrap",
                    ),
                    cls="h-fit",
                ),
                cls="grid grid-cols-1 lg:grid-cols-2 gap-6",
            ),
            cls="container mx-auto px-4 py-6",
        )

        return await BasePage(
            content=content,
            title=f"Learning Path: {path_detail.title}",
            page_type=PageType.STANDARD,
            request=request,
            active_page="learning",
        )

    routes.append(learning_path_detail)

    @rt("/learning/analytics")
    async def learning_analytics(request) -> Any:
        """Learning analytics dashboard with comprehensive insights."""

        content = Div(
            # Header
            Header(
                H1("Learning Analytics", cls="text-3xl font-bold text-primary"),
                P(
                    "Comprehensive insights into your learning journey",
                    cls="text-lg text-base-content/70 mt-2",
                ),
                cls="mb-8",
            ),
            # Analytics Overview
            Card(
                H2("Learning Performance", cls="text-xl font-semibold mb-4"),
                Div(
                    # Performance Metrics
                    Div(
                        Div(
                            Span("Learning Velocity", cls="text-sm text-base-content/70"),
                            Span("2.3", cls="text-2xl font-bold text-primary"),
                            P("concepts/day", cls="text-xs text-base-content/60"),
                            cls="stat text-center",
                        ),
                        Div(
                            Span("Retention Rate", cls="text-sm text-base-content/70"),
                            Span("87%", cls="text-2xl font-bold text-success"),
                            P("knowledge retained", cls="text-xs text-base-content/60"),
                            cls="stat text-center",
                        ),
                        Div(
                            Span("Efficiency Score", cls="text-sm text-base-content/70"),
                            Span("94", cls="text-2xl font-bold text-primary"),
                            P("out of 100", cls="text-xs text-base-content/60"),
                            cls="stat text-center",
                        ),
                        cls="stats stats-horizontal shadow w-full",
                    ),
                    cls="mb-6",
                ),
                # Learning Insights
                Div(
                    H3("Key Insights", cls="font-semibold mb-3"),
                    Div(
                        LearningUIComponents.render_insight_item(
                            "📈", "Peak Learning Time", "9-11 AM shows 40% higher focus", "high"
                        ),
                        LearningUIComponents.render_insight_item(
                            "🎯",
                            "Optimal Session Length",
                            "25-minute sessions maximize retention",
                            "medium",
                        ),
                        LearningUIComponents.render_insight_item(
                            "🔄",
                            "Review Schedule",
                            "Review concepts every 3 days for best retention",
                            "medium",
                        ),
                        cls="space-y-3",
                    ),
                ),
                cls="mb-8",
            ),
            cls="container mx-auto px-4 py-6",
        )

        return await BasePage(
            content=content,
            title="Learning Analytics",
            page_type=PageType.STANDARD,
            request=request,
            active_page="learning",
        )

    routes.append(learning_analytics)

    # KNOWLEDGE UNIT DETAIL PAGE: Moved to ku_reading_ui.py → /article/{uid}

    # ========================================================================
    # LEARNING STEP DETAIL PAGE
    # ========================================================================

    @rt("/ls/{uid}")
    async def ls_detail_view(request, uid: str) -> Any:
        """
        Learning Step detail view with full context and relationships.

        Shows LS details plus lateral relationships visualization.
        """
        # Note: This is a placeholder. Needs ls_service to be passed in
        content = Div(
            Card(
                H1(f"📖 Learning Step: {uid}", cls="text-2xl font-bold mb-4"),
                P("Learning Step detail page", cls="text-base-content/70 mb-4"),
                Button(
                    "← Back to Learning",
                    **{"hx-get": "/learning", "hx-target": "body"},
                    variant=ButtonT.ghost,
                ),
                cls="p-6 mb-4",
            ),
            # Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=uid,
                entity_type="ls",
            ),
            cls="container mx-auto p-6 max-w-4xl",
        )

        return await BasePage(
            content=content,
            title=f"LS: {uid}",
            page_type=PageType.STANDARD,
            request=request,
            active_page="learning",
        )

    routes.append(ls_detail_view)

    # ========================================================================
    # LEARNING PATH DETAIL PAGE
    # ========================================================================

    @rt("/lp/{uid}")
    async def lp_detail_view(request, uid: str) -> Any:
        """
        Learning Path detail view with full context and relationships.

        Shows LP details plus lateral relationships visualization.
        Note: This complements the existing /learning/path/{path_uid} route.
        """
        # Note: This is a placeholder. Needs lp_service to be passed in
        content = Div(
            Card(
                H1(f"🎓 Learning Path: {uid}", cls="text-2xl font-bold mb-4"),
                P("Learning Path detail page", cls="text-base-content/70 mb-4"),
                Button(
                    "← Back to Learning",
                    **{"hx-get": "/learning", "hx-target": "body"},
                    variant=ButtonT.ghost,
                ),
                cls="p-6 mb-4",
            ),
            # Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=uid,
                entity_type="lp",
            ),
            cls="container mx-auto p-6 max-w-4xl",
        )

        return await BasePage(
            content=content,
            title=f"LP: {uid}",
            page_type=PageType.STANDARD,
            request=request,
            active_page="learning",
        )

    routes.append(lp_detail_view)

    logger.info(f"✅ Learning UI routes registered: {len(routes)} endpoints")
    return routes


# Export the route creation function
__all__ = ["create_learning_ui_routes"]
