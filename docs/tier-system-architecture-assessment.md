# Nana Nalu Tier System Architecture Assessment

**Date:** January 2, 2026
**Purpose:** Evaluate and recommend architecture for user tiers, authentication, payment integration, and public access features

---

## Executive Summary

This assessment analyzes the three-tier system (Free, Kokua, Admin) for the Nana Nalu surf spot tracking PWA. The document covers database schema design, authentication strategies for mobile-first PWAs, tier restriction parameters, and strategies for showcasing features to non-authenticated users during the beta phase.

**FINAL APPROVED TIER DESIGN: "Contribution Pool" Model**

| Tier | Spot Quota | Max Crew Members | Crew Spot Limit | Price |
|------|------------|------------------|-----------------|-------|
| **Free** | 3 spots | 3 members | None (contribution-based) | Free |
| **Kokua** | TBD | TBD | TBD | $5/mo |
| **Admin** | Unlimited | Unlimited | Unlimited | N/A |

**Key Design Decisions:**
- ✅ **Contribution Pool Model:** Each user has a spot quota they can allocate between private and crew
- ✅ **Dynamic Crew Capacity:** Crew spots = sum of all member contributions (no hard cap)
- ✅ **Viral Incentive:** Invite more members → more spots for everyone ("bring your own value")
- ✅ **Flexible Allocation:** Users can freely move spots between private↔crew anytime
- ✅ **Creator Ownership:** Spots always belong to creator; they leave with user if they exit crew
- ✅ Archiving system (free: 2 archived max, kokua: unlimited) to preserve historical data
- ✅ JWT-based auth with refresh tokens for PWA/mobile compatibility
- ✅ Demo spots (not global spots) for beta showcase—no moderation burden
- ✅ Bi-directional friendships required before crew invites (spam prevention)

---

## 1. Database Entity Structure

### 1.1 New Entities Required

#### `account_tiers` (Reference Table)
```sql
CREATE TABLE account_tiers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,  -- 'free', 'kokua', 'admin'
    display_name VARCHAR(100) NOT NULL, -- 'Free', 'Kokua Supporter', 'Admin'

    -- Contribution Pool Model (simplified)
    spot_quota INTEGER,                -- spots user can allocate (free: 3, NULL = unlimited)
    max_archived_spots INTEGER,        -- NULL = unlimited archived spots

    -- Crew limits
    max_crews_joined INTEGER,          -- how many crews user can join (free: 1)
    max_crew_members INTEGER,          -- max members per crew (free: 3)
    -- NOTE: No max_crew_spots - capacity is contribution-based (sum of member quotas)

    can_create_global_spots BOOLEAN DEFAULT FALSE,
    price_monthly_cents INTEGER,       -- NULL for admin, 0 for free
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Update `users` Table
```sql
ALTER TABLE users
ADD COLUMN tier_id INTEGER REFERENCES account_tiers(id) DEFAULT 1,  -- default to free
ADD COLUMN subscription_status VARCHAR(50),  -- 'active', 'cancelled', 'expired', 'trial', NULL
ADD COLUMN subscription_id VARCHAR(255),     -- Stripe subscription ID
ADD COLUMN subscription_current_period_end TIMESTAMP,
ADD COLUMN is_admin BOOLEAN DEFAULT FALSE,   -- quick admin check
ADD COLUMN created_at TIMESTAMP DEFAULT NOW(),
ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();
```

#### `crews` Table
```sql
CREATE TABLE crews (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    created_by_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    max_members INTEGER NOT NULL,        -- set at creation based on creator's tier
    -- NOTE: No max_spots - capacity is dynamic (sum of member contributions)
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_crew_name_per_user UNIQUE(created_by_id, name)
);
```

#### `crew_members` Table
```sql
CREATE TABLE crew_members (
    id SERIAL PRIMARY KEY,
    crew_id INTEGER REFERENCES crews(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'member',   -- 'creator', 'admin', 'member'
    joined_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT unique_crew_membership UNIQUE(crew_id, user_id)
);
```

#### `friendships` Table
```sql
CREATE TABLE friendships (
    id SERIAL PRIMARY KEY,
    requester_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    addressee_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'accepted', 'blocked'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT unique_friendship UNIQUE(requester_id, addressee_id),
    CONSTRAINT no_self_friendship CHECK (requester_id != addressee_id)
);
```

#### Update `surf_spots` Table
```sql
ALTER TABLE surf_spots
ADD COLUMN crew_id INTEGER REFERENCES crews(id) ON DELETE SET NULL,
ADD COLUMN is_demo BOOLEAN DEFAULT FALSE,  -- for beta showcase (admin-created)
ADD COLUMN allocation VARCHAR(20) DEFAULT 'private' CHECK (allocation IN ('private', 'crew')),
ADD COLUMN status VARCHAR(50) DEFAULT 'active';  -- 'active', 'archived' (for tier quota management)

-- Notes on allocation:
-- 'private': Only creator can see (crew_id should be NULL)
-- 'crew': Shared with crew members (crew_id should be set)
-- Users can freely change allocation between private↔crew

-- Add indexes for performance
CREATE INDEX idx_surf_spots_allocation ON surf_spots(allocation, status);
CREATE INDEX idx_surf_spots_crew ON surf_spots(crew_id) WHERE crew_id IS NOT NULL;
CREATE INDEX idx_surf_spots_user_status ON surf_spots(created_by_id, status);  -- for quota checks
CREATE INDEX idx_surf_spots_demo ON surf_spots(is_demo) WHERE is_demo = TRUE;
```

### 1.2 Entity Relationship Notes

- **User → Tier**: Many-to-one (many users share a tier)
- **User → Crew**: Many-to-many via `crew_members`
- **User → Friends**: Many-to-many via `friendships` (self-referencing)
- **Crew → Spots**: One-to-many (crew owns multiple shared spots)
- **User → Private Spots**: One-to-many (existing relationship via `created_by_id`)

---

## 2. Authentication Architecture for PWA/Mobile

### 2.1 Recommended Strategy: JWT with Refresh Tokens

**Why this approach:**
- ✅ Stateless authentication (scales well)
- ✅ Works seamlessly with PWAs and Capacitor iOS apps
- ✅ No CORS issues with properly configured tokens
- ✅ Offline capability support (store JWT in IndexedDB/SecureStorage)
- ✅ Mobile-friendly (no cookie complexities)

### 2.2 Implementation Pattern

```python
# Token Structure
ACCESS_TOKEN_EXPIRE = 15 minutes
REFRESH_TOKEN_EXPIRE = 7 days

# Storage
- Access Token: Memory (React state/context) + localStorage for PWA persistence
- Refresh Token: httpOnly cookie (web) OR SecureStorage (Capacitor iOS)
```

### 2.3 Auth Flow

```
1. Login → Issue access_token + refresh_token
2. Store access_token in memory/localStorage
3. Store refresh_token in httpOnly cookie (web) or SecureStorage (iOS)
4. Include access_token in Authorization header for API calls
5. On 401 → Attempt refresh with refresh_token
6. If refresh succeeds → New access_token
7. If refresh fails → Redirect to login
```

### 2.4 PWA-Specific Considerations

**Service Worker Caching:**
- Cache forecast data for offline viewing
- Don't cache authenticated endpoints
- Clear cache on logout

**iOS Capacitor Transition:**
- Use Capacitor's SecureStorage plugin for tokens
- Biometric authentication for re-authentication
- Handle token refresh in background

**Security:**
```python
# backend/core/security.py
- Use bcrypt/argon2 for password hashing
- Implement rate limiting on auth endpoints (5 attempts/15min)
- Add CSRF protection for cookie-based refresh tokens
- Rotate refresh tokens on use (optional, high security)
- Implement device fingerprinting for suspicious activity detection
```

### 2.5 Recommended Libraries

**Backend (FastAPI):**
- `python-jose[cryptography]` - JWT encoding/decoding
- `passlib[bcrypt]` - Password hashing
- `python-multipart` - Form data handling

**Frontend (React):**
- `@tanstack/react-query` - Token refresh & request retry logic
- `axios` - HTTP client with interceptors
- `@capacitor/secure-storage` - iOS secure token storage (when migrating)

---

## 3. Tier System Parameters: Contribution Pool Model

### 3.1 Core Concept

The **Contribution Pool Model** replaces the complex "solo vs crew" quota system with a single, portable spot quota that users can allocate freely between private and crew use.

```
┌─────────────────────────────────────────────────────────┐
│  FREE TIER - CONTRIBUTION POOL MODEL                    │
│                                                         │
│  Each user has: 3 spots (their "quota")                 │
│  Max crew size: 3 members                               │
│  Crew spot limit: None (sum of contributions)           │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  ALLOCATION IS FLEXIBLE                         │    │
│  │                                                 │    │
│  │  Option A: ███ (3 private, 0 crew)              │    │
│  │  Option B: ██░ (2 private, 1 crew)              │    │
│  │  Option C: █░░ (1 private, 2 crew)              │    │
│  │  Option D: ░░░ (0 private, 3 crew)              │    │
│  │                                                 │    │
│  │  User can change allocation anytime!            │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 3.2 How Crew Capacity Works

Crew spot capacity is **dynamic** based on what members contribute:

```
EXAMPLE: 3-Person Crew (Max for Free Tier)

Member A: Contributes 3 spots  →  ███
Member B: Contributes 2 spots  →  ██
Member C: Contributes 1 spot   →  █
                                  ──────
Total Crew Pool:               →  6 spots (all members can access)

Member A still has: 0 private spots (3 - 3 = 0)
Member B still has: 1 private spot  (3 - 2 = 1)
Member C still has: 2 private spots (3 - 1 = 2)
```

**Maximum potential for free tier crew:** 3 members × 3 spots = **9 shared spots**

### 3.3 Final Tier Parameters (APPROVED) - Contribution Pool Model

| Feature | Free | Kokua | Admin |
|---------|------|-------|-------|
| **Spot Quota** | 3 spots | TBD | Unlimited |
| **Allocation** | Freely split between private/crew | Same | Same |
| **Archived Spots** | 2 max | Unlimited | Unlimited |
| **Crews Joined** | 1 max | TBD | Unlimited |
| **Max Crew Members** | 3 | TBD | Unlimited |
| **Crew Spot Limit** | None (contribution-based) | Same | Same |
| **Observations** | Unlimited (on accessible spots) | Unlimited | Unlimited |
| **Demo Spots** | View only | View only | Create & manage |
| **Forecast History** | 3 days | 30 days | Unlimited |
| **Export Data** | No | Yes (CSV/JSON) | Yes |

### 3.4 Why This Model?

**Simplicity:**
- One number to remember: "I have 3 spots"
- No complex formulas or separate pools
- Clear mental model: "My quota, my choice how to use it"

**Viral Incentive:**
- Invite friends → more spots for everyone
- "Join our crew and bring your 3 spots!"
- Frames joining as **contributing value**, not just taking

**Flexibility:**
- Users choose their own balance (privacy vs sharing)
- Can adjust anytime as needs change
- No punishment for collaboration

**Ownership Clarity:**
- Spots always belong to creator
- Leave crew → your spots come with you
- No confusing "transfer" mechanics

### 3.5 Scenario Walkthrough

| Scenario | What Happens |
|----------|--------------|
| Solo user creates 3 spots | All private, quota full |
| User joins crew | Existing spots stay private (user chooses what to share) |
| User shares 2 spots to crew | 2 crew + 1 private, crew pool grows by 2 |
| User wants spot back from crew | Change allocation to private (crew loses that spot) |
| User leaves crew | All their crew spots become private again |
| 4th person tries to join 3-person crew | Rejected: "Crew is full (3/3 members)" |
| User tries to create 4th spot | Rejected: "Quota reached (3/3 spots)" |

### 3.6 Anti-Abuse Considerations

**Crew Size Cap (3 members):**
- Prevents large free-tier crews gaming the system
- Upgrade incentive: "Need bigger crew? Go Kokua"

**Spot Quota (3 spots):**
- Enough for core local rotation
- Creates upgrade pressure for serious users

**Single Crew Limit:**
- Prevents spreading quota across multiple crews
- Focus on one core community

---

## 4. Global Spots vs. Beta Showcase Alternatives

### 4.1 Your Idea: Global Spots

**Concept:** Admin-created spots visible to all users (including non-authenticated) with community observations

**Pros:**
- ✅ Showcases app functionality without account creation
- ✅ Builds community database of popular spots
- ✅ Reduces friction for new users exploring the app
- ✅ Content marketing potential (SEO for "Spot X forecast")

**Cons:**
- ❌ Spam/moderation burden (community observations on global spots)
- ❌ Reduces free tier incentive (why create account if global spots exist?)
- ❌ Conflicting with your 20-account beta limit (global spots defeat scarcity)
- ❌ Data quality concerns (unverified observations)
- ❌ Legal/liability issues (public surf conditions = potential lawsuits)

### 4.2 Straw Man Against Global Spots

**Argument:** "Global spots cannibalize paid features and create moderation hell"

1. **Monetization Killer:**
   - If global spots have good coverage, free users never hit limits
   - Why pay $5/mo for 20 private spots if 50 global spots exist?
   - Reduces urgency to create account during beta

2. **Spam & Quality:**
   - Reddit-style moderation requires significant time investment
   - Bad actors can pollute observations (fake reports, trolling)
   - Need content moderation system (flags, reports, admin review)
   - You're one person building this—moderation scales poorly

3. **Beta Scarcity Conflict:**
   - You want 20 beta accounts to test features
   - Global spots let anyone access forecasts without beta access
   - Defeats purpose of limited beta (feedback from committed users)

4. **Data Ownership Ambiguity:**
   - Who owns observations on global spots?
   - Can users export their contributions?
   - What happens if you sunset global spots later?

### 4.3 Alternative: Demo Spots (Recommended)

**Concept:** Admin-curated "demo spots" (3-5 famous breaks) visible without authentication, but READ-ONLY

**Implementation:**
```sql
-- surf_spots table
visibility = 'demo'  -- separate from 'global'
is_demo = TRUE
allow_observations = FALSE  -- no community contributions
```

**What Users See:**
- Interactive map showing demo spot markers
- Full forecast data (wave height, wind, tide, etc.)
- Historical forecast charts (last 7 days)
- Sample observations (curated by you, not user-generated)
- Prominent CTA: "Create account to track your own spots"

**Pros:**
- ✅ Showcases app features without spam risk
- ✅ No moderation burden (you control all content)
- ✅ Creates FOMO ("I can see Pipeline, but I want my local spot!")
- ✅ Clear upgrade path (demo → free account → kokua)
- ✅ Works with beta scarcity (view-only doesn't need beta access)
- ✅ SEO benefits still exist ("Nana Nalu Pipeline forecast")

**Cons:**
- ⚠️ Less community engagement (but you're too small for community features now)
- ⚠️ Requires you to maintain demo spot observations (but only 3-5 spots)

### 4.4 Other Showcase Alternatives

#### Option B: "Guest Mode" (Temporary Spot Creation)
- Non-authenticated users create 1 temporary spot
- Data expires after 24 hours
- Forces account creation to persist data
- **Issue:** Complex UX, bad first impression if data disappears

#### Option C: Video Demos + Screenshots
- Landing page with interactive demo videos
- Screenshot carousel showing features
- No actual app access without account
- **Issue:** Doesn't let users "play" with forecasts (less engaging)

#### Option D: Shared Demo Account
- Single "demo@nanalu.com" account anyone can use
- Pre-loaded with spots and observations
- Users can't modify data (read-only)
- **Issue:** Confusing UX, doesn't show personalization value

### 4.5 Recommendation: Demo Spots + Waitlist

**Phase 1 (Beta - 20 accounts):**
1. Create 3-5 demo spots (Pipeline, Mavericks, Teahupo'o, local Hawaii spot)
2. Show demo spots on public landing page (no login required)
3. Full forecast data visible, but read-only
4. CTA: "Join beta waitlist to create your own spots"
5. Collect emails for beta access rolling invites

**Phase 2 (Post-Beta):**
1. Keep demo spots as permanent feature
2. Open sign-ups for free tier
3. Demo spots become marketing tool (SEO, social sharing)
4. Users understand value before creating account

**Why This Works:**
- ✅ Balances showcase value with scarcity (beta limit maintained)
- ✅ No moderation burden during beta
- ✅ Builds waitlist for future growth
- ✅ Demonstrates app value without account friction
- ✅ Creates clear narrative: "See what's possible? Sign up to track YOUR spots"

---

## 5. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Implement `account_tiers` table with seed data
- [ ] Update `users` table with tier relationship
- [ ] Build JWT authentication system (access + refresh tokens)
- [ ] Create auth endpoints (register, login, logout, refresh)
- [ ] Add tier-based middleware for route protection

### Phase 2: Spot Ownership (Weeks 3-4)
- [ ] Update `surf_spots` table with visibility fields
- [ ] Implement private spot quotas (enforce in service layer)
- [ ] Build spot archiving system
- [ ] Create 3-5 demo spots for public showcase
- [ ] Add spot quota checks in surf spot service

### Phase 3: Social Features (Weeks 5-7)
- [ ] Implement `friendships` table and endpoints
- [ ] Build friend request/accept/reject flow
- [ ] Create `crews` and `crew_members` tables
- [ ] Implement crew creation (quota enforcement)
- [ ] Build crew invitation system
- [ ] Add crew spot contribution logic (separate from private spots)

### Phase 4: Payment Integration (Weeks 8-9)
- [ ] Integrate Stripe for Kokua tier subscriptions
- [ ] Implement subscription webhooks (payment success, cancellation, renewal)
- [ ] Build subscription management UI (upgrade, downgrade, cancel)
- [ ] Add subscription status checks in middleware
- [ ] Handle tier downgrades gracefully (archive excess spots, leave crews)

### Phase 5: Public Demo & Beta Launch (Week 10)
- [ ] Polish demo spot presentation (public landing page)
- [ ] Build beta waitlist system
- [ ] Invite 20 beta users
- [ ] Collect feedback on tier restrictions
- [ ] Iterate based on real usage patterns

---

## 6. Key Architectural Decisions

### 6.1 Quota Enforcement (Contribution Pool Model)

**Application Layer Implementation:**

```python
# services/surf_spot_service.py

async def can_create_spot(user: User) -> bool:
    """Simple check: does user have quota remaining?"""
    tier = await get_user_tier(user.id)

    # Admin: unlimited
    if tier.spot_quota is None:
        return True

    current_spots = await count_user_spots(user.id, status='active')
    return current_spots < tier.spot_quota


async def get_quota_status(user: User) -> dict:
    """Get user's current quota usage"""
    tier = await get_user_tier(user.id)
    current_spots = await count_user_spots(user.id, status='active')

    private_count = await count_user_spots(user.id, status='active', allocation='private')
    crew_count = await count_user_spots(user.id, status='active', allocation='crew')

    return {
        "quota": tier.spot_quota,
        "used": current_spots,
        "available": max(0, tier.spot_quota - current_spots) if tier.spot_quota else None,
        "private": private_count,
        "crew": crew_count
    }


async def create_surf_spot(user: User, spot_data: dict, allocation: str = 'private'):
    """Create a new surf spot"""
    if not await can_create_spot(user):
        quota = await get_quota_status(user)
        raise QuotaExceededError(
            f"Spot quota reached ({quota['used']}/{quota['quota']}). "
            f"Archive a spot or upgrade to Kokua for more!"
        )

    # If allocating to crew, verify user is in a crew
    crew_id = None
    if allocation == 'crew':
        crew = await get_user_crew(user.id)
        if not crew:
            raise NotInCrewError("Join a crew first to share spots")
        crew_id = crew.id

    # Create the spot
    spot = SurfSpot(
        created_by_id=user.id,
        allocation=allocation,
        crew_id=crew_id,
        **spot_data
    )
    await save(spot)
    return spot


async def change_allocation(user: User, spot_id: int, new_allocation: str):
    """Freely toggle spot between private and crew"""
    spot = await get_spot(spot_id)

    # Must own the spot
    if spot.created_by_id != user.id:
        raise NotOwnerError("You can only reallocate your own spots")

    if new_allocation == 'crew':
        crew = await get_user_crew(user.id)
        if not crew:
            raise NotInCrewError("Join a crew first to share spots")
        spot.crew_id = crew.id
    else:
        spot.crew_id = None

    spot.allocation = new_allocation
    await save(spot)


async def on_leave_crew(user: User, crew: Crew):
    """When user leaves crew, their spots become private"""
    user_crew_spots = await get_spots(
        created_by_id=user.id,
        crew_id=crew.id,
        allocation='crew'
    )

    for spot in user_crew_spots:
        spot.allocation = 'private'
        spot.crew_id = None
        await save(spot)
```

**Why This Is Simpler:**
- ✅ Single quota check: `current_spots < tier.spot_quota`
- ✅ No complex formulas or pool calculations
- ✅ Allocation is just a flag, not a separate quota system
- ✅ Clear ownership: spots always belong to creator

### 6.2 Spot Ownership Model

**Recommendation: Creator-Owned (Portable)**

Spots always belong to creator, allocation just changes visibility:
- `allocation = 'private'`: Only creator can see
- `allocation = 'crew'`: All crew members can see

When user changes allocation or leaves crew:
- Spots stay with creator (not transferred to crew)
- User can freely toggle allocation anytime
- Leaving crew automatically converts crew spots → private

**Why:**
- Simpler mental model: "These are MY spots, I choose who sees them"
- No anxiety about "losing" spots to crew
- Encourages sharing (no permanent commitment)

### 6.3 Friend System: Bi-directional vs. Uni-directional

**Recommendation: Bi-directional (Like Facebook)**

Friendship requires acceptance:
```sql
-- User A sends request
INSERT INTO friendships (requester_id, addressee_id, status) VALUES (A, B, 'pending');

-- User B accepts
UPDATE friendships SET status = 'accepted' WHERE id = ...;

-- Query friends (either direction)
SELECT * FROM friendships
WHERE (requester_id = user_id OR addressee_id = user_id)
AND status = 'accepted';
```

**Why:**
- Prevents spam invites to crews
- Users control who sees their spot activity
- More privacy-conscious (important for spot secrecy)

---

## 7. Migration Path for Existing Users (Future)

When you eventually have users, handling tier changes:

### Upgrade (Free → Kokua):
- ✅ Immediate access to new quotas
- ✅ No data loss
- ✅ Show success message with new capabilities

### Downgrade (Kokua → Free):
**Grace Period Approach (Recommended):**
1. User cancels subscription
2. Remain on Kokua until billing period ends
3. 7 days before downgrade, email warning:
   - "You have 15 private spots, free tier allows 4"
   - "Please archive 11 spots or renew subscription"
4. On downgrade date:
   - Auto-archive oldest/least-viewed spots over limit
   - Preserve data (can re-activate if they upgrade again)
   - Leave crews over limit (stay as member, can't create new)

---

## 8. Security Considerations

### 8.1 Tier Bypass Prevention

**Attack Vector:** User manipulates client-side tier checks

**Mitigation:**
```python
# NEVER trust client-sent tier information
# ALWAYS query database for user's current tier

@require_auth
async def create_spot(request):
    user = request.user  # from JWT
    tier = await db.query(Tier).join(User).filter(User.id == user.id).first()

    # Enforce server-side
    if await spot_count(user.id) >= tier.max_private_spots:
        raise QuotaExceeded
```

### 8.2 Subscription Status Verification

**Attack Vector:** User cancels subscription but retains access

**Mitigation:**
```python
# Check subscription_status on every protected route
# Sync with Stripe webhooks (single source of truth)

@require_kokua_tier
async def advanced_feature(request):
    user = request.user

    if user.subscription_status != 'active':
        # Check Stripe for current status
        stripe_sub = stripe.Subscription.retrieve(user.subscription_id)

        if stripe_sub.status != 'active':
            # Downgrade user
            await downgrade_to_free(user)
            raise SubscriptionRequired
```

### 8.3 Rate Limiting (Prevent Abuse)

```python
# Protect expensive operations
@rate_limit("5/minute")  # 5 spot creations per minute
async def create_spot(request):
    ...

@rate_limit("100/hour")  # 100 observations per hour
async def create_observation(request):
    ...
```

---

## 9. Analytics & Metrics to Track

### Tier Conversion Metrics:
- Free tier → Kokua conversion rate
- Time to first upgrade (days from registration)
- Churn rate (Kokua → Free cancellations)
- Reactivation rate (Free → Kokua → Free → Kokua)

### Engagement Metrics:
- Spots created by tier (do free users hit limits?)
- Crew participation rate (% of users in a crew)
- Observations per user per tier
- Feature usage (which features drive upgrades?)

### Beta Success Metrics:
- Waitlist growth rate
- Beta user activation (% who create spots)
- Demo spot view → signup conversion
- Friend invites sent per user

---

## 10. Final Recommendations Summary

### ✅ DO THIS:

1. **Tiered System (Contribution Pool Model):**
   - Free: 3 spots (allocate freely), 1 crew (3 members max)
   - Kokua ($5/mo): TBD (more spots, larger crews)
   - Admin: Unlimited everything

2. **Auth:**
   - JWT with refresh tokens
   - httpOnly cookies for web, SecureStorage for iOS
   - Implement token refresh logic with axios interceptors

3. **Spots:**
   - Single quota per tier (user allocates between private/crew)
   - Users can freely toggle allocation anytime
   - Archive system for spots (doesn't count toward quota)
   - Demo spots (3-5 famous breaks) for public showcase

4. **Crews:**
   - Creator-owned model (spots stay with creator, leave with them)
   - Dynamic capacity (sum of member contributions, no hard cap)
   - Friend system required before crew invites
   - Bi-directional friendships (requires acceptance)

5. **Beta Strategy:**
   - Demo spots on public landing page
   - Waitlist for beta access
   - 20 beta users for focused feedback
   - Roll out social features (crews) after core features stable

### ⚠️ FUTURE CONSIDERATIONS:

1. **Kokua tier parameters:** Define when free tier is validated
2. **Global spots:** Save for post-MVP, use demo spots for now
3. **Multi-crew support:** Consider for Kokua tier

### ❌ DON'T DO THIS:

1. **Global spots with community observations during beta** (moderation nightmare)
2. **Complex quota formulas** (keep it simple: one number per tier)
3. **Uni-directional friendships** (enables spam, hurts privacy)
4. **Unlimited free tier features** (kills monetization)

---

## Appendix A: Sample Tier Seed Data (Contribution Pool Model)

```sql
-- FINAL APPROVED tier parameters with contribution pool model
INSERT INTO account_tiers (
    name,
    display_name,
    spot_quota,
    max_archived_spots,
    max_crews_joined,
    max_crew_members,
    can_create_global_spots,
    price_monthly_cents,
    is_active
)
VALUES
    -- Free: 3 spots, 2 archived, 1 crew with 3 members max
    ('free', 'Free', 3, 2, 1, 3, FALSE, 0, TRUE),

    -- Kokua: TBD (placeholder values)
    ('kokua', 'Kokua Supporter', 10, NULL, 3, 6, FALSE, 500, TRUE),

    -- Admin: unlimited everything
    ('admin', 'Admin', NULL, NULL, NULL, NULL, TRUE, NULL, TRUE);

-- Notes:
-- spot_quota: total spots user can create (allocate freely between private/crew)
-- max_crew_members: max members per crew (when user creates crew)
-- No max_crew_spots field - crew capacity is contribution-based (sum of members' allocated spots)
-- NULL = unlimited
```

## Appendix B: JWT Token Structure

```json
{
  "access_token": {
    "user_id": 123,
    "email": "user@example.com",
    "tier": "free",
    "is_admin": false,
    "exp": 1704123456  // 15 min expiry
  },
  "refresh_token": {
    "user_id": 123,
    "token_family": "abc-123",  // for rotation
    "exp": 1704729600  // 7 day expiry
  }
}
```

## Appendix C: Stripe Webhook Events to Handle

```python
WEBHOOK_EVENTS = {
    'customer.subscription.created': handle_subscription_created,
    'customer.subscription.updated': handle_subscription_updated,
    'customer.subscription.deleted': handle_subscription_cancelled,
    'invoice.payment_succeeded': handle_payment_success,
    'invoice.payment_failed': handle_payment_failed,
}
```

---

## Quick Reference: Implementation Checklist (Contribution Pool Model)

### Phase 1: Database & Auth (Weeks 1-2)
- [ ] Create `account_tiers` table with contribution pool fields (spot_quota, max_crew_members)
- [ ] Seed tier data (Free: 3 spots, 3 crew members, see Appendix A)
- [ ] Add tier fields to `users` table (tier_id, subscription_status, etc.)
- [ ] Implement JWT auth (access: 15min, refresh: 7 days)
- [ ] Add `allocation` and `status` fields to `surf_spots`

### Phase 2: Spot Quota Management (Weeks 3-4)
- [ ] Implement `can_create_spot()` function (simple quota check)
- [ ] Implement `get_quota_status()` for UI display
- [ ] Build spot archiving endpoints (archive, unarchive)
- [ ] Implement `change_allocation()` for private↔crew toggling
- [ ] Create 3-5 demo spots for public landing page
- [ ] Add helpful error messages ("Quota reached (3/3 spots)")

### Phase 3: Social Features (Weeks 5-7)
- [ ] Create `friendships` table (bi-directional, requires acceptance)
- [ ] Build friend request flow (send, accept, reject)
- [ ] Create `crews` and `crew_members` tables
- [ ] Implement crew creation (free: 1 crew, 3 members max)
- [ ] Build `on_leave_crew()` to convert spots back to private
- [ ] Build crew invitation system (friends-only)
- [ ] Build crew spot visibility (aggregate member contributions)

### Phase 4: Payment (Weeks 8-9)
- [ ] Integrate Stripe checkout for Kokua tier ($5/mo)
- [ ] Handle webhooks (subscription.created, updated, deleted)
- [ ] Build subscription management UI
- [ ] Implement graceful downgrade (archive excess spots)
- [ ] Define Kokua tier parameters

### Phase 5: Beta Launch (Week 10)
- [ ] Polish demo spots on public landing page
- [ ] Create beta waitlist
- [ ] Invite 20 beta users
- [ ] Monitor crew contribution patterns
- [ ] Track tier conversion metrics
- [ ] Iterate based on feedback

---

**End of Assessment**

**Document Status:** ✅ FINAL APPROVED - Contribution Pool Model
**Last Updated:** January 2, 2026
**Tier Design:**
- **Free:** 3 spots (allocate freely private/crew) + 2 archived | 1 crew: 3 members max
- **Kokua:** TBD
- **Key Feature:** Contribution-based crew capacity (sum of member allocations, no hard cap)

*Ready to start implementation? See Phase 1 checklist above.*
