import ctypes
import multiprocessing as mp
import os
import time
from typing import Any

import numpy as np
from sick_scan_api import SickScanApiLoadLibrary, SickScanApiCreate, SickScanApiInitByLaunchfile, \
    SickScanPointCloudMsgCallback, SickScanApiRegisterCartesianPointCloudMsg, \
    SickScanApiDeregisterCartesianPointCloudMsg, SickScanApiClose, SickScanApiRelease, SickScanApiUnloadLibrary


def parse_sick_scan_pointcloud(msg_contents):
    """
    Parses a SickScanPointCloudMsg into a structured numpy array (16 columns).
    Returns (points_reshaped, topic_name)
    """
    requiredTopic = "cloud_all_fields_fullframe"
    points_reshaped = None

    try:
        # Robust topic decoding (handle null terminators and slashes)
        topic = msg_contents.topic.decode('utf-8').split('\x00')[0].strip()
    except Exception:
        topic = ""

    num_points = msg_contents.width * msg_contents.height
    if num_points == 0:
        return None, topic

    # Extract raw buffer
    data_ptr = msg_contents.data.buffer
    data_size = msg_contents.data.size
    point_step = msg_contents.point_step
    buffer = ctypes.string_at(data_ptr, data_size)

    # Use endswith to match both "cloud_all_fields_fullframe" and "/cloud_all_fields_fullframe"
    if topic.endswith(requiredTopic) and msg_contents.fields.size > 0:
        # 1. Map sick_scan_api types to numpy types
        # 1:I8, 2:U8, 3:I16, 4:U16, 5:I32, 6:U32/U4, 7:F32, 8:F64
        type_map = {1: 'i1', 2: 'u1', 3: 'i2', 4: 'u2', 5: 'i4', 6: 'u4', 7: 'f4', 8: 'f8'}

        fields_arr = msg_contents.fields
        names = []
        formats = []
        offsets = []
        for i in range(fields_arr.size):
            f = fields_arr.buffer[i]
            # Robust field name decoding (equivalent to ctypesCharArrayToString)
            f_name = f.name.decode('utf-8').split('\x00')[0].strip()
            names.append(f_name)
            formats.append(type_map.get(f.datatype, 'f4'))
            offsets.append(f.offset)

        dt = np.dtype({
            'names': names,
            'formats': formats,
            'offsets': offsets,
            'itemsize': point_step
        })

        # 2. Vectorized extraction respecting row_step and point_step
        points_struct = np.ndarray(
            shape=(msg_contents.height, msg_contents.width),
            dtype=dt,
            buffer=buffer,
            strides=(msg_contents.row_step, msg_contents.point_step)
        ).reshape(-1)

        # 3. Map to 16-column array for pipeline
        points_reshaped = np.zeros((num_points, 16), dtype=np.float64)

        col_map = {
            'x': 0, 'y': 1, 'z': 2,
            'lidar_nsec': 3,
            'lidar_sec': 4,
            't': 5,
            'layer': 6, 'ring': 6,
            'elevation': 7,
            'ts': 8,
            'azimuth': 9,
            'range': 10,
            'reflector': 11,
            'echo': 12,
            'intensity': 13, 'i': 13
        }

        for name in names:
            if name in col_map:
                idx = col_map[name]
                points_reshaped[:, idx] = points_struct[name].astype(np.float64)

    return points_reshaped, topic


def lidar_worker_process(lidar_id: str, launch_args: str, pipeline: Any, data_queue: mp.Queue, stop_event: mp.Event):
    """
    Worker process that owns its own instance of sick_scan_xd library AND its own pipeline.
    """

    requiredTopic = "cloud_all_fields_fullframe"
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
            points_reshaped, topic = parse_sick_scan_pointcloud(msg_contents)

            if points_reshaped is None:
                return

            if not topic.endswith(requiredTopic) and msg_contents.segment_idx != -1:
                return

            timestamp = msg_contents.header.timestamp_sec + msg_contents.header.timestamp_nsec / 1e9

            # --- PROCESS DATA IN WORKER PROCESS ---
            if pipeline:
                processed_result = pipeline.process(points_reshaped)
                payload = {
                    "lidar_id": lidar_id,
                    "processed": True,
                    "data": processed_result,
                    "raw_points": points_reshaped,
                    "timestamp": timestamp
                }
            else:
                payload = {
                    "lidar_id": lidar_id,
                    "processed": False,
                    "points": points_reshaped,
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

    # 3. Main Loop
    try:
        while not stop_event.is_set():
            time.sleep(0.1)
    finally:
        SickScanApiDeregisterCartesianPointCloudMsg(sick_scan_library, api_handle, pc_callback)
        SickScanApiClose(sick_scan_library, api_handle)
        SickScanApiRelease(sick_scan_library, api_handle)
        SickScanApiUnloadLibrary(sick_scan_library)
