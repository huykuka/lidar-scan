"""
Vehicle Profiler — Multi-2D-LiDAR vehicle velocity + side-profile reconstruction.

Overview
--------
One vertically-mounted LiDAR tracks the vehicle's leading-edge position
(Kalman-filtered), while one or more side-mounted LiDARs capture cross-section
scan lines.  The Kalman-filtered position is used directly as the along-track
coordinate for each scan line, avoiding velocity-integration drift.

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
        │     └── VehicleDetector (detector.py)
        │           ├── Background model (median per beam)
        │           ├── Edge detection (threshold)
        │           └── Kalman filter (1D, constant-velocity)
        │                 → smoothed position & velocity
        │
        └── source == any other sensor?
              └── ProfileAccumulator (profiler.py)
                    ├── Accepts 2D & 3D (pose-transformed) points
                    ├── Uses Kalman position directly as along-track Z
                    └── Multi-sensor merge automatic via pose transforms

Multi-Sensor Merge
------------------
Side LiDARs at different mounting positions are aligned automatically:
each ``LidarSensor`` node transforms its points to world space using its
configured pose (XYZ + RPY) before forwarding.  The profiler preserves
those world-space coordinates and uses the Kalman-filtered position as the
along-track Z coordinate, producing a spatially consistent merged profile.

File Structure
--------------
- ``node.py``      — VehicleProfilerNode: state machine, frame dispatch
- ``detector.py``  — PositionTracker (pykalman) + VehicleDetector (bg model + edge detect)
- ``profiler.py``  — ProfileAccumulator (2D/3D merge, along-track stacking)
- ``registry.py``  — Schema (dynamic sensor dropdown, Kalman params) + factory

Configurable Parameters (UI)
-----------------------------
====================  ========  ==============================================
Parameter             Default   Description
====================  ========  ==============================================
Velocity Sensor       Auto      Dropdown of all sensor nodes in DAG
Process Noise (Q)     0.1       Kalman trust in measurements vs motion model
Measurement Noise (R) 0.5       How noisy edge-position readings are
Background Threshold  0.3 m     Distance closer than bg = vehicle
BG Learning Frames    20        Initial frames to learn background
Travel Axis           X         Which scan axis = vehicle travel direction
Min Scan Lines        10        Minimum scans to emit a valid profile
Max Gap               2.0 s     Max time between scans before abort
====================  ========  ==============================================
"""
