"""
Node registry for the debug_save operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="debug_save",
    display_name="Save PCD",
    category="operation",
    description="Saves point cloud to PCD files",
    use_case="Capture frames for offline analysis or ground-truth collection — e.g. record a sequence of scans during a test run for later replay, or export individual frames to validate algorithm behaviour in a notebook.",
    icon="save",
    websocket_enabled=False,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="folder", label="Folder", type="string", default="session1",
                       help_text="Directory to write output PCD files"),
        PropertySchema(name="prefix", label="File Prefix", type="string", default="pcd",
                       help_text="Filename prefix for saved PCD files"),
        PropertySchema(name="max_keeps", label="Max Keeps", type="number", default=10, min=1,
                       help_text="Maximum number of files to keep"),
        # FTP section
        PropertySchema(name="ftp_enabled", label="Enable FTP Upload", type="boolean", default=False,
                       help_text="Upload each saved file to an FTP server"),
        PropertySchema(name="ftp_host", label="FTP Host", type="string", default="",
                       help_text="FTP server hostname or IP address",
                       depends_on={"ftp_enabled": [True]}),
        PropertySchema(name="ftp_port", label="FTP Port", type="number", default=21, min=1, max=65535,
                       help_text="FTP server port",
                       depends_on={"ftp_enabled": [True]}),
        PropertySchema(name="ftp_user", label="FTP Username", type="string", default="",
                       depends_on={"ftp_enabled": [True]}),
        PropertySchema(name="ftp_password", label="FTP Password", type="string", default="",
                       depends_on={"ftp_enabled": [True]}),
        PropertySchema(name="ftp_remote_dir", label="Remote Directory", type="string", default="/",
                       help_text="Remote directory to upload files into",
                       depends_on={"ftp_enabled": [True]}),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("debug_save")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import OperationNode
    config = node.get("config", {})
    op_config = config.copy()
    op_config.pop("op_type", None)
    throttle_ms = op_config.pop("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    return OperationNode(
        manager=service_context,
        node_id=node["id"],
        op_type="debug_save",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
