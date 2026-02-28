# Backend Architecture & Best Practices

## Tech Stack

Python 3.10+, FastAPI, Open3D, Asyncio/Multiprocessing, SQLite.

## Core Architecture

The backend is a dynamic Directed Acyclic Graph (DAG) orchestration engine. It routes tensor data directly from memory buffers.

1. **Modules (`app/modules/`)**: Self-contained pluggable nodes. Everything MUST define a `registry.py` with `@NodeFactory.register()`.
2. **Orchestrator (`app/services/nodes/orchestrator.py`)**: Central DAG manager. Module code MUST NOT directly couple to the orchestrator.
3. **Concurrency**: All heavy Open3D processing routines must offload to the threadpool via `await asyncio.to_thread()` to avoid locking the FastAPI asyncio event loop.
4. **Hardware Sources**: Worker processes (e.g., SICK LIDAR UDP readers) run natively as isolated `multiprocessing.Process` instances pushing binary frames to a `multiprocessing.Queue`.

## Best Practices

- **Type Hinting**: All functions MUST use strict Python type hinting (`Dict`, `List`, `Optional`, etc.).
- **Pydantic**: Use Pydantic V2 models for REST API data validation.
- **Data Transfer**: Do not serialize full point clouds to JSON over REST. Only metadata. Actual XYZ point clouds MUST be broadcast over binary WebSockets (`LIDR` protocol).
- **Error Handling**: Use explicit FastAPI `HTTPException` raises in the `/api/v1/` routing layer, not deep inside module services.
- **Node Implementation**: When building new processing nodes, inherit from `ModuleNode` and ensure you implement `async def on_input(self, payload)`.
