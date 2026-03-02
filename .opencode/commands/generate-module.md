# Generate Module Command

## Name

`generate-module`

## Description

Generate a new pluggable module for the LiDAR point cloud processing system with complete boilerplate code, schema definitions, and factory registration.

## Usage

```
/generate-module <module_name> <description> [--type=<sensor|fusion|operation>]
```

### Arguments

- **module_name** (required): Short, lowercase, snake_case name for the module (e.g., `radar`, `thermal_fusion`, `voxel_filter`)
- **description** (required): One-line description of the module's purpose
- **--type** (optional): Module type - one of: `sensor`, `fusion`, `operation`. If not specified, the agent will ask you.

### Examples

```bash
# Generate a sensor module for radar data
/generate-module radar "Process radar sensor data streams" --type=sensor

# Generate a fusion module (agent will ask for type if not specified)
/generate-module multi_sensor_fusion "Fuse LiDAR, radar, and camera data"

# Generate an operation module
/generate-module noise_filter "Remove noise using statistical methods" --type=operation
```

## What This Command Does

This command will:

1. **Load the generation skill** - Activate the `generate-module` skill with comprehensive module architecture guidelines
2. **Determine module type** - Ask the user to select sensor/fusion/operation if not specified
3. **Gather configuration** - Ask about properties, dependencies, and special requirements
4. **Generate file structure** - Create all necessary files:
   - `app/services/modules/<module_name>/__init__.py`
   - `app/services/modules/<module_name>/registry.py`
   - `app/services/modules/<module_name>/<node_class>.py`
   - Supporting files as needed (workers, operations, etc.)
5. **Implement boilerplate** - Fill in complete, working code based on the module type
6. **Create tests** - Generate a basic test file with fixtures and examples
7. **Verify integration** - Test that the module imports and registers correctly

## Module Types

### Sensor Modules

For interfacing with hardware or data sources:
- Spawn multiprocessing workers
- Handle UDP packets or file I/O
- Push data to orchestrator queue
- Manage lifecycle (start/stop workers)

**Examples**: LiDAR sensors, radar, cameras, playback from files

### Fusion Modules

For combining multiple data streams:
- Receive input from multiple upstream nodes
- Buffer latest frames from each source
- Merge data when all sources are ready
- Use enable/disable for state management

**Examples**: Multi-sensor fusion, point cloud merging, data aggregation

### Operation Modules

For processing and transforming data:
- Apply algorithms to point clouds
- Use Open3D or NumPy operations
- Highly composable (chain multiple together)
- Support dynamic configuration

**Examples**: Filtering, clustering, segmentation, feature extraction

## Generated File Structure

```
app/services/modules/<module_name>/
├── __init__.py              # Public API exports
├── registry.py              # Schema definition & factory builder
├── <node_class>.py          # Main node implementation
├── (workers/)               # For sensor modules: process functions
├── (operations/)            # For operation modules: algorithm implementations
└── tests/
    └── test_<module>.py     # Unit tests
```

## After Generation

The agent will:

1. Show you the generated files
2. Verify the module imports successfully
3. Test that `discover_modules()` registers it
4. Confirm the factory can create instances
5. Provide next steps for customization

## Customization Points

After generation, you can customize:

- **Properties**: Add/modify configuration parameters in `registry.py`
- **Processing logic**: Implement your algorithm in the node or operation class
- **Worker processes**: For sensors, customize the worker function
- **Status metrics**: Add custom metrics to `get_status()`
- **WebSocket topics**: Enable streaming to the frontend
- **Recording support**: Add recorder integration

## Related Commands

- `/test-module <module_name>` - Run tests for a specific module
- `/list-modules` - Show all registered modules
- `/module-docs <module_name>` - Show documentation for a module

## Skill Reference

This command uses the `generate-module` skill located at `.opencode/skills/generate-module/SKILL.md`.
