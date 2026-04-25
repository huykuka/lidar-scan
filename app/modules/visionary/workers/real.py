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

    Resolution order:
    1. ``VISIONARY_SDK_PATH`` environment variable (absolute path to the cloned repo)
    2. ``<repo_root>/sick_visionary_python_base/`` (auto-discovered)
    3. Already installed as a Python package (no action needed)
    """
    from pathlib import Path

    env_path = os.environ.get("VISIONARY_SDK_PATH")
    if env_path:
        p = Path(env_path).resolve()
        if p.is_dir() and str(p.parent) not in sys.path:
            sys.path.insert(0, str(p.parent))
        return

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

    # Suppress verbose per-frame SDK logging ("Reading binary segment", etc.)
    logging.getLogger("root").setLevel(logging.WARNING)
    logging.getLogger("sick_visionary_python_base").setLevel(logging.WARNING)

    from app.modules.visionary.point_cloud import StereoProjector, ToFProjector

    streaming: Any = None
    control: Any = None

    try:
        # --- Control channel ---------------------------------------------------
        logger.info(f"[{sensor_id}] Connecting control channel to {hostname}:{control_port} ({cola_protocol})")
        control = Control(hostname, cola_protocol, control_port=control_port, timeout=5)
        control.open()
        control.login(Control.USERLEVEL_SERVICE, "CUST_SERV")
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
        projector = None  # built lazily from first frame's camera params

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

                # Build projector once (pixel grids + distortion LUTs are constant)
                if projector is None:
                    cam = my_data.cameraParams
                    cam2world = np.array(
                        cam.cam2worldMatrix, dtype=np.float64
                    ).reshape(4, 4)
                    if is_stereo:
                        projector = StereoProjector(
                            cam.width, cam.height,
                            cam.fx, cam.fy, cam.cx, cam.cy,
                            cam2world,
                        )
                    else:
                        projector = ToFProjector(
                            cam.width, cam.height,
                            cam.fx, cam.fy, cam.cx, cam.cy,
                            cam.k1, cam.k2, cam.f2rc,
                            cam2world,
                        )

                depth = my_data.depthmap.distance
                intensity = my_data.depthmap.intensity
                confidence = my_data.depthmap.confidence

                points = projector.project(depth, intensity, confidence)

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
