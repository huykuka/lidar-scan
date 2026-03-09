# Swagger API Documentation — Frontend Tasks

> **Feature**: `swagger-doc`  
> **Refs**: [`requirements.md`](requirements.md) · [`technical.md`](technical.md) · [`api-spec.md`](api-spec.md)  
> **Assignee**: `@fe-dev`

Check off each box (`[ ]` → `[x]`) as work completes.

---

## Task Overview

This document outlines the minimal frontend integration tasks for the Swagger API Documentation feature. Since this is primarily a backend documentation feature, frontend changes are limited to testing and validation.

---

## Phase 1 — Testing Integration

- [x] **1.1** Verify that Angular SPA at `/` still loads correctly after Swagger UI is added
- [x] **1.2** Test that Angular routing is not affected by the new `/docs` and `/redoc` endpoints
- [x] **1.3** Confirm that existing API calls from Angular components continue to work unchanged
- [x] **1.4** Verify CORS configuration allows Angular development server to access documented endpoints

---

## Phase 2 — API Discovery Validation

- [x] **2.1** Navigate to `http://localhost:8005/docs` and verify all API endpoints are visible
- [x] **2.2** Use Swagger UI "Try it out" feature to test key endpoints used by the Angular frontend:
  - [x] `GET /api/v1/status` (system health check)
  - [x] `GET /api/v1/nodes` (node list for canvas)
  - [x] `GET /api/v1/nodes/status/all` (runtime status display)
  - [x] `POST /api/v1/nodes/reload` (configuration refresh)
- [x] **2.3** Verify that API response schemas in Swagger UI match what Angular components expect
- [x] **2.4** Test ReDoc interface at `http://localhost:8005/redoc` for clean documentation viewing

---

## Phase 3 — Development Workflow Enhancement

- [x] **3.1** Update development documentation to reference Swagger UI for API exploration
- [x] **3.2** Verify that new developers can understand API contracts from Swagger UI without code diving
- [x] **3.3** Test that frontend mock data matches the documented response schemas
- [x] **3.4** Confirm WebSocket endpoints (`/ws/{topic}`, `/logs/ws`) are correctly excluded from REST docs

---

## Phase 4 — Performance & Integration Verification

- [x] **4.1** Confirm that Angular build process is not affected by backend Swagger changes
- [x] **4.2** Verify that production static file serving still works correctly
- [x] **4.3** Test that Angular error handling works with documented error response formats
- [x] **4.4** Validate that no new console errors appear in browser dev tools

---

## Dependencies & Order

```
Phase 1 (Basic Integration)
  └── Phase 2 (API Discovery)
        └── Phase 3 (Workflow Enhancement)
              └── Phase 4 (Performance Verification)
```

> All phases depend on backend Swagger implementation being complete.

---

## Pre-PR Checklist

- [x] Angular SPA loads correctly at `/` route
- [x] No new browser console errors or warnings
- [x] Swagger UI at `/docs` displays all expected API endpoints
- [x] ReDoc at `/redoc` provides clean documentation viewing
- [x] Existing Angular API integrations continue to work unchanged
- [x] Frontend mock data aligns with documented API schemas
- [x] Development workflow documentation updated to reference Swagger UI

---

## Notes for Frontend Developers

### No Code Changes Required
This feature is purely backend documentation - no Angular component modifications are needed.

### API Contract Reference
Use the Swagger UI at `/docs` to verify that existing frontend API calls match the documented contracts. This helps identify any discrepancies between what the frontend expects and what the backend actually provides.

### Testing Focus
Primary focus should be on regression testing to ensure that the addition of Swagger documentation doesn't break existing functionality.

### Future Benefits
Once complete, new developers can use Swagger UI to understand API contracts without needing to read backend code or reverse-engineer API behavior from frontend usage.
