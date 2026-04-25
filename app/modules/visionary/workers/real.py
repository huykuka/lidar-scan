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
import socket
import sys
import time
from multiprocessing import Event, Queue
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)



def visionary_worker_process(
    sensor_id: str,
    camera_ip: str,
    host_ip: str,
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
        camera_ip:      IP address of the SICK Visionary camera.
        streaming_port: TCP/UDP streaming port (default 2114).
        protocol:       ``"TCP"`` or ``"UDP"``.
        cola_protocol:  ``"ColaB"`` or ``"Cola2"``.
        control_port:   CoLa control port (default 2122 for Cola2, 2112 for ColaB).
        is_stereo:      True for stereo cameras (Visionary-S, Visionary-B Two).
        data_queue:     Shared queue for pushing payloads to the main process.
        stop_event:     Multiprocessing event signalling graceful shutdown.
    """
    try:
        from app.modules.visionary.workers.api.Stream import Streaming
        from app.modules.visionary.workers.api.Streaming.Data import Data
        from app.modules.visionary.workers.api.Control import Control
        from app.modules.visionary.workers.api.Streaming.BlobServerConfiguration import BlobClientConfig
        from app.modules.visionary.workers.api.Usertypes import FrontendMode
    except ImportError as exc:
        logger.error(
            f"[{sensor_id}] API module is not available: {exc}"
        )
        _push_event(data_queue, sensor_id, "error", f"SDK not installed: {exc}")
        return

    # Suppress verbose per-frame SDK logging ("Reading binary segment", etc.)
    logging.getLogger("root").setLevel(logging.WARNING)
    logging.getLogger("app.modules.visionary.workers.api").setLevel(logging.WARNING)

    from app.modules.visionary.point_cloud import StereoProjector, ToFProjector

    streaming: Any = None
    control: Any = None

    try:
        # --- Control channel ---------------------------------------------------
        logger.info(f"[{sensor_id}] Connecting control channel to {camera_ip}:{control_port} ({cola_protocol})")
        control = Control(camera_ip, cola_protocol, control_port=control_port, timeout=5)
        control.open()
        control.login(Control.USERLEVEL_SERVICE, "CUST_SERV")
        logger.info(f"[{sensor_id}] Control channel connected")

        # --- Configure streaming via control channel -----------------------------
        streaming_settings = BlobClientConfig(control)

        if protocol == "UDP":
            streaming_settings.setTransportProtocol(streaming_settings.PROTOCOL_UDP)
            streaming_settings.setBlobUdpReceiverPort(streaming_port)
            streaming_settings.setBlobUdpReceiverIP(host_ip)
            streaming_settings.setBlobUdpControlPort(streaming_port)
            streaming_settings.setBlobUdpMaxPacketSize(1024)
            streaming_settings.setBlobUdpIdleTimeBetweenPackets(10)
            streaming_settings.setBlobUdpHeartbeatInterval(0)
            streaming_settings.setBlobUdpHeaderEnabled(True)
            streaming_settings.setBlobUdpFecEnabled(False)
            streaming_settings.setBlobUdpAutoTransmit(True)
            streaming = Streaming(camera_ip, streaming_port, protocol="UDP")
            streaming.openStream((host_ip, streaming_port))
        else:
            streaming_settings.setTransportProtocol(streaming_settings.PROTOCOL_TCP)
            streaming_settings.setBlobTcpPort(streaming_port)
            streaming = Streaming(camera_ip, streaming_port)
            streaming.openStream()

        # Set continuous acquisition mode
        control.setFrontendMode(FrontendMode.Continuous)
        control.logout()

        _push_event(data_queue, sensor_id, "connected", "Camera streaming started")

        my_data = Data()
        frame_count = 0
        projector = None  # built lazily from first frame's camera params

        # --- Acquisition loop --------------------------------------------------
        while not stop_event.is_set():
            try:
                try:
                    streaming.getFrame()
                except (IndexError, ValueError) as parse_err:
                    if frame_count == 0:
                        logger.warning(
                            f"[{sensor_id}] UDP frame parse error: {parse_err}")
                    continue

                raw_frame = streaming.frame

                if raw_frame is None:
                    continue

                # Skip expensive parsing + projection when queue is backed up
                if data_queue.full():
                    continue

                my_data.read(raw_frame, convertToMM=False)

                if not my_data.hasDepthMap:
                    continue
                if projector is None:
                    cam = my_data.cameraParams
                    cam2world = np.array(
                        cam.cam2worldMatrix, dtype=np.float64
                    ).reshape(4, 4)
                    logger.info(
                        f"[{sensor_id}] Camera: {cam.width}x{cam.height}, "
                        f"fx={cam.fx:.2f} fy={cam.fy:.2f}"
                    )

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

            except Exception as frame_exc:
                logger.warning(f"[{sensor_id}] Frame error: {frame_exc}")
                _push_event(data_queue, sensor_id, "error", str(frame_exc))
                if stop_event.is_set():
                    break

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
                # Restore TCP mode when shutting down UDP to leave camera
                # in a clean state for the next connection.
                if protocol == "UDP":
                    control.login(Control.USERLEVEL_AUTH_CLIENT, "CLIENT")
                    restore = BlobClientConfig(control)
                    restore.setTransportProtocol(restore.PROTOCOL_TCP)
                    restore.setBlobTcpPort(streaming_port)
                    control.logout()
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
