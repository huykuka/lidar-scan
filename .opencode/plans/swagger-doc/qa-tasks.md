# Swagger API Documentation — QA Tasks

> **Feature**: `swagger-doc`  
> **Refs**: [`requirements.md`](requirements.md) · [`technical.md`](technical.md) · [`api-spec.md`](api-spec.md)  
> **Assignee**: `@qa`

Check off each box (`[ ]` → `[x]`) as work completes.

---

## Task Overview

This document outlines comprehensive QA testing tasks for the Swagger API Documentation feature. Testing focuses on documentation accuracy, API contract validation, and integration with existing functionality.

---

## Phase 1 — Documentation Accessibility

- [ ] **1.1** Verify Swagger UI is accessible at `http://localhost:8005/docs`
- [ ] **1.2** Verify ReDoc documentation is accessible at `http://localhost:8005/redoc`
- [ ] **1.3** Confirm OpenAPI JSON schema is available at `http://localhost:8005/openapi.json`
- [ ] **1.4** Test that documentation loads without authentication requirements
- [ ] **1.5** Verify CORS configuration allows frontend access to documentation endpoints
- [ ] **1.6** Test documentation accessibility from different browsers (Chrome, Firefox, Safari)

---

## Phase 2 — API Endpoint Coverage

### Core Endpoint Groups
- [ ] **2.1** System endpoints (`/api/v1/status`, `/api/v1/start`, `/api/v1/stop`)
- [ ] **2.2** Nodes endpoints (all CRUD operations under `/api/v1/nodes`)
- [ ] **2.3** Edges endpoints (all operations under `/api/v1/edges`)
- [ ] **2.4** Configuration endpoints (`/api/v1/config/*`)
- [ ] **2.5** Recordings endpoints (`/api/v1/recordings/*`)
- [ ] **2.6** Logs endpoints (`/api/v1/logs/*`)
- [ ] **2.7** Calibration endpoints (`/api/v1/calibration/*`)
- [ ] **2.8** LiDAR endpoints (`/api/v1/lidar/*`)
- [ ] **2.9** Assets endpoints (`/api/v1/assets/*`)
- [ ] **2.10** Topics endpoints (`/api/v1/topics/*`)

### Coverage Validation
- [ ] **2.11** Verify all REST endpoints are documented (no missing endpoints)
- [ ] **2.12** Confirm WebSocket endpoints are excluded from documentation
- [ ] **2.13** Test that static file mounts (`/recordings/*`, SPA `/`) are not documented
- [ ] **2.14** Verify metrics endpoints are noted as excluded (not yet implemented)

---

## Phase 3 — Schema Accuracy Testing

### Request/Response Model Validation
- [ ] **3.1** Test that documented request schemas match actual API expectations
- [ ] **3.2** Validate response schemas against actual API responses
- [ ] **3.3** Verify that Open3D types are excluded from detailed schemas
- [ ] **3.4** Test that binary endpoints show appropriate content types (not JSON schemas)
- [ ] **3.5** Confirm error response formats match documented `ErrorDetail` schema

### Data Type Verification
- [ ] **3.6** Test UUID field formats in node/edge/recording IDs
- [ ] **3.7** Verify timestamp formats follow ISO-8601 standard
- [ ] **3.8** Validate numeric constraints (ports: 1024-65535, etc.)
- [ ] **3.9** Test optional vs required field handling
- [ ] **3.10** Verify array and object nesting in complex schemas

---

## Phase 4 — Interactive Testing (Swagger UI)

### Try-It-Out Functionality
- [ ] **4.1** Test successful API calls through Swagger UI for each endpoint group
- [ ] **4.2** Validate error responses (400, 404, 409, 500) through interactive testing
- [ ] **4.3** Test file upload endpoints (configuration import, recording start)
- [ ] **4.4** Verify file download endpoints (recordings, logs, assets)
- [ ] **4.5** Test pagination parameters (logs, calibration history)

### Authentication & CORS
- [ ] **4.6** Confirm no authentication prompts appear in Swagger UI
- [ ] **4.7** Test cross-origin requests from Swagger UI work correctly
- [ ] **4.8** Verify that API calls from Swagger UI don't conflict with SPA

---

## Phase 5 — Documentation Quality

### Content Review
- [ ] **5.1** Review endpoint descriptions for clarity and accuracy
- [ ] **5.2** Validate that examples use realistic, concrete values
- [ ] **5.3** Test that tag grouping makes logical sense for API discovery
- [ ] **5.4** Verify that HTTP status codes are documented appropriately
- [ ] **5.5** Check that parameter descriptions are helpful and complete

### Tag Organization
- [ ] **5.6** Verify all 10 expected tag groups are present and correctly named
- [ ] **5.7** Test that endpoints are grouped logically under appropriate tags
- [ ] **5.8** Confirm tag descriptions accurately reflect their endpoint groups
- [ ] **5.9** Validate that WebSocket routes don't appear under any tags

---

## Phase 6 — Performance & Integration Testing

### Performance Impact
- [ ] **6.1** Measure API startup time impact (should be < 1ms overhead)
- [ ] **6.2** Test that documentation generation doesn't slow down API responses
- [ ] **6.3** Verify that Swagger UI loading doesn't affect SPA performance
- [ ] **6.4** Test concurrent access to docs and API endpoints

### Integration Validation
- [ ] **6.5** Confirm SPA still loads correctly at `/` after Swagger addition
- [ ] **6.6** Test that existing middleware (CORS, error handling) works unchanged
- [ ] **6.7** Verify that static file serving for recordings is unaffected
- [ ] **6.8** Test that WebSocket connections work normally

---

## Phase 7 — Edge Case & Error Handling

### URL Routing
- [ ] **7.1** Test that `/docs` doesn't serve SPA content on 404
- [ ] **7.2** Test that `/redoc` doesn't serve SPA content on 404
- [ ] **7.3** Test that `/openapi.json` returns JSON, not SPA HTML
- [ ] **7.4** Verify proper 404 handling for non-existent documentation URLs

### Error Scenarios
- [ ] **7.5** Test behavior when OpenAPI generation encounters errors
- [ ] **7.6** Validate graceful handling of malformed API requests through Swagger UI
- [ ] **7.7** Test documentation behavior during API server restart
- [ ] **7.8** Verify error responses match documented schemas

---

## Phase 8 — Cross-Platform & Browser Testing

### Browser Compatibility
- [ ] **8.1** Test Swagger UI functionality in Chrome
- [ ] **8.2** Test Swagger UI functionality in Firefox
- [ ] **8.3** Test Swagger UI functionality in Safari
- [ ] **8.4** Test ReDoc rendering across browsers
- [ ] **8.5** Verify mobile browser compatibility for documentation

### Platform Testing
- [ ] **8.6** Test documentation on development environment
- [ ] **8.7** Test documentation behavior in production-like environment
- [ ] **8.8** Verify HTTPS compatibility if applicable
- [ ] **8.9** Test documentation with different network configurations

---

## Phase 9 — Regression Testing

### Existing Functionality
- [ ] **9.1** Run full API test suite to ensure no regressions
- [ ] **9.2** Test frontend application end-to-end workflows
- [ ] **9.3** Verify WebSocket connections and streaming functionality
- [ ] **9.4** Test recording/playback functionality remains intact
- [ ] **9.5** Validate calibration workflows continue to work

### Backend Services
- [ ] **9.6** Test DAG node lifecycle (create, reload, delete)
- [ ] **9.7** Verify Open3D processing pipeline functionality
- [ ] **9.8** Test LiDAR device integration
- [ ] **9.9** Validate database operations (nodes, edges, recordings)
- [ ] **9.10** Test file system operations (assets, recordings, logs)

---

## Dependencies & Order

```
Phase 1 (Basic Access)
  └── Phase 2 (Coverage)
        ├── Phase 3 (Schema Accuracy)
        ├── Phase 4 (Interactive Testing)
        └── Phase 5 (Documentation Quality)
              ├── Phase 6 (Performance)
              ├── Phase 7 (Edge Cases)
              ├── Phase 8 (Cross-Platform)
              └── Phase 9 (Regression Testing)
```

> All phases depend on backend implementation being complete.

---

## Pre-PR Checklist

- [ ] All documented endpoints are functional and match schemas
- [ ] No regressions in existing API or frontend functionality  
- [ ] Swagger UI and ReDoc provide complete, accurate documentation
- [ ] WebSocket endpoints correctly excluded from REST documentation
- [ ] Performance impact is minimal (< 1ms startup overhead)
- [ ] Cross-browser compatibility verified
- [ ] Error handling and edge cases properly tested
- [ ] Integration testing passes for all major workflows

---

## Test Data & Environment Setup

### Required Test Environment
- Backend server running with all node types available
- Test LiDAR devices or simulators for sensor endpoints
- Sample recording files for testing download/playback endpoints
- Valid configuration files for import/export testing

### Test Data Requirements
- Valid node configurations for multiple sensor types
- Sample edge connections for DAG topology testing
- Test recordings with known frame counts and metadata
- Calibration test data with known sensor positions
- Log files with various log levels and modules

---

## Bug Reporting Template

When reporting issues, include:
- **Endpoint**: Which API endpoint or documentation section
- **Browser**: Browser type and version
- **Steps**: Exact steps to reproduce the issue
- **Expected**: What should happen according to documentation
- **Actual**: What actually happens
- **Impact**: Whether this affects API functionality or just documentation
- **Screenshots**: For Swagger UI/ReDoc visual issues

