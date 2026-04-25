"""
Worker process for SICK Visionary 3D camera data acquisition.

Runs as an isolated multiprocessing.Process that:
1. Connects to the camera control channel (CoLa protocol)
2. Opens a TCP/UDP streaming channel
3. Continuously receives BLOB frames, parses depth/intensity/confidence
4. Converts to 3D point clouds and pushes payloads to the shared data queue

The worker is self-contained so that a crash does not bring down the
main FastAPI event loop.
"""
import logging
import os
import sys
import time
from multiprocessing import Event, Queue
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _add_sdk_to_path() -> None:
    """Ensure the sick_visionary_python_base package is importable.

    The SDK is expected to live at ``<repo_root>/sick_visionary_python_base/``
    or be installed as a regular package.
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[4]
    sdk_path = repo_root / "sick_visionary_python_base"
    if sdk_path.is_dir() and str(sdk_path.parent) not in sys.path:
        sys.path.insert(0, str(sdk_path.parent))


def visionary_worker_process(
    sensor_id: str,
    hostname: str,
    streaming_port: int,
    protocol: str,
    cola_protocol: str,
    control_port: int,
    is_stereo: bool,
    data_queue: "Queue[Any]",
    stop_event: "Event",
) -> None:
    """Main entry point executed inside a ``multiprocessing.Process``.

    Args:
        sensor_id:      Unique node identifier.
        hostname:       Camera IP address.
        streaming_port: TCP/UDP streaming port (default 2114).
        protocol:       ``"TCP"`` or ``"UDP"``.
        cola_protocol:  ``"ColaB"`` or ``"Cola2"``.
        control_port:   CoLa control port (default 2122 for Cola2, 2112 for ColaB).
        is_stereo:      True for stereo cameras (Visionary-S, Visionary-B Two).
        data_queue:     Shared queue for pushing payloads to the main process.
        stop_event:     Multiprocessing event signalling graceful shutdown.
    """
    _add_sdk_to_path()

    try:
        from sick_visionary_python_base.Stream import Streaming
        from sick_visionary_python_base.Streaming.Data import Data
        from sick_visionary_python_base.Control import Control
    except ImportError as exc:
        logger.error(
            f"[{sensor_id}] sick_visionary_python_base is not available: {exc}"
        )
        _push_event(data_queue, sensor_id, "error", f"SDK not installed: {exc}")
        return

    from app.modules.visionary.point_cloud import (
        depth_to_point_cloud_stereo,
        depth_to_point_cloud_tof,
    )

    streaming: Any = None
    control: Any = None

    try:
        # --- Control channel ---------------------------------------------------
        logger.info(f"[{sensor_id}] Connecting control channel to {hostname}:{control_port} ({cola_protocol})")
        control = Control(hostname, cola_protocol, control_port=control_port, timeout=5)
        control.open()
        control.login(Control.USERLEVEL_SERVICE, control.calculatePasswordHash("CUST_STD"))
        logger.info(f"[{sensor_id}] Control channel connected")

        # --- Streaming channel -------------------------------------------------
        logger.info(f"[{sensor_id}] Opening streaming channel to {hostname}:{streaming_port} ({protocol})")
        streaming = Streaming(hostname, streaming_port, protocol=protocol)
        if protocol == "UDP":
            streaming.openStream(server_address=("", streaming_port))
        else:
            streaming.openStream()
        logger.info(f"[{sensor_id}] Streaming channel open")

        _push_event(data_queue, sensor_id, "connected", "Camera streaming started")

        my_data = Data()
        frame_count = 0

        # --- Acquisition loop --------------------------------------------------
        while not stop_event.is_set():
            try:
                streaming.sendBlobRequest()
                streaming.getFrame()
                raw_frame = streaming.frame

                if raw_frame is None:
                    continue

                my_data.read(raw_frame, convertToMM=True)

                if not my_data.hasDepthMap:
                    continue

                cam = my_data.cameraParams
                cam2world = np.array(cam.cam2worldMatrix, dtype=np.float64).reshape(4, 4)

                depth = my_data.depthmap.distance
                intensity = my_data.depthmap.intensity
                confidence = my_data.depthmap.confidence

                if is_stereo:
                    points = depth_to_point_cloud_stereo(
                        dist_data=depth,
                        intensity_data=intensity,
                        confidence_data=confidence,
                        width=cam.width,
                        height=cam.height,
                        fx=cam.fx,
                        fy=cam.fy,
                        cx=cam.cx,
                        cy=cam.cy,
                        cam2world=cam2world,
                    )
                else:
                    points = depth_to_point_cloud_tof(
                        dist_data=depth,
                        intensity_data=intensity,
                        confidence_data=confidence,
                        width=cam.width,
                        height=cam.height,
                        fx=cam.fx,
                        fy=cam.fy,
                        cx=cam.cx,
                        cy=cam.cy,
                        k1=cam.k1,
                        k2=cam.k2,
                        f2rc=cam.f2rc,
                        cam2world=cam2world,
                    )

                if points is None or len(points) == 0:
                    continue

                frame_count += 1
                payload = {
                    "lidar_id": sensor_id,
                    "processed": False,
                    "points": points,
                    "count": len(points),
                    "timestamp": time.time(),
                }

                try:
                    data_queue.put(payload, block=False)
                except Exception:
                    pass  # queue full — drop frame

                if frame_count % 100 == 1:
                    logger.debug(
                        f"[{sensor_id}] Frame #{frame_count}: {len(points)} points"
                    )

            except Exception as frame_exc:
                logger.warning(f"[{sensor_id}] Frame error: {frame_exc}")
                _push_event(data_queue, sensor_id, "error", str(frame_exc))
                if stop_event.is_set():
                    break
                time.sleep(0.5)

    except Exception as exc:
        logger.error(f"[{sensor_id}] Worker fatal error: {exc}", exc_info=True)
        _push_event(data_queue, sensor_id, "error", str(exc))
    finally:
        if streaming is not None:
            try:
                streaming.closeStream()
            except Exception:
                pass
        if control is not None:
            try:
                control.close()
            except Exception:
                pass
        _push_event(data_queue, sensor_id, "disconnected", "Worker stopped")
        logger.info(f"[{sensor_id}] Visionary worker stopped.")


def _push_event(
    data_queue: "Queue[Any]",
    sensor_id: str,
    event_type: str,
    message: str,
) -> None:
    """Push a lifecycle event (connected/disconnected/error) into the queue."""
    try:
        data_queue.put(
            {
                "lidar_id": sensor_id,
                "event_type": event_type,
                "message": message,
                "timestamp": time.time(),
            },
            block=False,
        )
    except Exception:
        pass
