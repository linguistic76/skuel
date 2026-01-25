"""
User Dashboard Components
==========================

Reusable components for the user dashboard page.
Displays user profile, stats, and quick links to all domains.

Uses semantic HTML with TailwindCSS + DaisyUI styling.

Version: 2.0.0
Date: 2025-12-02
"""

from fasthtml.common import NotStr


class DashboardComponents:
    """Component library for user dashboard"""

    @staticmethod
    def render_dashboard(user, stats: dict | None = None) -> NotStr:
        """
        Render the complete user dashboard.

        Args:
            user: User object with uid, username, email, display_name
            stats: Optional dict with user statistics

        Returns:
            Complete dashboard UI as NotStr
        """
        # Default stats if none provided
        if stats is None:
            stats = {
                "tasks": {"total_active": 0, "completed_today": 0},
                "habits": {"total_active": 0, "current_streak": 0},
                "goals": {"total_active": 0, "on_track": 0},
                "learning": {"knowledge_mastered": 0, "paths_active": 0},
            }

        display_name = user.display_name or getattr(user, "title", "User")

        # Build stat cards using DaisyUI stats component
        stat_cards = f"""
        <div class="stats stats-vertical lg:stats-horizontal shadow bg-base-100 w-full">
            <a href="/tasks" class="stat hover:bg-base-200 transition-colors">
                <div class="stat-figure text-success text-2xl">✅</div>
                <div class="stat-title">Tasks</div>
                <div class="stat-value text-success">{stats["tasks"].get("total_active", 0)}</div>
                <div class="stat-desc">{stats["tasks"].get("completed_today", 0)} completed today</div>
            </a>
            <a href="/habits" class="stat hover:bg-base-200 transition-colors">
                <div class="stat-figure text-secondary text-2xl">🔁</div>
                <div class="stat-title">Habits</div>
                <div class="stat-value text-secondary">{stats["habits"].get("total_active", 0)}</div>
                <div class="stat-desc">{stats["habits"].get("current_streak", 0)} day streak</div>
            </a>
            <a href="/goals" class="stat hover:bg-base-200 transition-colors">
                <div class="stat-figure text-warning text-2xl">🎯</div>
                <div class="stat-title">Goals</div>
                <div class="stat-value text-warning">{stats["goals"].get("total_active", 0)}</div>
                <div class="stat-desc">{stats["goals"].get("on_track", 0)} on track</div>
            </a>
            <a href="/sel" class="stat hover:bg-base-200 transition-colors">
                <div class="stat-figure text-primary text-2xl">📚</div>
                <div class="stat-title">Learning</div>
                <div class="stat-value text-primary">{stats["learning"].get("knowledge_mastered", 0)}</div>
                <div class="stat-desc">{stats["learning"].get("paths_active", 0)} paths active</div>
            </a>
        </div>
        """

        # Build quick action cards
        quick_actions = """
        <a href="/search" class="block no-underline">
            <div class="p-6 bg-base-100 border border-base-200 rounded-lg hover:border-primary hover:shadow-md transition-all">
                <h3 class="text-lg font-semibold text-base-content mb-2">🔍 Search Knowledge</h3>
                <p class="text-sm text-base-content/70">Find and explore your knowledge base</p>
            </div>
        </a>
        <a href="/tasks/create" class="block no-underline">
            <div class="p-6 bg-base-100 border border-base-200 rounded-lg hover:border-primary hover:shadow-md transition-all">
                <h3 class="text-lg font-semibold text-base-content mb-2">✅ Add Task</h3>
                <p class="text-sm text-base-content/70">Create a new task to track</p>
            </div>
        </a>
        <a href="/calendar" class="block no-underline">
            <div class="p-6 bg-base-100 border border-base-200 rounded-lg hover:border-primary hover:shadow-md transition-all">
                <h3 class="text-lg font-semibold text-base-content mb-2">📆 View Calendar</h3>
                <p class="text-sm text-base-content/70">See all your tasks, events, and habits</p>
            </div>
        </a>
        <a href="/journals/create" class="block no-underline">
            <div class="p-6 bg-base-100 border border-base-200 rounded-lg hover:border-primary hover:shadow-md transition-all">
                <h3 class="text-lg font-semibold text-base-content mb-2">📝 Write Journal</h3>
                <p class="text-sm text-base-content/70">Reflect on your day</p>
            </div>
        </a>
        <a href="/askesis" class="block no-underline">
            <div class="p-6 bg-base-100 border border-base-200 rounded-lg hover:border-primary hover:shadow-md transition-all">
                <h3 class="text-lg font-semibold text-base-content mb-2">🎭 Chat with Askesis</h3>
                <p class="text-sm text-base-content/70">Get wisdom and guidance</p>
            </div>
        </a>
        <a href="/profile" class="block no-underline">
            <div class="p-6 bg-base-100 border border-base-200 rounded-lg hover:border-primary hover:shadow-md transition-all">
                <h3 class="text-lg font-semibold text-base-content mb-2">⚙️ Settings</h3>
                <p class="text-sm text-base-content/70">Manage your preferences</p>
            </div>
        </a>
        """

        return NotStr(f"""
        <div class="container mx-auto p-8 max-w-7xl">
            <!-- Welcome header -->
            <div class="text-center mb-12">
                <h1 class="text-4xl font-bold mb-2 text-base-content">Welcome back, {display_name}!</h1>
                <p class="text-base-content/70 mb-8">User ID: {user.uid}</p>
            </div>

            <!-- Stats cards -->
            <div class="mb-12">
                {stat_cards}
            </div>

            <!-- Quick actions -->
            <div class="mb-12">
                <h2 class="text-2xl font-bold mb-6 text-base-content">Quick Actions</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {quick_actions}
                </div>
            </div>

            <!-- Recent activity section -->
            <div class="mb-8">
                <h2 class="text-2xl font-bold mb-6 text-base-content">Recent Activity</h2>
                <div class="card bg-base-100 shadow-sm">
                    <div class="card-body">
                        <p class="text-base-content/70 text-center py-8">
                            Your recent activity will appear here
                        </p>
                    </div>
                </div>
            </div>
        </div>
        """)

    @staticmethod
    def render_profile_page(user) -> NotStr:
        """
        Render user profile page.

        Args:
            user: User object with full profile data

        Returns:
            Profile page UI as NotStr
        """
        display_name = user.display_name or getattr(user, "title", "User")
        username = getattr(user, "title", user.uid)
        is_active = getattr(user, "is_active", True)

        status_html = (
            """
            <span class="badge badge-success gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                Active
            </span>
        """
            if is_active
            else """
            <span class="badge badge-error gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
                Inactive
            </span>
        """
        )

        return NotStr(f"""
        <div class="container mx-auto p-8 max-w-7xl">
            <!-- Header -->
            <div class="text-center mb-12">
                <h1 class="text-4xl font-bold mb-2 text-base-content">Your Profile</h1>
                <p class="text-base-content/70 mb-8">Manage your account settings and preferences</p>
            </div>

            <!-- Profile information -->
            <div class="card bg-base-100 shadow-md max-w-2xl mx-auto mb-8">
                <div class="card-body p-8">
                    <h2 class="text-2xl font-bold mb-6 text-base-content">Account Information</h2>

                    <!-- Username -->
                    <div class="mb-6">
                        <span class="font-semibold text-base-content/80 block mb-1">Username</span>
                        <p class="text-base-content text-lg">{username}</p>
                    </div>

                    <!-- Display Name -->
                    <div class="mb-6">
                        <span class="font-semibold text-base-content/80 block mb-1">Display Name</span>
                        <p class="text-base-content text-lg">{display_name}</p>
                    </div>

                    <!-- Email -->
                    <div class="mb-6">
                        <span class="font-semibold text-base-content/80 block mb-1">Email</span>
                        <p class="text-base-content text-lg">{user.email}</p>
                    </div>

                    <!-- User ID -->
                    <div class="mb-6">
                        <span class="font-semibold text-base-content/80 block mb-1">User ID</span>
                        <p class="text-base-content/70 font-mono text-sm">{user.uid}</p>
                    </div>

                    <!-- Account Status -->
                    <div class="mb-6">
                        <span class="font-semibold text-base-content/80 block mb-1">Account Status</span>
                        {status_html}
                    </div>
                </div>
            </div>

            <!-- Action buttons -->
            <div class="text-center">
                <a href="/profile/settings" class="btn btn-primary mr-3">Edit Profile</a>
                <a href="/profile" class="btn btn-outline">Back to Profile</a>
            </div>
        </div>
        """)


__all__ = ["DashboardComponents"]
