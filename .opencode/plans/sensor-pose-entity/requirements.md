# Feature: Unified Sensor Pose Entity

## Feature Overview

Refactor all sensor pose data (position: x, y, z; orientation: roll, pitch, yaw) from scattered individual fields into a single unified `Pose` entity/data type. This change must be applied consistently across the entire stack:

- **Python Backend**: Models, validation, DAG processing, database schema
- **API Layer**: Request/response contracts, serialization
- **Angular Frontend**: TypeScript interfaces, forms, state management, UI controls
- **Database**: Schema migration, storage format

All scattered pose fields (whether flat properties like `sensor_x`, `sensor_y`, or nested but inconsistent structures) will be **replaced and removed**. No deprecated, transitional, or legacy fields remain after implementation.

**Additional UI Enhancement**: The sensor form will be augmented with:
- A single **Reset Pose** button that sets all pose values to zero (x=0, y=0, z=0, roll=0, pitch=0, yaw=0)
- **Synergy UI `syn-range` sliders** for roll, pitch, and yaw angle adjustment (replacing any previous input controls)

## User Stories

### As a Backend Developer
- I want all sensor pose data represented as a single `Pose` object in Python models so that I can handle position and orientation as one cohesive entity throughout the DAG and API logic.
- I want the database schema to store pose as a single structured field (JSON or composite type) so that queries and migrations are straightforward.

### As a Frontend Developer
- I want a TypeScript `Pose` interface/type that mirrors the backend contract so that sensor state management is type-safe and consistent.
- I want the sensor configuration form to use Synergy UI `syn-range` sliders for roll, pitch, yaw so that angle adjustments are intuitive and visually consistent with the design system.
- I want a single Reset Pose button that zeroes all six pose values in one action so that users can quickly reset sensor alignment.

### As a System Administrator / End User
- I want all sensor pose values (position and orientation) to be grouped together in the API and UI so that configuration is clear and unambiguous.
- I want the ability to reset all pose values to their default (zero) state with a single button click so that I can quickly restore a neutral sensor position.
- I want angle controls (roll, pitch, yaw) to provide smooth range sliders with clear visual feedback so that precise adjustments are easier.

### As a QA Engineer
- I want strict validation on all pose fields (x, y, z in millimeters; roll, pitch, yaw in degrees -180° to +180°) so that invalid data is rejected at the API boundary and UI.
- I want the migration to be a clean breaking change (no backward compatibility) so that test cases are simpler and the codebase has no legacy code paths.

## Acceptance Criteria

### Backend (Python + Database)

- [ ] **Pose Entity Created**: A `Pose` class/model is defined with six fields:
  - `x`, `y`, `z` (type: float, unit: millimeters)
  - `roll`, `pitch`, `yaw` (type: float, unit: degrees, range: -180° to +180°)
- [ ] **Validation Enforced**: Backend validates:
  - `x`, `y`, `z` must be numeric (floats)
  - `roll`, `pitch`, `yaw` must be numeric floats within [-180, +180] degrees
  - Invalid values return HTTP 422 with descriptive error messages
- [ ] **Database Schema Updated**: Sensor table stores pose as a single structured field (JSON column or composite type), not as six separate columns
- [ ] **All Models Refactored**: All Pydantic models, SQLAlchemy models, and DAG node logic use the `Pose` type exclusively
- [ ] **No Legacy Fields Remain**: All scattered pose fields (e.g., `sensor_x`, `sensor_y`, `sensor_roll`, etc.) are removed from:
  - Database schema
  - Python models
  - API response serialization
  - DAG processing logic

### API Layer

- [ ] **API Contract Updated**: All sensor-related endpoints (GET, POST, PUT, PATCH) accept/return pose as a single nested object:
  ```json
  {
    "id": "sensor-1",
    "name": "Front LiDAR",
    "pose": {
      "x": 0.0,
      "y": 0.0,
      "z": 0.0,
      "roll": 0.0,
      "pitch": 0.0,
      "yaw": 0.0
    }
  }
  ```
- [ ] **Breaking Change Migration**: Endpoints **do not** accept old flat pose fields (e.g., `sensor_x`, `sensor_y`). Clients must send the new format.
- [ ] **OpenAPI/Swagger Updated**: API documentation reflects the new `Pose` schema with validation constraints documented (units, ranges)

### Frontend (Angular + UI)

- [x] **TypeScript Pose Interface**: A `Pose` interface/type is defined matching the backend contract:
  ```typescript
  interface Pose {
    x: number; // millimeters
    y: number; // millimeters
    z: number; // millimeters
    roll: number; // degrees, -180 to +180
    pitch: number; // degrees, -180 to +180
    yaw: number; // degrees, -180 to +180
  }
  ```
- [x] **All Frontend Code Refactored**: All Angular components, services, and state management use the `Pose` type exclusively
- [x] **No Legacy Fields Remain**: Remove all scattered pose properties from:
  - TypeScript interfaces
  - Angular reactive forms
  - State signals/stores
  - API service layer
- [x] **Sensor Form UI Updated**:
  - Roll, pitch, yaw controls replaced with **Synergy UI `syn-range` sliders**
  - Sliders configured with:
    - `min="-180"`
    - `max="180"`
    - `step="1"` (or finer granularity if needed)
    - Value labels display current angle in degrees (e.g., "45°")
  - X, Y, Z inputs remain numeric fields with unit labels ("mm")
- [x] **Reset Pose Button Added**:
  - Single button labeled "Reset Pose" added to sensor form
  - Clicking button sets all pose values to zero: `{ x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 }`
  - Button styled consistently with Synergy UI (e.g., `syn-button` variant)
  - No individual "reset x", "reset y", etc. buttons—one unified action

### Validation & Error Handling

- [x] **Frontend Validation**: Angular form validators enforce:
  - X, Y, Z are numeric
  - Roll, pitch, yaw are numeric and within [-180, +180] degrees
  - Form is invalid if any constraint is violated; submit button is disabled
- [ ] **Backend Validation**: FastAPI Pydantic models enforce the same constraints; return HTTP 422 with field-specific error messages
- [x] **User Feedback**: Validation errors display inline near the offending field with clear messaging (e.g., "Roll must be between -180° and +180°")

### Data Migration

- [ ] **Migration Strategy Documented**: Since this is a **breaking change**, a migration guide is created documenting:
  - Users must manually update sensor configurations
  - Old pose fields are no longer accepted
  - Example of old vs. new format provided
- [ ] **No Backward Compatibility**: The system does **not** attempt to read or auto-convert old flat pose fields. Any sensor data with the old format must be updated manually or re-created.

### Testing & QA

- [ ] **Unit Tests**: All new `Pose` validation logic covered by unit tests (backend and frontend)
- [ ] **Integration Tests**: API endpoints tested with valid and invalid pose payloads
- [ ] **UI Tests**: Sensor form behavior tested:
  - Synergy UI sliders update pose values correctly
  - Reset Pose button zeroes all fields
  - Validation errors appear when out-of-range values are entered
- [ ] **E2E Tests**: Full user workflow tested (create sensor → configure pose → reset pose → save → verify stored data)

### Documentation

- [ ] **API Documentation**: Swagger/OpenAPI spec updated with `Pose` schema, units, and validation rules
- [ ] **User Guide**: Migration guide created for users with existing sensor data
- [ ] **Developer Docs**: Internal docs updated to reflect the `Pose` entity structure and usage patterns

## Out of Scope

- **Automatic Migration of Legacy Data**: The system will **not** include automatic conversion logic for old pose field formats. Users must manually update configurations.
- **Pose Inheritance or Templates**: This feature does not introduce pose presets or inheritance mechanisms (e.g., "copy pose from sensor A to sensor B"). That would be a separate feature.
- **Coordinate Frame Transformations**: This feature does not add coordinate system conversion logic (e.g., ENU to NED). Pose values are stored and displayed as-is.
- **Advanced Angle Input Modes**: Only `syn-range` sliders for angles are in scope. Additional input modes (e.g., quaternion input, Euler angle order selection) are out of scope.
- **Undo/Redo for Pose Changes**: Undo/redo functionality for form edits is not part of this feature.
- **Pose Visualization in 3D Scene**: Visual representation of sensor pose in the Three.js scene is out of scope (may exist separately but is not part of this refactor).

## User-Facing Impacts

### Breaking Changes
- **API**: All sensor endpoints now require pose as a nested `pose` object. Old flat fields (e.g., `sensor_x`, `sensor_roll`) are no longer accepted.
- **Data Storage**: Sensors stored in the database with old pose field formats will fail validation and must be manually updated or re-created.

### UI Changes
- **Sensor Configuration Form**:
  - Roll, Pitch, Yaw inputs are now Synergy UI range sliders (visual change)
  - New "Reset Pose" button appears in the form
  - All pose fields are now visually grouped together (if not already)
- **Validation Feedback**: Users will see inline validation errors if they attempt to set angles outside the -180° to +180° range

### Workflow Changes
- **Reset Pose**: Users can now reset all six pose values with one button click instead of manually clearing each field
- **Angle Adjustment**: Slider-based angle input may change the interaction pattern for users accustomed to text input (though text input may still be supported via Synergy UI slider features)

## Technical Constraints

- **Units**: X, Y, Z in millimeters; Roll, Pitch, Yaw in degrees (not radians)
- **Angle Range**: Roll, Pitch, Yaw constrained to [-180, +180] degrees (backend and frontend validation)
- **No Legacy Support**: Zero tolerance for old pose field formats after migration—clean break only
- **Synergy UI Dependency**: Frontend must use `syn-range` component from the Synergy Design System

## Dependencies

- **Synergy UI**: `syn-range` component must be available and properly integrated in the Angular app
- **Database Migration Tooling**: Backend must support schema migration (e.g., Alembic for SQLAlchemy) to update the sensor table
- **API Versioning** (Optional): If API versioning exists, this change would bump the major version (breaking change)

## Success Metrics

- **Zero Legacy Fields**: No scattered pose fields remain in backend models, database schema, API contracts, or frontend code
- **100% Validation Coverage**: All pose field constraints (units, ranges) are enforced in both backend and frontend
- **UI Consistency**: All angle inputs use Synergy UI `syn-range` sliders; Reset Pose button is consistently styled
- **Developer Feedback**: Engineering team confirms the `Pose` entity simplifies sensor configuration logic and reduces boilerplate

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Breaking Change Impact**: Existing sensor data becomes invalid | Provide clear migration guide; consider adding a migration CLI tool (optional) |
| **Synergy UI Slider Bugs**: `syn-range` component may have issues with boundary values (-180, +180) | Test slider behavior thoroughly; file issues with Synergy UI team if bugs found |
| **Frontend/Backend Mismatch**: Pose validation logic differs between layers | Share validation logic via OpenAPI schema; write contract tests |
| **User Confusion**: Users accustomed to old pose fields may struggle with new format | Provide clear documentation, error messages, and migration examples |

---

**Next Steps**: 
1. Architecture agent (`@architecture`) to design the `Pose` entity structure, database schema, and API contract in `technical.md`
2. Architecture agent to define the API specification in `api-spec.md`
3. Backend and frontend dev agents to create task breakdowns in `backend-tasks.md` and `frontend-tasks.md`
