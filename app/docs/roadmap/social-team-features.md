# Social & Team Features Roadmap

## Status: Planned (Not Implemented)

These features require significant multi-user infrastructure and are deferred for future implementation.

## Current State

**Implemented:**
- ✅ Entity pinning (bookmark/favorites) - fully functional
- ✅ UserRelationshipService with read-only queries for social relationships

**Not Implemented:**
- ❌ Following/followers mutation methods (follow_user, unfollow_user)
- ❌ Team/group functionality (entire domain)
- ❌ User discovery and profile pages
- ❌ Activity feeds
- ❌ Privacy settings

## Phase 1: Following/Followers (Estimated: 12-15 hours)

### Prerequisites
- User discovery page (browse/search users)
- User profile pages (view other users' public content)
- Privacy settings (public vs private profiles)
- Notification system for new followers

### Implementation

**1. Add Mutation Methods to UserRelationshipService (2 hours)**

```python
async def follow_user(self, user_uid: str, target_user_uid: str) -> Result[bool]:
    """Follow another user."""
    # Create (user)-[:FOLLOWS]->(target) relationship
    pass

async def unfollow_user(self, user_uid: str, target_user_uid: str) -> Result[bool]:
    """Unfollow a user."""
    # Delete (user)-[:FOLLOWS]->(target) relationship
    pass

async def get_follow_suggestions(self, user_uid: str, limit: int = 10) -> Result[list[str]]:
    """Get suggested users to follow based on common interests."""
    pass
```

**2. Create Social API Routes (2 hours)**

Routes needed:
```
POST   /api/user/social/follow        - Follow user
DELETE /api/user/social/follow/{uid}  - Unfollow user
GET    /api/user/social/suggestions   - Who to follow
GET    /api/user/social/activity      - Activity feed
```

**3. Build User Discovery UI (4-5 hours)**

Components needed:
- User search/browse page
- User profile cards with follow/unfollow buttons
- Following/followers lists
- User statistics display

**4. Create Activity Feed (4-5 hours)**

Components needed:
- Activity feed timeline component
- Activity item rendering (goals achieved, knowledge learned, etc.)
- Real-time updates (optional, via WebSocket or polling)
- Feed filtering (by followed users, by domain)

**5. Add Privacy Settings (2-3 hours)**

Features needed:
- Public/private profile toggle
- Visibility controls for specific content types
- Block user functionality

## Phase 2: Teams/Groups (Estimated: 15-20 hours)

### Prerequisites
- Team domain model (`/core/models/team/team.py`)
- Team backend (`UniversalNeo4jBackend[Team]`)
- Team service (CRUD operations)
- Permissions system (team admins, members, viewers)

### Implementation

**1. Create Team Domain Model (2 hours)**

```python
@dataclass(frozen=True)
class Team:
    uid: str
    name: str
    description: str
    owner_uid: str
    created_at: datetime
    member_count: int
    visibility: TeamVisibility  # public, private, invite_only
    metadata: dict[str, Any] | None = None


class TeamVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    INVITE_ONLY = "invite_only"


class TeamRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"
```

**2. Implement TeamsService (4-5 hours)**

```python
class TeamsService(BaseService[UniversalNeo4jBackend[Team], Team]):
    async def create_team(self, name: str, owner_uid: str, visibility: TeamVisibility) -> Result[Team]:
        """Create a new team."""
        pass

    async def add_member(self, team_uid: str, user_uid: str, role: TeamRole = TeamRole.MEMBER) -> Result[bool]:
        """Add member to team."""
        pass

    async def remove_member(self, team_uid: str, user_uid: str) -> Result[bool]:
        """Remove member from team."""
        pass

    async def get_team_members(self, team_uid: str) -> Result[list[dict]]:
        """Get all team members with roles."""
        pass

    async def update_member_role(self, team_uid: str, user_uid: str, new_role: TeamRole) -> Result[bool]:
        """Update member's role in team."""
        pass

    async def get_user_teams(self, user_uid: str) -> Result[list[Team]]:
        """Get all teams a user belongs to."""
        pass
```

**3. Create Team API Routes (3-4 hours)**

Routes needed:
```
POST   /api/teams             - Create team
GET    /api/teams/{uid}       - Get team details
PUT    /api/teams/{uid}       - Update team
DELETE /api/teams/{uid}       - Delete team
POST   /api/teams/{uid}/join  - Join team (if public)
DELETE /api/teams/{uid}/leave - Leave team
GET    /api/teams/{uid}/members - List members
POST   /api/teams/{uid}/invite - Invite user
PUT    /api/teams/{uid}/members/{user_uid}/role - Update member role
```

**4. Build Team UI Components (5-6 hours)**

Components needed:
- Team creation form
- Team directory/browse page
- Team detail page with member list
- Team settings page (for admins)
- Join/leave buttons
- Team content dashboard (shared goals, knowledge, etc.)
- Member management interface

**5. Add Permissions System (3-4 hours)**

Features needed:
- Role-based access control (RBAC)
- Permission checks on all team operations
- Audit log for team actions
- Team content visibility controls

## Phase 3: Shared Content & Collaboration (Estimated: 10-15 hours)

### Prerequisites
- Teams infrastructure (from Phase 2)
- Real-time collaboration support (optional)

### Implementation

**1. Shared Goals (3-4 hours)**

Features:
- Create team goals
- Assign goals to team members
- Track team progress on goals
- Team goal completion celebrations

**2. Shared Knowledge (3-4 hours)**

Features:
- Team knowledge repositories
- Collaborative knowledge unit creation
- Team learning paths
- Knowledge sharing within teams

**3. Team Activity Feed (2-3 hours)**

Features:
- Team-specific activity stream
- Member contributions tracking
- Team milestones and achievements

**4. Collaborative Editing (2-4 hours, optional)**

Features:
- Real-time collaborative editing of team content
- Conflict resolution
- Version history
- Comments and discussions

## Decision Points

Before implementing these features, consider:

### 1. Product Direction
- **Question:** Is SKUEL becoming a social platform or staying personal productivity?
- **Implications:** Social features add complexity, maintenance burden, and moderation needs
- **Alternative:** Keep SKUEL focused on individual productivity with optional sharing via links

### 2. Value Proposition
- **Following/Followers:** What's the value prop? Share goals? Progress accountability? Learning buddies?
- **Teams:** What would teams enable? Shared goals? Collaborative learning? Study groups?
- **Trade-offs:** Social features vs. focus on individual productivity

### 3. Infrastructure Requirements
- **Multi-user:** Requires robust user discovery, profile pages, privacy controls
- **Scalability:** Activity feeds, notifications, real-time updates need infrastructure
- **Moderation:** Social features require content moderation, user blocking, reporting
- **Cost:** Increased server costs, storage, maintenance

### 4. Privacy & Security
- **Data sharing:** What user data is visible to others?
- **Consent:** How do users control their visibility?
- **Safety:** How to prevent harassment, spam, inappropriate content?

## Alternative: Sharing Links (2-3 hours)

A simpler approach without full social infrastructure:

### Features
- **Share this goal/KU/LP:** Generates shareable link
- **Read-only view:** Recipients can view but not edit
- **Optional comments:** Allow comments on shared content
- **No following/follower complexity:** Just direct sharing

### Benefits
- Much simpler implementation (2-3 hours vs 37-55 hours)
- No social network maintenance burden
- No moderation needs
- Privacy-first approach
- Still enables collaboration via direct sharing

### Implementation
```python
# Share link generation
async def create_share_link(entity_uid: str, expires_in_days: int = 30) -> Result[str]:
    """Generate shareable link for an entity."""
    pass

# Public view route
@rt("/share/{share_token}")
async def view_shared_entity(share_token: str):
    """Public view of shared entity (read-only)."""
    pass
```

## Recommendation

**Start with:**
1. ✅ Entity pinning (already implemented)
2. Sharing links (2-3 hours, high value, low complexity)

**Defer:**
1. Following/followers (12-15 hours, unclear value prop)
2. Teams (15-20 hours, requires significant infrastructure)
3. Collaborative features (10-15 hours, needs teams first)

**Total deferred effort:** 37-55 hours

**Rationale:** SKUEL's strength is individual productivity and learning. Adding social features should be driven by clear user demand, not speculation. Start simple with sharing links, validate user interest, then build more complex social features if needed.

## Next Steps

1. **Validate demand:** Survey users about interest in social features
2. **Define use cases:** What specific problems would social features solve?
3. **Start minimal:** Implement sharing links first
4. **Measure engagement:** Track sharing link usage
5. **Iterate:** Add more social features only if sharing links are heavily used

## References

- UserRelationshipService: `/core/services/user_relationship_service.py`
- Entity Pinning API: `/adapters/inbound/user_pins_api.py`
- User Profile Hub: `/adapters/inbound/user_profile_ui.py`
- Architecture: `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md`
