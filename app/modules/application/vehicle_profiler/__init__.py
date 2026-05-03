"""
Vehicle Profiler — Multi-2D-LiDAR vehicle velocity + side-profile reconstruction.

Overview
--------
One vertically-mounted LiDAR (full gantry FOV) tracks the vehicle cluster via
Nearest-Neighbour centroid association, estimating velocity continuously from
centroid displacement between frames.  One or more side-mounted LiDARs capture
cross-section scan lines indexed by integrated travel distance.

DAG Wiring
----------
::

    [LiDAR Sensor A (vertical)] ──┐
    [LiDAR Sensor B (side)]     ──┼──► [Vehicle Profiler] ──► 3D profile cloud
    [LiDAR Sensor C (side)]     ──┘

State Machine
-------------
::

    IDLE ──(vehicle detected)──► MEASURING ──(vehicle left)──► IDLE
                                      │
                                 (emit profile)

Internal Pipeline
-----------------
::

    on_input(payload)
        │
        ├── source == velocity_sensor_id?
        │     └── VehicleDetector (utils/detector.py)
        │           ├── Background model (median per beam)
        │           ├── Cluster extraction (background subtraction)
        │           └── ClusterTracker (NN centroid association)
        │                 → smoothed velocity & integrated position
        │
        └── source == any other sensor?
              └── ProfileAccumulator (utils/profiler.py)
                    ├── Accepts 2D & 3D (pose-transformed) points
                    ├── Uses integrated position as along-track coordinate
                    └── Multi-sensor merge automatic via pose transforms

File Structure
--------------
- ``node.py``         — VehicleProfilerNode: state machine, frame dispatch
- ``utils/detector.py`` — ClusterTracker (NN) + VehicleDetector (bg model + cluster track)
- ``utils/profiler.py`` — ProfileAccumulator (2D/3D merge, along-track stacking)
- ``registry.py``     — Schema + factory

Configurable Parameters (UI)
-----------------------------
==========================  ========  ==============================================
Parameter                   Default   Description
==========================  ========  ==============================================
Velocity Sensor             Auto      Dropdown of all sensor nodes in DAG
Max Association Distance    2.0 m     NN gate — max centroid jump between frames
Velocity Smoothing (EMA α)  0.4       Smoothing factor for velocity (0=frozen, 1=raw)
Background Threshold        0.3 m     Distance closer than bg = vehicle
BG Learning Frames          20        Initial frames to learn background
Gap Debounce (s)            3.0       Falling-edge hold before declaring vehicle gone
Travel Axis                 X         Which axis = vehicle travel direction
Min Scan Lines              10        Minimum scans to emit a valid profile
==========================  ========  ==============================================
"""
