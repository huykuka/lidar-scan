"""
TcpStreamServer - Async TCP server that streams metadata to connected clients.

Each connected client receives newline-delimited JSON (NDJSON) frames — one
JSON object per line — matching the same payload broadcast on the WebSocket
output topic.

Usage:
    server = TcpStreamServer.from_config(config)  # None if disabled
    asyncio.create_task(server.start())            # schedule startup
    await server.broadcast(message)               # send to all clients
    server.stop()                                  # graceful shutdown
"""
import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default port — callers should override via config["tcp_port"]
DEFAULT_TCP_PORT = 9000


class TcpStreamServer:
    """Async TCP server that fans out NDJSON payloads to all connected clients."""

    def __init__(self, port: int) -> None:
        self._port = port
        self._server: Optional[asyncio.AbstractServer] = None
        self._writers: Set[asyncio.StreamWriter] = set()
        self._on_client_change: Optional[Callable[[], None]] = None

    def set_client_change_callback(self, cb: Callable[[], None]) -> None:
        """Register a zero-argument callback fired on every connect/disconnect."""
        self._on_client_change = cb

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def client_count(self) -> int:
        """Number of currently connected TCP clients."""
        return len(self._writers)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> Optional["TcpStreamServer"]:
        """Return a TcpStreamServer if tcp_enabled is true, else None."""
        if not config.get("tcp_enabled"):
            return None
        port = int(config.get("tcp_port") or DEFAULT_TCP_PORT)
        return cls(port=port)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start listening. Safe to call multiple times (idempotent)."""
        if self._server is not None:
            return
        try:
            self._server = await asyncio.start_server(
                self._handle_client, host="0.0.0.0", port=self._port
            )
            logger.info(f"TcpStreamServer listening on 0.0.0.0:{self._port}")
        except OSError as exc:
            logger.error(f"TcpStreamServer failed to bind on port {self._port}: {exc}")
            self._server = None

    async def stop_async(self) -> None:
        """
        Gracefully shut down: close all client writers and await port release.

        Must be awaited to guarantee the OS port is fully freed before returning
        (important when reloading on the same port).
        """
        # 1. Close all active client connections and wait for drain.
        writers = list(self._writers)
        self._writers.clear()
        for writer in writers:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        # 2. Stop accepting new connections and release the port.
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
            logger.info(f"TcpStreamServer stopped (port {self._port})")

    def stop(self) -> None:
        """
        Sync entry point called by ModuleNode.stop().

        Schedules stop_async() on the running loop. If no loop is running
        (process teardown), the OS reclaims the resources.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.stop_async())
        except RuntimeError:
            # No running loop — close writers best-effort; OS frees the port.
            for writer in list(self._writers):
                try:
                    writer.close()
                except Exception:
                    pass
            self._writers.clear()
            self._server = None

    async def reload(self, new_port: Optional[int] = None) -> None:
        """
        Stop the server and restart it, optionally on a new port.

        Awaits full port release before binding again so the same port can
        be reused immediately.

        Args:
            new_port: If provided, the server will bind to this port after reload.
        """
        await self.stop_async()
        if new_port is not None:
            self._port = new_port
        await self.start()

    # ------------------------------------------------------------------
    # Client handler
    # ------------------------------------------------------------------

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        logger.info(f"TcpStreamServer: client connected from {peer}")
        self._writers.add(writer)
        if self._on_client_change:
            self._on_client_change()
        try:
            # Keep the connection open; drain any keep-alive bytes the client sends.
            while True:
                data = await reader.read(256)
                if not data:
                    break  # client disconnected
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            self._writers.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.info(f"TcpStreamServer: client disconnected from {peer}")
            if self._on_client_change:
                self._on_client_change()

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        """Send *payload* as a single NDJSON line to every connected client."""
        if not self._writers:
            return

        try:
            line = json.dumps(payload, default=str) + "\n"
            data = line.encode()
        except Exception as exc:
            logger.error(f"TcpStreamServer: serialisation failed: {exc}")
            return

        dead: List[asyncio.StreamWriter] = []
        for writer in list(self._writers):
            try:
                writer.write(data)
                await writer.drain()
            except Exception:
                dead.append(writer)

        for writer in dead:
            self._writers.discard(writer)
            try:
                writer.close()
            except Exception:
                pass
        if dead and self._on_client_change:
            self._on_client_change()
