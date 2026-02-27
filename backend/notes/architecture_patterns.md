# Architecture Patterns — nana-nalu Backend

## Pattern Name

**Layered Service Architecture** (also called Service Layer Pattern)

This is a standard enterprise architecture pattern documented in Martin Fowler's *Patterns of Enterprise Application Architecture* and widely adopted across Spring Boot (Java), ASP.NET Core (C#), NestJS (TypeScript), and Django REST Framework (Python).

FastAPI doesn't enforce this pattern, but its `Depends()` DI system maps directly to constructor injection in opinionated frameworks like Spring or NestJS.

---

## Layer Responsibilities

```
Route (thin)
  ├── Depends(get_current_user)     → authentication
  ├── Depends(get_*_service)        → one service call
  └── return SuccessResponse(await service.method(user_id, ...))

Service (all business logic)
  ├── authorization (_validate_access, _validate_ownership)
  ├── business rules (quotas, matching, evaluation)
  ├── orchestration (multiple repos, other services)
  └── session.commit()

Repository (data access only)
  └── single-table queries, JOINs, no business logic
```

### Route Layer

- Extracts authentication via FastAPI dependencies (`get_current_user`, `require_admin`)
- Makes **exactly one** service call per endpoint
- Wraps result in `SuccessResponse`
- No `if/else`, no orchestration, no direct repo access
- Does NOT handle authorization (that's the service's job)

### Service Layer

- Owns ALL business logic: authorization, validation, orchestration
- Receives `user_id` (not tokens or request objects) from routes
- Composes repositories and other services via constructor injection
- Calls `session.commit()` when mutations succeed
- Raises domain exceptions (`SpotPermissionError`, `CrewQuotaExceededError`)

### Repository Layer

- Pure data access — single-table or multi-table queries
- No business logic, no authorization checks
- Returns ORM models or raw query results
- Raises data-layer exceptions (`NotFoundError`)

---

## Key Rules

### 1. Authentication vs Authorization

| Concern | Where | How |
|---------|-------|-----|
| **Authentication** ("Who are you?") | Route layer | `Depends(get_current_user)` extracts JWT |
| **Authorization** ("Can you do this?") | Service layer | `_validate_ownership()`, `_validate_spot_access()` |

Authentication is stateless token verification — belongs in the request pipeline.
Authorization requires querying relationships (ownership, crew membership, tier limits) — that's business logic.

### 2. When Routes Call Services vs Repos Directly

**Original approach**: Routes called repos directly for simple CRUD to avoid "expensive" service instantiation.

**Corrected understanding**: Service instantiation is effectively free. FastAPI's `Depends()` is a reference-passing tree, not a resource-creation tree:

- DB connection pools are app-level singletons (created at startup)
- Redis clients are app-level singletons (created at startup)
- Settings are `@lru_cache` cached (loaded once)
- DB sessions are checked out from the existing pool (microseconds)
- Repos and services just store references (`self.x = x`)
- FastAPI deduplicates dependencies within a request (same session shared across all repos)

**Updated rule**: Always go through the service layer. The only reason to skip is if there truly is zero business logic AND there never will be (rare).

### 3. Route Has One Service Call

If a route needs to call two service methods or coordinate results between them, that orchestration belongs in a service:

```python
# BAD — orchestration in route
@router.post("/complex")
async def do_thing(svc_a: A = Depends(...), svc_b: B = Depends(...)):
    result_a = await svc_a.step_one()
    result_b = await svc_b.step_two(result_a)
    return SuccessResponse(data=result_b)

# GOOD — orchestration in service
@router.post("/complex")
async def do_thing(svc: OrchestratingService = Depends(...)):
    result = await svc.do_complex_thing()
    return SuccessResponse(data=result)
```

### 4. Service Composition

Services can depend on other services. Two patterns:

**Hierarchical** — one service uses another as a tool:
```python
class ConditionProfileService:
    def __init__(self, forecast_service: ForecastService, ...):
```

**Orchestrating** — new service coordinates peers:
```python
class OnboardingService:
    def __init__(self, auth_service, crew_service, spot_service, ...):
```

### 5. Rule of Three for Extraction

- 1 inline ownership check in a route? Fine temporarily.
- 2 similar checks across routes? Tolerable.
- 3+ duplicate checks? Extract to service `_validate_*` method.

Prevents premature abstraction while ensuring logic doesn't stay scattered.

---

## FastAPI DI Cost Model

Understanding why service instantiation is free:

| Resource | When Created | Lifetime | Cost per Request |
|----------|-------------|----------|-----------------|
| DB connection pool | App startup (`init_app`) | App-level singleton on `app.state` | 0 — already exists |
| Redis client | App startup | App-level singleton on `app.state` | 0 — already exists |
| Settings | First load (`@lru_cache`) | Cached forever | 0 — cached |
| DB session | `get_async_db_session` | Per-request, from pool | Microseconds (pool checkout) |
| Repository | `get_*_repository` | Per-request | Nanoseconds (`self.session = session`) |
| Service | `get_*_service` | Per-request | Nanoseconds (stores references) |

The entire DI tree for a service with 6 dependencies resolves in roughly the time it takes to create a Python dict with 6 keys.

---

## Testing Implications

This architecture directly informs what's worth testing:

| Layer | Has testable logic? | Test approach |
|-------|-------------------|---------------|
| Routes | No — just glue | Skip or cover via integration |
| Services (matching, evaluation) | Yes — business logic | Unit test (construct with `None` deps for pure methods) |
| Services (authorization) | Yes — access control | Integration test (real DB for relationship queries) |
| Repos (complex queries) | Yes — JOINs, filters | Integration test (real DB) |
| Repos (simple CRUD) | No — ORM handles it | Skip |
| Schemas (validators) | Yes — edge cases | Unit test |

Full testing strategy documented in `tests/TEST_PLAN.md`.

---

## References

- Martin Fowler, *Patterns of Enterprise Application Architecture* — Service Layer pattern
- Robert Martin, *Clean Architecture* — dependency rule (outer layers depend inward)
- Spring Boot docs — Controller / Service / Repository convention
- FastAPI docs — Dependency Injection system
