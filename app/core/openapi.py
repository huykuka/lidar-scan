"""OpenAPI tag metadata for Swagger/ReDoc documentation."""

OPENAPI_TAGS: list[dict] = [
    {"name": "System",        "description": "Lifecycle control and health checks for the pipeline engine."},
    {"name": "Nodes",         "description": "Read-only access and live-action toggles for DAG processing nodes. Node creation, update, and deletion is performed atomically via PUT /api/v1/dag/config."},
    {"name": "Edges",         "description": "Read-only access to directed connections between DAG nodes. Edge creation and deletion is performed atomically via PUT /api/v1/dag/config."},
    {"name": "Configuration", "description": "Full-graph import/export and validation. Allows backup and restore of the entire node-edge topology."},
    {"name": "Recordings",    "description": "Start, stop, list, and download point-cloud recordings."},
    {"name": "Logs",          "description": "Access and stream application logs. Live streaming via GET /api/v1/logs/ws WebSocket."},
    {"name": "Calibration",   "description": "ICP multi-sensor calibration. Trigger alignment, accept/reject results, rollback."},
    {"name": "LiDAR",         "description": "SICK LiDAR device profiles and configuration validation."},
    {"name": "PCD Injection", "description": "Multipart PCD file upload for injecting point cloud data into the DAG."},
    {"name": "Assets",        "description": "Static image assets served directly from the lidar module bundle."},
    {"name": "Topics",        "description": "Introspection of registered WebSocket topics and single-frame HTTP snapshots."},
    {"name": "Results",       "description": "Persistent storage and retrieval of application node results."},
    {"name": "DAG",           "description": "Atomic DAG configuration save/load. PUT /dag/config replaces all nodes and edges in one transaction."},
    {"name": "Host Monitor",  "description": "Host system metrics for troubleshooting: CPU, memory, disk, network."},
]
