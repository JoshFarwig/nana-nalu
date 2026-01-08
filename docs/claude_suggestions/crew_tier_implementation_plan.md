# Crew Tier System Implementation Plan

## Overview

Implement a flexible crew tier system for nānā-nalu that handles:
1. **Single-crew Free tier** (1 crew, 3 members max)
2. **Multi-crew Kokua tier** (2 crews, with 1 "Kokua upgraded" option at 5 members)
3. **Tier-based crew creation and membership limits**
4. **Graceful downgrade handling** (Kokua → Free)

---

## Key Questions Resolved

### Q1: Should we keep `invited_by_user_id` on User model?

**Context:** Crew invites are user → crew, not user → user. Is referral tracking still valuable?

**Answer:** **OPTIONAL - Implement if you want growth analytics**

**Pros:**
- ✅ Track viral growth: "Which users bring in the most signups?"
- ✅ Future features: Referral rewards, achievement badges
- ✅ Analytics: Measure crew invite → signup conversion
- ✅ Identify power users: Users who drive network effects

**Cons:**
- ❌ Indirect relationship: It's "who created the invite link" not "who invited me"
- ❌ Extra complexity if you don't need the analytics now
- ❌ Can be added later without data loss (track going forward)

**Recommendation:**
- **If pre-revenue/beta:** Skip it for now, focus on core features
- **If planning referral programs:** Add it from the start
- **Middle ground:** Add the column (nullable), populate later when you need it

```python
# Keep it simple for now
class User(Base):
    invited_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # NULL = direct signup, no crew invite used
    # Populated only when joining via crew magic link
```

---

### Q2: Crew Tier Model - Free vs Kokua

**Free Tier:**
- Can create OR join: **1 crew total**
- Crew max members: **3**
- Spot quota: **3 spots** (allocate freely between private/crew)

**Kokua Tier:**
- Can create OR join: **2 crews total**
- **1 crew can be "Kokua upgraded"** (5 members, extra features)
- **1 crew is standard** (3 members, free tier features)
- Spot quota: **TBD** (allocate freely between private/crew)

**Key clarifications:**
- "Kokua upgraded crew" = premium crew with 5 member slots
- Kokua users choose at creation: "Make this a Kokua crew?" (Yes/No)
- If Yes: Uses their 1 Kokua upgrade slot, 5 members
- If No: Standard crew, 3 members (same as free tier)
- Free users **CAN join** Kokua upgraded crews (they just can't create them)

---

## Database Schema Updates

### Updated `account_tiers` Table

```python
class AccountTier(Base):
    __tablename__ = "account_tiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))

    # Spot quotas (contribution pool model - unchanged)
    spot_quota: Mapped[int | None]  # Free: 3, Kokua: TBD, Admin: NULL
    max_archived_spots: Mapped[int | None]  # Free: 2, Kokua: NULL, Admin: NULL

    # ========== CREW TIER LIMITS ==========

    # Total crews user can be in (as member OR creator)
    max_crews_joined: Mapped[int | None]
    # Free: 1, Kokua: 2, Admin: NULL (unlimited)

    # How many crews user can CREATE (as owner)
    max_crews_created: Mapped[int | None]
    # Free: 1, Kokua: 2, Admin: NULL (unlimited)
    # Note: This limits creation, not membership

    # ========== KOKUA UPGRADED CREW LIMITS ==========

    # How many "premium" crews (5 members) user can create
    max_kokua_crews_allowed: Mapped[int] = mapped_column(default=0)
    # Free: 0, Kokua: 1, Admin: NULL (unlimited)

    # Max members for standard (non-upgraded) crews
    default_crew_max_members: Mapped[int | None]
    # Free: 3, Kokua: 3, Admin: NULL (unlimited)

    # Max members for Kokua upgraded crews
    kokua_crew_max_members: Mapped[int | None]
    # Free: NULL (can't create), Kokua: 5, Admin: NULL (unlimited)

    # Other tier features (unchanged)
    can_create_global_spots: Mapped[bool] = mapped_column(default=False)
    price_monthly_cents: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

### Updated `crews` Table

```python
class Crew(Base):
    __tablename__ = "crews"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # ========== TIER-BASED CREW CONFIG ==========

    # Is this a Kokua upgraded crew? (5 members, premium features)
    is_kokua_crew: Mapped[bool] = mapped_column(default=False)

    # Max members for THIS crew (set at creation)
    max_members: Mapped[int]
    # - Free tier crew: 3
    # - Kokua upgraded crew: 5
    # - Admin crew: Could be set to any value

    # ========== DOWNGRADE HANDLING ==========

    # Flag when crew needs member reduction (creator downgraded)
    requires_member_reduction: Mapped[bool] = mapped_column(default=False)
    # If creator downgrades from Kokua → Free and crew has >3 members

    # Deadline to reduce members (grace period)
    member_reduction_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # ========== STANDARD FIELDS ==========

    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Relationships
    members: Mapped[list["CrewMember"]] = relationship("CrewMember", back_populates="crew")
    spots: Mapped[list["SurfSpot"]] = relationship("SurfSpot", back_populates="crew")
```

### `crew_members` Table (unchanged)

```python
class CrewMember(Base):
    __tablename__ = "crew_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    crew_id: Mapped[int] = mapped_column(ForeignKey("crews.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    role: Mapped[str] = mapped_column(String(50), default="member")
    # 'creator', 'admin', 'member'

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("crew_id", "user_id", name="unique_crew_membership"),
    )
```

---

## Tier Seed Data

```python
# Migration: Seed account_tiers table

INSERT INTO account_tiers (
    name,
    display_name,
    spot_quota,
    max_archived_spots,
    max_crews_joined,
    max_crews_created,
    max_kokua_crews_allowed,
    default_crew_max_members,
    kokua_crew_max_members,
    can_create_global_spots,
    price_monthly_cents,
    is_active
)
VALUES
    -- Free: 1 crew, 3 members, 3 spots
    (
        'free',
        'Free',
        3,                -- spot_quota
        2,                -- max_archived_spots
        1,                -- max_crews_joined
        1,                -- max_crews_created
        0,                -- max_kokua_crews_allowed (can't create premium crews)
        3,                -- default_crew_max_members
        NULL,             -- kokua_crew_max_members (not applicable)
        FALSE,            -- can_create_global_spots
        0,                -- price_monthly_cents
        TRUE              -- is_active
    ),

    -- Kokua: 2 crews, 1 can be upgraded to 5 members, TBD spots
    (
        'kokua',
        'Kokua Supporter',
        10,               -- spot_quota (TBD - placeholder)
        NULL,             -- max_archived_spots (unlimited)
        2,                -- max_crews_joined
        2,                -- max_crews_created
        1,                -- max_kokua_crews_allowed (1 premium crew)
        3,                -- default_crew_max_members (non-upgraded crews)
        5,                -- kokua_crew_max_members (upgraded crew size)
        FALSE,            -- can_create_global_spots
        500,              -- price_monthly_cents ($5/mo)
        TRUE              -- is_active
    ),

    -- Admin: unlimited everything
    (
        'admin',
        'Admin',
        NULL,             -- spot_quota (unlimited)
        NULL,             -- max_archived_spots (unlimited)
        NULL,             -- max_crews_joined (unlimited)
        NULL,             -- max_crews_created (unlimited)
        NULL,             -- max_kokua_crews_allowed (unlimited)
        NULL,             -- default_crew_max_members (unlimited)
        NULL,             -- kokua_crew_max_members (unlimited)
        TRUE,             -- can_create_global_spots
        NULL,             -- price_monthly_cents (not applicable)
        TRUE              -- is_active
    );
```

---

## Service Layer Implementation

### Crew Creation with Tier Validation

```python
# services/crew_service.py

class CrewService:

    async def create_crew(
        self,
        user_id: int,
        crew_data: CrewCreate,
        use_kokua_upgrade: bool = False
    ) -> Crew:
        """
        Create a crew with tier-based validation.

        Args:
            user_id: ID of user creating the crew
            crew_data: Crew details (name, description)
            use_kokua_upgrade: If True, use Kokua upgrade slot (5 members)

        Raises:
            QuotaExceededError: User has reached crew creation limit
            PermissionError: User tier doesn't allow Kokua crews
        """

        # Get user with tier info
        user = await self.user_repo.get_by_id_with_tier(user_id)
        tier = user.tier

        # ========== VALIDATION 1: Crew Creation Limit ==========
        current_crews_created = await self.crew_repo.count_created_by_user(user_id)

        if tier.max_crews_created is not None:
            if current_crews_created >= tier.max_crews_created:
                raise QuotaExceededError(
                    f"Crew creation limit reached ({current_crews_created}/{tier.max_crews_created}). "
                    f"Upgrade to Kokua to create more crews!"
                )

        # ========== VALIDATION 2: Total Crew Membership Limit ==========
        total_crews = await self.crew_repo.count_total_crews_for_user(user_id)

        if tier.max_crews_joined is not None:
            if total_crews >= tier.max_crews_joined:
                raise QuotaExceededError(
                    f"You're already in {total_crews} crew(s). "
                    f"Leave a crew first or upgrade to Kokua for more slots."
                )

        # ========== VALIDATION 3: Kokua Upgrade Slot ==========
        if use_kokua_upgrade:
            # Check tier allows Kokua crews
            if tier.max_kokua_crews_allowed == 0:
                raise PermissionError(
                    "Kokua tier required for upgraded crews. "
                    "Upgrade your account to unlock 5-member crews!"
                )

            # Check user hasn't used their Kokua slot
            kokua_crews_count = await self.crew_repo.count_kokua_crews_by_user(user_id)

            if tier.max_kokua_crews_allowed is not None:
                if kokua_crews_count >= tier.max_kokua_crews_allowed:
                    raise QuotaExceededError(
                        f"You've already created your Kokua upgraded crew. "
                        f"Your next crew will be a standard crew (3 members)."
                    )

            max_members = tier.kokua_crew_max_members  # 5
            is_kokua_crew = True
        else:
            max_members = tier.default_crew_max_members  # 3
            is_kokua_crew = False

        # ========== CREATE CREW ==========
        crew = await self.crew_repo.create(
            created_by_id=user_id,
            is_kokua_crew=is_kokua_crew,
            max_members=max_members,
            **crew_data.model_dump()
        )

        # Add creator as first member with 'creator' role
        await self.crew_repo.add_member(
            crew_id=crew.id,
            user_id=user_id,
            role="creator"
        )

        logger.info(
            "Crew created successfully",
            extra={
                "user_id": user_id,
                "crew_id": crew.id,
                "is_kokua_crew": is_kokua_crew,
                "max_members": max_members,
            },
        )

        return crew
```

### Joining a Crew

```python
async def join_crew(
    self,
    user_id: int,
    crew_id: int
) -> CrewMember:
    """
    Join an existing crew with tier validation.

    Raises:
        QuotaExceededError: User has reached max crew membership
        CrewFullError: Crew has reached max members
    """

    user = await self.user_repo.get_by_id_with_tier(user_id)
    crew = await self.crew_repo.get_by_id(crew_id)
    tier = user.tier

    # ========== VALIDATION 1: User's Crew Membership Limit ==========
    total_crews = await self.crew_repo.count_total_crews_for_user(user_id)

    if tier.max_crews_joined is not None:
        if total_crews >= tier.max_crews_joined:
            raise QuotaExceededError(
                f"You're already in {total_crews} crew(s). "
                f"Leave a crew first or upgrade to Kokua."
            )

    # ========== VALIDATION 2: Crew Member Capacity ==========
    current_members = await self.crew_repo.count_members(crew_id)

    if current_members >= crew.max_members:
        raise CrewFullError(
            f"This crew is full ({current_members}/{crew.max_members} members). "
            f"The crew owner can upgrade to Kokua for more slots."
        )

    # ========== JOIN CREW ==========
    member = await self.crew_repo.add_member(
        crew_id=crew_id,
        user_id=user_id,
        role="member"
    )

    logger.info(
        "User joined crew",
        extra={
            "user_id": user_id,
            "crew_id": crew_id,
        },
    )

    return member
```

---

## Tier Downgrade Handling

### Problem: User Downgrades Kokua → Free

**Scenario:**
- Kokua user is in 2 crews (limit: 2)
- User cancels subscription → becomes Free tier (limit: 1)
- **Which crew do they keep?**

**Additional complication:**
- If user CREATED a Kokua crew (5 members), what happens to it?
- Do they lose ownership? Does crew get deleted? Grace period?

---

### Strategy Options

#### Option A: User Choice (Recommended)

**Flow:**
1. User cancels Kokua subscription
2. Remain on Kokua until billing period ends (grace period)
3. **7 days before downgrade**, email warning:
   - "You're in 2 crews. Free tier allows 1 crew."
   - "Choose which crew to keep: [Sunset Crew] or [North Shore Riders]"
4. User selects in app settings
5. On downgrade date:
   - Remove from non-selected crew
   - Update tier to Free

**Handling Kokua crew ownership:**
- If user CREATED a Kokua crew (5 members), convert it to free crew (3 members max)
- **7 days before downgrade**, email crew:
   - "Crew owner is downgrading. Crew will reduce from 5 to 3 members."
   - "Newest 2 members will be removed unless owner upgrades."
- On downgrade: Remove 2 newest members (by `joined_at` timestamp)

**Pros:**
- ✅ User has control over which crew to keep
- ✅ Transparent: no surprise removals
- ✅ Grace period allows user to change mind (re-subscribe)

**Cons:**
- ⚠️ Requires UI for crew selection
- ⚠️ Requires background job for downgrade processing
- ⚠️ User might ignore email and not choose (need default behavior)

**Implementation:**

```python
# users table
class User(Base):
    pending_tier_downgrade: Mapped[bool] = mapped_column(default=False)
    tier_downgrade_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_crew_to_keep_id: Mapped[int | None] = mapped_column(ForeignKey("crews.id"))

# Background job (runs daily)
async def process_tier_downgrades():
    """Process users whose downgrade deadline has passed."""

    users_to_downgrade = await db.query(User).filter(
        User.pending_tier_downgrade == True,
        User.tier_downgrade_deadline <= datetime.now(timezone.utc)
    ).all()

    for user in users_to_downgrade:
        # If user didn't choose, use default strategy (see Option B/C/D)
        if not user.selected_crew_to_keep_id:
            user.selected_crew_to_keep_id = await auto_select_crew_to_keep(user.id)

        # Remove from other crews
        await remove_from_other_crews(user.id, keep_crew_id=user.selected_crew_to_keep_id)

        # Handle Kokua crew ownership
        kokua_crews_owned = await get_kokua_crews_created_by(user.id)
        for crew in kokua_crews_owned:
            await downgrade_crew_to_free(crew.id)  # Reduce to 3 members

        # Downgrade tier
        free_tier = await get_tier_by_name("free")
        user.tier_id = free_tier.id
        user.pending_tier_downgrade = False

        await db.commit()
```

---

#### Option B: Activity-Based (Automatic)

**Strategy:** Keep the crew user is most active in

**Metrics to consider:**
- Most observations created in crew spots
- Most recent activity (last observation timestamp)
- Highest spot contribution (most crew spots allocated)

**Pros:**
- ✅ Automatic: no user input required
- ✅ Logical: keep the crew they actually use

**Cons:**
- ❌ User might disagree with the choice
- ❌ Requires tracking activity metrics
- ❌ What if activity is equal? (need tiebreaker)

**Implementation:**

```python
async def auto_select_crew_to_keep(user_id: int) -> int:
    """Select crew based on user activity."""

    crews = await get_user_crews(user_id)

    crew_scores = []
    for crew in crews:
        # Calculate activity score
        observations_count = await count_observations_by_user_in_crew(user_id, crew.id)
        spots_contributed = await count_spots_contributed_to_crew(user_id, crew.id)
        days_since_last_activity = await get_days_since_last_activity(user_id, crew.id)

        score = (
            observations_count * 2 +  # Observations are more valuable
            spots_contributed * 5 +    # Contributing spots is valuable
            (1 / max(days_since_last_activity, 1)) * 10  # Recent activity matters
        )

        crew_scores.append((crew.id, score))

    # Sort by score descending, return highest
    crew_scores.sort(key=lambda x: x[1], reverse=True)
    return crew_scores[0][0]
```

---

#### Option C: Creator Priority (Automatic)

**Strategy:** Keep crews user CREATED over crews they joined

**Logic:**
1. If user created any crew → keep the created crew
2. If user created multiple crews → keep most active (or oldest)
3. If user created zero crews → keep most active joined crew

**Pros:**
- ✅ Simple logic: ownership matters
- ✅ Protects crews user invested time creating
- ✅ Automatic

**Cons:**
- ❌ User might care more about a crew they joined
- ❌ Created crew could be inactive/abandoned

**Implementation:**

```python
async def auto_select_crew_to_keep(user_id: int) -> int:
    """Select crew prioritizing creator ownership."""

    created_crews = await get_crews_created_by(user_id)

    if created_crews:
        # Keep the created crew (if multiple, keep most active)
        if len(created_crews) == 1:
            return created_crews[0].id
        else:
            # Tiebreaker: most active created crew
            return await get_most_active_crew(created_crews)
    else:
        # User didn't create any crew, keep most active joined crew
        joined_crews = await get_crews_joined_by(user_id)
        return await get_most_active_crew(joined_crews)
```

---

#### Option D: Grace Period + Manual Removal (Hybrid)

**Strategy:** Don't auto-remove, but restrict new actions

**Flow:**
1. User downgrades to Free (limit: 1 crew)
2. **Don't immediately remove** from 2nd crew
3. **Restrict actions:** Can't create spots, join new crews, invite members
4. Show banner: "You're in 2 crews. Free tier allows 1. Choose which to leave."
5. User manually leaves a crew when ready
6. Once down to 1 crew → restrictions lifted

**Pros:**
- ✅ User has full control
- ✅ No forced removal (better UX)
- ✅ User can take their time deciding

**Cons:**
- ❌ User could stay in "restricted" state indefinitely
- ❌ Need to enforce restrictions across all endpoints
- ❌ Complicates business logic (need to check "over quota" state)

**Implementation:**

```python
# Middleware or dependency
async def check_crew_quota(user: User):
    """Block new crew actions if user is over quota."""

    tier = user.tier
    total_crews = await count_total_crews(user.id)

    if tier.max_crews_joined and total_crews > tier.max_crews_joined:
        raise QuotaExceededError(
            f"You're in {total_crews} crews but your tier allows {tier.max_crews_joined}. "
            f"Leave a crew to continue."
        )
```

---

### Recommended Approach: **Option A (User Choice) with Option B (Activity) as Fallback**

**Why:**
- Respects user agency (they choose which crew to keep)
- Automatic fallback if user doesn't respond (activity-based)
- Grace period allows re-subscription if user changes mind
- Transparent: user knows exactly what will happen

**Implementation Timeline:**

```python
# Day 0: User cancels subscription
- subscription_status = 'cancelled'
- pending_tier_downgrade = True
- tier_downgrade_deadline = billing_period_end + 7 days
- Send email: "Choose which crew to keep"

# Day 1-7: Grace period
- User can select crew in settings UI
- User can re-subscribe to cancel downgrade

# Day 7: Downgrade deadline
- If user selected crew: keep that one, leave others
- If user didn't select: auto-select based on activity (Option B)
- If user created Kokua crew: convert to free crew (remove 2 members)
- Set tier = 'free'
- Clear pending_tier_downgrade flag
```

---

## Edge Cases & Considerations

### Edge Case 1: User is Only Member of Crew

**Scenario:**
- User created a crew but nobody joined
- User downgrades and is forced to leave

**Question:** Delete the empty crew or keep it?

**Recommendation:**
- Keep the crew, mark as `is_active = False`
- User is removed as member but remains as `created_by_id`
- If user re-upgrades, can re-activate the crew
- After 30 days inactive, permanently delete crew

---

### Edge Case 2: Kokua Crew Becomes Orphaned

**Scenario:**
- User A (Kokua) creates 5-member crew
- User A downgrades to Free
- Crew reduces to 3 members, but User A leaves (chose other crew)
- **Who owns the Kokua crew now?**

**Recommendation:**
- Transfer ownership to longest-tenured member
- Automatically downgrade crew to free (3 members)
- Notify new owner via email

```python
async def handle_creator_leaving_crew(crew_id: int, leaving_user_id: int):
    """Transfer ownership if creator leaves."""

    crew = await get_crew(crew_id)

    if crew.created_by_id == leaving_user_id:
        # Find next owner (oldest member)
        next_owner = await get_oldest_member(crew_id, exclude_user_id=leaving_user_id)

        if next_owner:
            # Transfer ownership
            crew.created_by_id = next_owner.user_id
            await db.commit()

            # Notify new owner
            await send_email(
                to=next_owner.email,
                subject=f"You're now the owner of {crew.name}",
                body=f"The previous owner left the crew. You're now in charge!"
            )
        else:
            # No other members, deactivate crew
            crew.is_active = False
            await db.commit()
```

---

### Edge Case 3: All Members are Free Tier in Kokua Crew

**Scenario:**
- User A (Kokua) creates 5-member crew
- Invites 4 Free tier users
- User A downgrades to Free
- **Crew has 5 Free tier users but max should be 3**

**Recommendation:**
- Remove newest 2 members (by `joined_at`)
- Notify removed members: "Crew owner downgraded, crew reduced to 3 members"
- Offer removed members: "Upgrade to Kokua to create your own crew!"

---

### Edge Case 4: User in 2 Crews, Both Inactive

**Scenario:**
- User joined 2 crews 6 months ago
- Zero activity in either crew
- Downgrade forces a choice

**Recommendation:**
- Use Option B (activity-based) fallback
- If activity is equal (both zero), use tiebreaker:
  1. Keep crew user created (if any)
  2. Keep oldest crew (by `joined_at`)
  3. Keep crew with most members (more active community)

---

## Frontend UX Considerations

### Crew Selection UI (Downgrade Flow)

```typescript
// SettingsPage.tsx - Tier Downgrade Warning

interface CrewChoice {
  crew_id: number
  crew_name: string
  member_count: number
  your_role: 'creator' | 'admin' | 'member'
  spots_contributed: number
  recent_activity: string  // "Active 2 days ago"
}

function CrewDowngradeSelector({ crews, deadline }: Props) {
  const [selectedCrewId, setSelectedCrewId] = useState<number | null>(null)

  return (
    <div className="downgrade-warning">
      <h3>⚠️ Tier Downgrade Pending</h3>
      <p>
        Your Kokua subscription ends on {deadline}.
        Free tier allows 1 crew. Choose which to keep:
      </p>

      {crews.map(crew => (
        <CrewChoiceCard
          key={crew.crew_id}
          crew={crew}
          selected={selectedCrewId === crew.crew_id}
          onSelect={() => setSelectedCrewId(crew.crew_id)}
        />
      ))}

      <button onClick={() => saveCrewChoice(selectedCrewId)}>
        Confirm Selection
      </button>

      <p className="auto-select-warning">
        If you don't choose, we'll keep the crew you're most active in.
      </p>
    </div>
  )
}
```

### Crew Creation UI (Kokua Upgrade Option)

```typescript
// CreateCrewModal.tsx

function CreateCrewForm({ userTier }: Props) {
  const [useKokuaUpgrade, setUseKokuaUpgrade] = useState(false)

  // Check if user has Kokua slot available
  const hasKokuaSlot = userTier.max_kokua_crews_allowed > 0
  const hasUsedKokuaSlot = userKokuaCrew !== null

  return (
    <form onSubmit={handleCreateCrew}>
      <input name="crew_name" placeholder="Crew name" />
      <textarea name="description" placeholder="Description" />

      {hasKokuaSlot && !hasUsedKokuaSlot && (
        <div className="kokua-upgrade-option">
          <label>
            <input
              type="checkbox"
              checked={useKokuaUpgrade}
              onChange={e => setUseKokuaUpgrade(e.target.checked)}
            />
            <strong>Use Kokua Upgrade</strong> - 5 members (you have 1 available)
          </label>

          {useKokuaUpgrade && (
            <p className="info">
              This crew will have 5 member slots instead of 3.
              You can only create 1 Kokua crew.
            </p>
          )}
        </div>
      )}

      <p className="member-limit-info">
        Max members: {useKokuaUpgrade ? '5' : '3'}
      </p>

      <button type="submit">Create Crew</button>
    </form>
  )
}
```

---

## Implementation Checklist

### Phase 1: Database Schema (Week 1)

- [ ] Add crew tier columns to `account_tiers` table:
  - `max_crews_joined`
  - `max_crews_created`
  - `max_kokua_crews_allowed`
  - `default_crew_max_members`
  - `kokua_crew_max_members`

- [ ] Add Kokua crew columns to `crews` table:
  - `is_kokua_crew`
  - `requires_member_reduction`
  - `member_reduction_deadline`

- [ ] Add downgrade columns to `users` table (optional for Option A):
  - `pending_tier_downgrade`
  - `tier_downgrade_deadline`
  - `selected_crew_to_keep_id`

- [ ] Run migrations and seed tier data

### Phase 2: Repository Layer (Week 2)

- [ ] Add crew counting methods to `CrewRepository`:
  - `count_created_by_user(user_id)`
  - `count_total_crews_for_user(user_id)`
  - `count_kokua_crews_by_user(user_id)`
  - `count_members(crew_id)`

- [ ] Add member management methods:
  - `add_member(crew_id, user_id, role)`
  - `remove_member(crew_id, user_id)`
  - `get_oldest_member(crew_id, exclude_user_id)`

### Phase 3: Service Layer (Week 3)

- [ ] Implement `create_crew()` with tier validation
- [ ] Implement `join_crew()` with tier + capacity validation
- [ ] Implement `leave_crew()` with ownership transfer logic
- [ ] Add exception classes:
  - `QuotaExceededError`
  - `CrewFullError`
  - `PermissionError`

### Phase 4: Downgrade Handling (Week 4)

- [ ] Choose downgrade strategy (recommend Option A + B)
- [ ] Implement downgrade flow:
  - Email warning 7 days before
  - Crew selection UI
  - Background job for auto-processing
- [ ] Implement Kokua crew downgrade:
  - Convert 5-member crew → 3-member crew
  - Remove newest 2 members
  - Notify removed members

### Phase 5: API Endpoints (Week 5)

- [ ] `POST /crews` - Create crew with `use_kokua_upgrade` param
- [ ] `POST /crews/{id}/join` - Join crew with quota validation
- [ ] `DELETE /crews/{id}/leave` - Leave crew
- [ ] `POST /users/me/select-crew-to-keep` - For downgrade flow
- [ ] `GET /users/me/crew-quota` - Check current crew usage

### Phase 6: Frontend Integration (Week 6)

- [ ] Crew creation modal with Kokua upgrade checkbox
- [ ] Crew selection UI for tier downgrades
- [ ] Quota status display ("You're in 1/2 crews")
- [ ] Error handling for quota exceeded
- [ ] Downgrade warning banner in settings

### Phase 7: Background Jobs (Week 7)

- [ ] Daily cron job: `process_tier_downgrades()`
- [ ] Stripe webhook handler: Detect subscription cancellations
- [ ] Email notifications:
  - 7-day downgrade warning
  - Crew reduction notice (for Kokua crews)
  - Removed from crew notice

---

## Testing Scenarios

### Test Case 1: Free User Creates Crew

- Free user creates crew
- Crew has `max_members = 3`, `is_kokua_crew = False`
- User cannot create 2nd crew (quota error)

### Test Case 2: Kokua User Creates Kokua Crew

- Kokua user creates crew with `use_kokua_upgrade = True`
- Crew has `max_members = 5`, `is_kokua_crew = True`
- User can create 2nd crew (but not another Kokua crew)

### Test Case 3: Free User Joins Kokua Crew

- Free user (in 0 crews) joins Kokua crew (5 members)
- Success (free users can join Kokua crews)
- Free user cannot join 2nd crew (quota error)

### Test Case 4: Kokua Downgrade - User Chooses Crew

- Kokua user in 2 crews cancels subscription
- Downgrade deadline set to billing_period_end + 7 days
- User selects "Crew A" to keep
- On deadline: User removed from "Crew B"

### Test Case 5: Kokua Downgrade - No Choice (Fallback)

- Kokua user in 2 crews cancels subscription
- User doesn't select a crew
- On deadline: Auto-select based on activity
- User kept in most active crew

### Test Case 6: Kokua Crew Owner Downgrades

- Kokua user created 5-member crew
- User downgrades to Free
- Crew reduced to 3 members (newest 2 removed)
- Removed members notified via email

### Test Case 7: Crew Becomes Orphaned

- Kokua user created crew, then downgrades
- User chooses to keep different crew (leaves this one)
- Ownership transferred to oldest member
- Crew downgraded to free (3 members)

---

## Security Considerations

### Prevent Tier Bypass

```python
# ALWAYS validate tier server-side
# NEVER trust client-sent tier information

async def create_crew(user_id: int, use_kokua_upgrade: bool):
    # Query database for current tier
    user = await db.query(User).join(AccountTier).filter(User.id == user_id).first()

    # Server-side validation
    if use_kokua_upgrade and user.tier.max_kokua_crews_allowed == 0:
        raise PermissionError("Kokua tier required")
```

### Rate Limiting

```python
# Prevent abuse of crew creation
@rate_limit("5/hour")  # 5 crew creations per hour
async def create_crew(request):
    ...
```

### Subscription Status Verification

```python
# Sync with Stripe on critical operations
async def verify_subscription_active(user_id: int):
    user = await get_user(user_id)

    if user.tier.name == 'kokua':
        # Verify with Stripe
        stripe_sub = stripe.Subscription.retrieve(user.subscription_id)

        if stripe_sub.status != 'active':
            # Trigger downgrade
            await initiate_tier_downgrade(user_id)
            raise SubscriptionExpiredError()
```

---

## Analytics to Track

### Crew Metrics:
- Crews created per tier (free vs kokua)
- Kokua upgrade usage rate (% of Kokua users who use their 5-member slot)
- Average crew size (free: 1-3, kokua: 1-5)
- Crew longevity (how long crews stay active)

### Downgrade Metrics:
- Downgrade completion rate (% who choose vs auto-selected)
- Re-subscription rate during grace period
- Reasons for downgrade (survey on cancellation)

### Conversion Metrics:
- Free → Kokua due to crew limit hit
- Crew invites → new signups → paid conversions

---

## Future Enhancements

- [ ] **Multi-crew spot sharing**: Allocate spots to specific crews (not just private/crew)
- [ ] **Crew roles**: Admin, moderator, member with different permissions
- [ ] **Crew invites**: Magic links for crew invites (already in magic_link plan)
- [ ] **Crew analytics**: Leaderboards, activity stats
- [ ] **Premium tier**: Unlimited crews, advanced features

---

## Final Recommendations

### ✅ DO THIS:

1. **Tier Limits:**
   - Free: 1 crew (create or join), 3 members max
   - Kokua: 2 crews, 1 can be "Kokua upgraded" (5 members)

2. **Kokua Crew Upgrade:**
   - Checkbox at crew creation: "Use Kokua upgrade?"
   - Only 1 per Kokua user
   - Free users CAN join Kokua crews

3. **Downgrade Handling:**
   - Option A (user choice) + Option B (activity fallback)
   - 7-day grace period
   - Email notifications
   - Kokua crew → Free crew conversion (remove 2 members)

4. **Referral Tracking:**
   - Add `invited_by_user_id` if you want growth analytics
   - Optional: Can add later without data loss

### ⚠️ FUTURE CONSIDERATIONS:

1. **Kokua tier spot quota**: Define after validating free tier (currently TBD)
2. **Crew features**: What extra features do Kokua crews get?
3. **Multi-crew spot allocation**: Allow allocating spots to specific crews

### ❌ DON'T DO THIS:

1. **Immediate forced removal** on downgrade (bad UX)
2. **Delete crews** when user leaves (preserve data)
3. **Complex quota formulas** (keep it simple)

---

**Document Status:** ✅ READY FOR IMPLEMENTATION
**Last Updated:** January 6, 2026
**Next Steps:** Start with Phase 1 (Database Schema)
