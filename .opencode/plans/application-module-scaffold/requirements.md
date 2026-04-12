# Application Module Scaffold - Requirements

## Feature Overview

Create a new **DAG node type** under `app/modules/application/` that integrates into the existing node orchestration system. Application nodes are specialized DAG nodes designed for higher-level processing tasks (e.g., object detection, analytics, event processing) that consume point cloud data from upstream nodes and participate in the standard DAG routing and lifecycle management.

The initial deliverable is a "Hello World" example application node demonstrating the full integration pattern, following the conventions established by existing modules (`lidar`, `pipeline`, `fusion`, `flow_control`).

## User Stories

**As a developer**, I want to:
- Create new application-level DAG nodes under `app/modules/application/` using a consistent base class pattern
- Have application nodes automatically discovered and registered via the existing `discover_modules()` system
- Define node schemas that appear in the Angular flow-canvas UI with configurable properties
- Implement nodes that receive data from upstream DAG nodes via `on_input(payload)`
- Use lifecycle methods (`start()`, `stop()`) managed by the NodeManager orchestrator
- Leverage built-in logging, configuration validation, and error handling
- Write pytest tests that verify nodes integrate correctly with the DAG pipeline

**As a system architect**, I want:
- Application nodes to follow the same architectural patterns as sensor, operation, and fusion nodes
- Automatic registration via `registry.py` with `NodeFactory` and `node_schema_registry`
- Full compatibility with the NodeManager orchestrator (routing, throttling, status reporting, WebSocket broadcasting)
- Clear separation: application nodes are for high-level logic, not low-level point cloud operations

## Acceptance Criteria

### Directory Structure
- [x] Create `app/modules/application/` with the following structure:
  ```
  app/modules/application/
  ├── __init__.py              # Empty or minimal package marker
  ├── registry.py              # Schema + factory registration (loaded via discover_modules)
  ├── base_node.py             # Abstract base class ApplicationNode(ModuleNode)
  └── hello_world/             # Example application node implementation
      ├── __init__.py
      └── node.py              # HelloWorldNode class
  ```

### Base Node Implementation (`base_node.py`)
Must provide:
- [x] Abstract base class `ApplicationNode(ModuleNode)` extending `app.services.nodes.base_module.ModuleNode`
- [x] Inherit all required `ModuleNode` interface methods:
  - `async def on_input(payload: Dict[str, Any])` - Receive data from upstream nodes
  - `def emit_status() -> NodeStatusUpdate` - Return standardized status
  - `def start(data_queue, runtime_status)` - Lifecycle initialization
  - `def stop()` - Lifecycle cleanup
- [x] Add application-specific helper methods or utilities (if needed)
- [x] Full type hints and docstrings following existing code patterns

### Registry Module (`registry.py`)
Must include:
- [x] Import statements:
  ```python
  from app.services.nodes.node_factory import NodeFactory
  from app.services.nodes.schema import NodeDefinition, PropertySchema, PortSchema, node_schema_registry
  ```
- [x] Register `NodeDefinition` for "hello_world" node type:
  - `type`: "hello_world"
  - `display_name`: "Hello World App"
  - `category`: "application"
  - `description`: Short description
  - `icon`: Material icon name (e.g., "celebration")
  - `websocket_enabled`: True (streams output data)
  - `properties`: At least one configurable property (e.g., `message` string, `interval` number)
  - `inputs`: Single input port
  - `outputs`: Single output port
- [x] Define factory builder function:
  ```python
  @NodeFactory.register("hello_world")
  def build_hello_world(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
  ```
- [x] Builder extracts config from `node["config"]`, handles `throttle_ms`, returns `HelloWorldNode` instance
- [x] Follows the exact pattern from `app/modules/lidar/registry.py` and `app/modules/pipeline/registry.py`

### Hello World Node Implementation (`hello_world/node.py`)
- [x] Implement `HelloWorldNode` class extending `ApplicationNode` (or directly `ModuleNode`)
- [x] Constructor signature: `__init__(self, manager, node_id, name, config, throttle_ms=0)`
- [x] Store required attributes:
  - `self.id = node_id`
  - `self.name = name`
  - `self.manager = manager`
  - `self.config = config` (dict with user-defined properties)
  - `self.logger = get_logger(__name__)`
- [x] Implement `async def on_input(self, payload: Dict[str, Any])`:
  - Log received payload (at INFO level)
  - Extract `points`, `timestamp`, `node_id` from payload
  - Perform simple processing (e.g., append custom metadata, count points)
  - Forward result via `self.manager.forward_data(self.id, new_payload)`
  - Demonstrate async/await operation (e.g., `await asyncio.sleep(0)`)
- [x] Implement `def emit_status() -> NodeStatusUpdate`:
  - Return `NodeStatusUpdate` with:
    - `node_id=self.id`
    - `operational_state=OperationalState.RUNNING`
    - Optional `application_state` showing custom status
- [x] Implement `def start(self, data_queue=None, runtime_status=None)`:
  - Log startup message with node name and config
- [x] Implement `def stop(self)`:
  - Log shutdown message
- [x] Include comprehensive docstrings and type hints

### Testing Infrastructure
- [x] Create pytest test suite in `tests/modules/application/test_hello_world.py`
- [x] Test coverage must include:
  - **Node instantiation**: Create HelloWorldNode with mock manager
  - **Configuration handling**: Verify config properties are stored correctly
  - **Data flow**: Call `on_input(payload)` and verify:
    - Payload is processed
    - `manager.forward_data()` is called with correct arguments
    - Async execution works correctly
  - **Status reporting**: Call `emit_status()` and validate structure
  - **Lifecycle**: Call `start()` and `stop()`, verify logging
  - **Integration**: Mock the NodeManager and verify node can receive/forward data
- [x] Use pytest-asyncio for async test support
- [x] Use `unittest.mock` for mocking NodeManager dependencies
- [x] Tests run independently without external services or database

### Integration with DAG System
- [x] Node type `"hello_world"` registered in `NodeFactory._registry`
- [x] Node schema registered in `node_schema_registry` (appears in UI node palette)
- [x] Registry loaded automatically via `discover_modules()` at startup
- [x] Node can be instantiated via `NodeFactory.create(node_data, service_context, edges)`
- [x] Node participates in standard DAG routing:
  - Receives data via `on_input()` when upstream nodes forward to it
  - Can forward data to downstream nodes via `manager.forward_data()`
  - Respects `throttle_ms` configuration (handled by NodeManager)
- [x] WebSocket broadcasting works (when `websocket_enabled=True`)
- [x] Status aggregation works (via `emit_status()`)

### Code Quality
- [x] All code must include:
  - Comprehensive docstrings (module, class, method level)
  - Type hints on all function signatures
  - Inline comments for complex logic only
- [x] Follow existing project conventions:
  - Import organization matching other module registries
  - Naming conventions (snake_case for methods, PascalCase for classes)
  - Error handling patterns from the codebase
  - Logging via `app.core.logging.get_logger()`

## Out of Scope

The following are explicitly **NOT** part of this initial scaffold:

- **Standalone/CLI Execution**: Application nodes are DAG nodes only, not standalone apps
- **Non-DAG Entrypoints**: No independent runners, CLI harnesses, or main() functions
- **FastAPI Endpoints**: No REST API routes for direct HTTP access
- **Angular UI Components**: No frontend dashboard or visualization (schema registration is sufficient)
- **Database Persistence**: Configuration comes from the existing NodeModel SQLite tables
- **Production Applications**: Only "Hello World" example; real applications (object detection, etc.) come later
- **Advanced Processing**: Example node performs minimal processing (logging, forwarding)
- **Multiprocessing Workers**: No worker process spawning (unlike sensor nodes)
- **WebSocket Topic Management**: Handled automatically by NodeManager
- **Performance Monitoring Integration**: No metrics collection (future feature)
- **README/Documentation Files**: Only inline code comments and docstrings
- **Custom Orchestrator**: Use existing NodeManager, no separate application manager

## Technical Constraints

1. **Python Version**: Must support Python 3.10+
2. **Base Class**: Must extend `app.services.nodes.base_module.ModuleNode` (or a subclass)
3. **Registration**: Must register via `@NodeFactory.register()` and `node_schema_registry.register()`
4. **Discovery**: Registry must be in `app/modules/application/registry.py` for `discover_modules()` to find it
5. **Async Framework**: Use asyncio, compatible with existing FastAPI event loop
6. **Logging**: Use `app.core.logging.get_logger()` from existing infrastructure
7. **Testing**: Pytest with pytest-asyncio plugin
8. **Import Path**: Node must be importable as `from app.modules.application.hello_world.node import HelloWorldNode`
9. **No External Dependencies**: Use only packages already in project (no new requirements.txt entries)
10. **Schema Compliance**: `NodeDefinition` must match the structure in `app.services.nodes.schema.py`

## Definition of Done

- [x] `app/modules/application/registry.py` exists and registers `hello_world` node schema + factory ✅ DONE
- [x] `app/modules/application/base_node.py` provides `ApplicationNode` base class (if needed, or use `ModuleNode` directly) ✅ DONE
- [x] `app/modules/application/hello_world/node.py` contains working `HelloWorldNode` implementation ✅ DONE
- [x] `HelloWorldNode` implements all required `ModuleNode` interface methods ✅ DONE
- [x] Pytest suite in `tests/modules/application/test_hello_world.py` passes 100% ✅ 67/67 tests pass
- [x] Tests cover: instantiation, config, data flow, status, lifecycle, DAG integration ✅ DONE
- [x] Node type appears in `NodeFactory._registry` after `discover_modules()` runs ✅ VERIFIED
- [x] Node schema appears in `node_schema_registry.get_all()` ✅ VERIFIED
- [x] Can create node instance via `NodeFactory.create()` with valid `node_data` ✅ VERIFIED
- [x] Node can receive data via `on_input()` and forward via `manager.forward_data()` ✅ VERIFIED
- [x] All code includes type hints and docstrings ✅ DONE
- [x] Code follows existing project conventions from other modules ✅ DONE (zero divergence)
- [x] No linting errors or type checking failures ✅ ruff: zero errors; mypy: only pre-existing repo-wide issues
- [x] Example demonstrates: config loading, async on_input, status emission, lifecycle hooks, DAG routing ✅ DONE

## Example Usage (Post-Implementation)

Once implemented, a developer should be able to:

1. **Via Angular UI**: Add "Hello World App" node to flow canvas, configure properties, connect to upstream nodes
2. **Via Database**: Insert node record with `type="hello_world"` and `config={"message": "test"}`
3. **Via NodeManager**: Orchestrator loads node automatically during `load_config()`, routes data to it
4. **Via Pytest**: Run `pytest tests/modules/application/` to verify all functionality

## Success Metrics

✓ Application module follows **exact same registration pattern** as `lidar`, `pipeline`, `fusion`, `flow_control`  
✓ `discover_modules()` loads `app/modules/application/registry.py` without errors  
✓ NodeFactory can instantiate `HelloWorldNode` from persisted config  
✓ Node integrates seamlessly with existing DAG orchestration (routing, lifecycle, status)  
✓ 100% test coverage on all interface methods  
✓ Zero architectural divergence from existing module patterns
