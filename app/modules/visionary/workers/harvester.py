"""
Worker process for SICK Visionary AP cameras via GigE Vision (Harvester/GenTL).

Uses the ``harvesters`` Python library with SICK's GenIStreamC GenTL producer
(.cti file) to acquire frames from Visionary AP camera models:
  - Visionary-T Mini AP
  - Visionary-B Two
  - Visionary-S AP

The worker is self-contained so that a crash does not bring down the main
FastAPI event loop.
"""
import logging
import time
from multiprocessing import Event, Queue
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


def harvester_worker_process(
    sensor_id: str,
    cti_path: str,
    camera_ip: str,
    is_stereo: bool,
    data_queue: "Queue[Any]",
    stop_event: "Event",
) -> None:
    """Main entry point executed inside a ``multiprocessing.Process``.

    Args:
        sensor_id:  Unique node identifier.
        cti_path:   Absolute path to the GenIStreamC ``.cti`` producer file.
        camera_ip:  IP address of the SICK Visionary camera (used to select the correct device).
        is_stereo:  True for stereo cameras (Visionary-S AP, Visionary-B Two).
        data_queue: Shared queue for pushing payloads to the main process.
        stop_event: Multiprocessing event signalling graceful shutdown.
    """
    try:
        from harvesters.core import Harvester
    except ImportError as exc:
        logger.error(f"[{sensor_id}] harvesters package not installed: {exc}")
        _push_event(data_queue, sensor_id, "error", f"harvesters not installed: {exc}")
        return

    from app.modules.visionary.point_cloud import (
        depth_to_point_cloud_stereo,
        depth_to_point_cloud_tof,
    )

    h: Optional[Any] = None
    ia: Optional[Any] = None

    try:
        h = Harvester()
        h.add_file(cti_path)
        h.update()

        if not h.device_info_list:
            msg = f"No GigE Vision devices found via CTI: {cti_path}"
            logger.error(f"[{sensor_id}] {msg}")
            _push_event(data_queue, sensor_id, "error", msg)
            return

        # Try to find the device matching the configured camera IP
        target_idx = 0
        for idx, info in enumerate(h.device_info_list):
            dev_id = getattr(info, "id_", "") or ""
            if camera_ip in dev_id:
                target_idx = idx
                break

        ia = h.create(target_idx)
        ia.start()

        _push_event(data_queue, sensor_id, "connected", "GigE Vision streaming started")
        logger.info(f"[{sensor_id}] GigE Vision acquisition started (device #{target_idx})")

        frame_count = 0

        while not stop_event.is_set():
            try:
                with ia.fetch(timeout=5.0) as buffer:
                    component = buffer.payload.components[0]
                    width = component.width
                    height = component.height
                    raw = component.data.reshape(height, width, -1)

                    # GenIStreamC provides depth, intensity, confidence as
                    # separate components or packed channels depending on
                    # the device configuration. Parse accordingly.
                    if raw.shape[2] >= 3:
                        depth = raw[:, :, 0].astype(np.float64).ravel()
                        intensity = raw[:, :, 1].astype(np.float64).ravel()
                        confidence = raw[:, :, 2].astype(np.uint16).ravel()
                    else:
                        depth = raw[:, :, 0].astype(np.float64).ravel()
                        intensity = np.zeros(height * width, dtype=np.float64)
                        confidence = np.zeros(height * width, dtype=np.uint16)

                    # Use identity cam2world — the pose transform is applied
                    # in the sensor's handle_data method.
                    cam2world = np.eye(4, dtype=np.float64)

                    # Default intrinsics; the GenTL producer may expose these
                    # via GenICam node map. For now use reasonable defaults
                    # that can be overridden once camera parameters are read.
                    fx = fy = float(width)
                    cx = float(width) / 2.0
                    cy = float(height) / 2.0

                    if is_stereo:
                        points = depth_to_point_cloud_stereo(
                            dist_data=depth,
                            intensity_data=intensity,
                            confidence_data=confidence,
                            width=width,
                            height=height,
                            fx=fx,
                            fy=fy,
                            cx=cx,
                            cy=cy,
                            cam2world=cam2world,
                        )
                    else:
                        points = depth_to_point_cloud_tof(
                            dist_data=depth,
                            intensity_data=intensity,
                            confidence_data=confidence,
                            width=width,
                            height=height,
                            fx=fx,
                            fy=fy,
                            cx=cx,
                            cy=cy,
                            k1=0.0,
                            k2=0.0,
                            f2rc=0.0,
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
        logger.error(f"[{sensor_id}] Harvester worker fatal error: {exc}", exc_info=True)
        _push_event(data_queue, sensor_id, "error", str(exc))
    finally:
        if ia is not None:
            try:
                ia.stop()
                ia.destroy()
            except Exception:
                pass
        if h is not None:
            try:
                h.reset()
            except Exception:
                pass
        _push_event(data_queue, sensor_id, "disconnected", "Worker stopped")
        logger.info(f"[{sensor_id}] Harvester worker stopped.")


def _push_event(
    data_queue: "Queue[Any]",
    sensor_id: str,
    event_type: str,
    message: str,
) -> None:
    """Push a lifecycle event into the queue."""
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
