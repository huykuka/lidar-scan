import ctypes
import multiprocessing as mp
import os
import time
from typing import Any
import numpy as np
from sick_scan_api import SickScanApiLoadLibrary, SickScanApiCreate, SickScanApiInitByLaunchfile, SickScanPointCloudMsgCallback, SickScanApiRegisterCartesianPointCloudMsg, SickScanApiDeregisterCartesianPointCloudMsg, SickScanApiClose, SickScanApiRelease, SickScanApiUnloadLibrary
def lidar_worker_process(lidar_id: str, launch_args: str, pipeline: Any, data_queue: mp.Queue, stop_event: mp.Event):
    """
    Worker process that owns its own instance of sick_scan_xd library AND its own pipeline.
    """
    # 1. Load Library
    if os.name == "nt":
        lib_name = "sick_scan_xd_shared_lib.dll"
        search_paths = ["build/Debug/", "./"]
    else:
        lib_name = "libsick_scan_xd_shared_lib.so"
        search_paths = ["build/", "./"]

    sick_scan_library = SickScanApiLoadLibrary(search_paths, lib_name)
    if not sick_scan_library:
        print(f"[{lidar_id}] Error: Could not load {lib_name}")
        return

    api_handle = SickScanApiCreate(sick_scan_library)
    SickScanApiInitByLaunchfile(sick_scan_library, api_handle, launch_args)

    def _py_pointcloud_cb(handle, msg):
        try:
            msg_contents = msg.contents
            num_points = msg_contents.width * msg_contents.height
            if num_points == 0:
                return

            # Extract points
            data_ptr = msg_contents.data.buffer
            data_size = msg_contents.data.size
            point_step = msg_contents.point_step
            buffer = ctypes.string_at(data_ptr, data_size)

            points_raw = np.frombuffer(buffer, dtype=np.float32)
            fields_count = point_step // 4
            points_reshaped = points_raw.reshape(-1, fields_count)[:, :3]

            timestamp = msg_contents.header.timestamp_sec + msg_contents.header.timestamp_nsec / 1e9

            # --- PROCESS DATA IN WORKER PROCESS ---
            if pipeline:
                processed_result = pipeline.process(points_reshaped)
                payload = {
                    "lidar_id": lidar_id,
                    "processed": True,
                    "data": processed_result,
                    "raw_points": points_reshaped.tolist(),
                    "timestamp": timestamp
                }
            else:
                payload = {
                    "lidar_id": lidar_id,
                    "processed": False,
                    "points": points_reshaped.tolist(),
                    "count": len(points_reshaped),
                    "timestamp": timestamp
                }

            try:
                data_queue.put(payload, block=False)
            except Exception:
                pass

        except Exception as e:
            print(f"[{lidar_id}] Callback error: {e}")

    # 2. Register Callback
    pc_callback = SickScanPointCloudMsgCallback(_py_pointcloud_cb)
    SickScanApiRegisterCartesianPointCloudMsg(sick_scan_library, api_handle, pc_callback)

    print(f"[{lidar_id}] Worker ready with independent pipeline.")

    # 3. Main Loop
    try:
        while not stop_event.is_set():
            time.sleep(0.1)
    finally:
        SickScanApiDeregisterCartesianPointCloudMsg(sick_scan_library, api_handle, pc_callback)
        SickScanApiClose(sick_scan_library, api_handle)
        SickScanApiRelease(sick_scan_library, api_handle)
        SickScanApiUnloadLibrary(sick_scan_library)
