# Swagger API Documentation - Requirements

## Feature Overview

Add comprehensive Swagger/OpenAPI documentation to the LiDAR Standalone backend to improve developer experience and API discoverability. The documentation will expose all REST API endpoints with interactive testing capabilities through FastAPI's built-in Swagger UI and ReDoc interfaces.

## User Stories

**As a frontend developer**, I want to explore available API endpoints interactively so that I can understand request/response schemas without reading backend code.

**As a third-party developer**, I want to access standardized API documentation so that I can integrate with the LiDAR Standalone system effectively.

**As a backend developer**, I want auto-generated API documentation so that endpoint documentation stays in sync with code changes automatically.

**As a QA engineer**, I want to test API endpoints directly from the browser so that I can validate functionality without external tools.

**As a system integrator**, I want both interactive (Swagger UI) and clean reading (ReDoc) documentation formats so that I can choose the best format for different use cases.

## Acceptance Criteria

### Core Documentation Features
- [x] Swagger UI available at `/docs` route with interactive endpoint testing
- [x] ReDoc documentation available at `/redoc` route with clean, printable format
- [x] All REST API endpoints in `/api/v1/` are automatically documented
- [ ] Request/response schemas are properly documented using Pydantic models
- [ ] HTTP status codes and error responses are documented for each endpoint
- [ ] API versioning is clearly indicated in the documentation

### Technical Requirements
- [ ] Use FastAPI's default Swagger UI without custom branding or themes
- [ ] Document only standard Python types (int, str, dict, list) and Pydantic models
- [ ] Exclude specialized Open3D types from detailed schema documentation
- [ ] No authentication required - documentation publicly accessible
- [ ] Documentation automatically updates when API code changes

### API Coverage
- [ ] Node management endpoints (`/api/v1/nodes/*`)
- [ ] System status endpoints (`/api/v1/system/*`)
- [ ] Configuration endpoints (`/api/v1/config/*`)
- [ ] LiDAR device endpoints (`/api/v1/lidar/*`)
- [ ] Recording endpoints (`/api/v1/recordings/*`)
- [ ] Asset management endpoints (`/api/v1/assets/*`)
- [ ] Calibration endpoints (`/api/v1/calibration/*`)
- [ ] Logging endpoints (`/api/v1/logs/*`)
- [ ] Performance metrics endpoints (`/api/metrics/*`)

### Documentation Quality
- [ ] Each endpoint has a clear summary and description
- [ ] Request parameters are documented with types and constraints
- [ ] Response models show expected data structures
- [ ] Example request/response payloads are provided where helpful
- [ ] API tags are used to group related endpoints logically

### Performance & Integration
- [ ] Documentation generation adds minimal overhead (<1ms) to API startup
- [ ] Documentation remains functional with existing CORS and middleware setup
- [ ] Static file serving for Angular SPA is not affected
- [ ] WebSocket endpoints are excluded from REST documentation (separate protocol)

## Out of Scope

### Excluded Features
- **Custom Branding**: No custom logos, colors, or styling - use default FastAPI appearance
- **Authentication**: No access restrictions or login requirements for documentation
- **Open3D Documentation**: Specialized Open3D types (PointCloud, TriangleMesh) details excluded
- **WebSocket Protocol**: LIDR binary WebSocket protocol not covered (separate documentation)
- **DAG Workflow Documentation**: Node orchestration details excluded from API docs
- **Performance Monitoring Details**: Basic metrics endpoint coverage only, no detailed monitoring docs

### Technical Exclusions
- **Custom OpenAPI Extensions**: No custom schema extensions or vendor-specific features
- **Advanced Swagger Features**: No try-it-out customization, custom validators, or plugins
- **External Documentation Generation**: No PDF export, external doc site generation
- **API Mocking**: No built-in mock server or test data generation

### Future Considerations
- WebSocket protocol documentation may be added as separate feature
- DAG workflow documentation could be separate technical documentation
- Custom branding may be added if project branding guidelines are established
- Authentication restrictions could be added if security requirements change

## Dependencies

- **FastAPI**: Leverage built-in OpenAPI generation and Swagger UI integration
- **Pydantic V2**: Ensure all API models use Pydantic for automatic schema generation
- **Existing API Structure**: Work with current `/api/v1/` routing and middleware setup
- **CORS Configuration**: Documentation must work with existing CORS policy