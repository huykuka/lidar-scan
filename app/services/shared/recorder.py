"""Service for managing LiDAR data recordings."""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.shared.recording import RecordingWriter

logger = logging.getLogger(__name__)


class RecordingHandle:
    """Handle for an active recording session with frame batching."""
    
    def __init__(self, recording_id: str, node_id: str, writer: RecordingWriter, metadata: dict[str, Any]):
        self.recording_id = recording_id
        self.node_id = node_id
        self.writer = writer
        self.metadata = metadata
        self.started_at = datetime.now(timezone.utc)
        self.frame_count = 0
        self.last_timestamp: float | None = None
        self.status = "recording"  # "recording", "stopping", "stopped"
        
        # Batching
        self.frame_buffer: list[tuple[Any, float]] = []  # (points, timestamp)
        self.batch_size = 10  # Write every 10 frames
        self.last_flush_time = datetime.now(timezone.utc)
        self.flush_interval = 1.0  # Force flush every 1 second
    
    def get_info(self) -> dict[str, Any]:
        """Get current recording info."""
        duration = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return {
            "recording_id": self.recording_id,
            "node_id": self.node_id,
            "frame_count": self.frame_count,
            "duration_seconds": duration,
            "started_at": self.started_at.isoformat(),
            "metadata": self.metadata,
            "status": self.status,
        }


class RecordingService:
    """
    Manages active recordings by intercepting WebSocket broadcasts.
    Supports concurrent recording of multiple topics.
    """
    
    def __init__(self, recordings_dir: str | Path | None = None):
        """
        Initialize recording service.
        
        Args:
            recordings_dir: Directory for storing recordings (default: config/recordings)
        """
        if recordings_dir is None:
            recordings_dir = Path("recordings")
        
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        
        self.active_recordings: dict[str, RecordingHandle] = {}
        self.lock = asyncio.Lock()
        
        logger.info(f"RecordingService initialized with directory: {self.recordings_dir}")
    
    async def start_recording(
        self,
        node_id: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> tuple[str, str]:
        """
        Start recording a topic.
        
        Args:
            node_id: Target Node ID to intercept pipeline payload from
            name: Optional display name for the recording
            metadata: Optional metadata to store with recording
        
        Returns:
            Tuple of (recording_id, file_path)
        
        Raises:
            ValueError: If topic is already being recorded
        """
        async with self.lock:
            # Note: We intentionally DO NOT check if the topic is already being recorded.
            # Allowing multiple isolated recording loops for the same output string ensures
            # multiple duplicate backend graph node outputs can be individually explicitly captured.
            
            # Generate recording ID and file path
            recording_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"capture_{timestamp}_{recording_id[:8]}.zip"
            file_path = self.recordings_dir / filename
            
            # Prepare metadata
            if metadata is None:
                metadata = {}
            
            metadata.update({
                "node_id": node_id,
                "name": name or node_id,
                "recording_timestamp": datetime.now(timezone.utc).isoformat(),
            })
            
            # Create recording writer
            writer = RecordingWriter(file_path, metadata)
            
            # Create handle
            handle = RecordingHandle(recording_id, node_id, writer, metadata)
            self.active_recordings[recording_id] = handle
            
            logger.info(f"Started recording '{node_id}' (ID: {recording_id}) to {file_path}")
            
            return recording_id, str(file_path)
    
    async def stop_recording(self, recording_id: str) -> dict[str, Any]:
        """
        Stop an active recording and finalize the file.
        Sets status to 'stopping' immediately and returns, then finalizes asynchronously.
        
        Args:
            recording_id: Recording ID
        
        Returns:
            Recording info dictionary with status='stopping'
        
        Raises:
            KeyError: If recording_id not found
        """
        # Mark as stopping immediately (this is what the UI sees)
        handle = None
        async with self.lock:
            if recording_id not in self.active_recordings:
                raise KeyError(f"Recording '{recording_id}' not found")
            
            handle = self.active_recordings[recording_id]
            handle.status = "stopping"
            logger.info(f"Marking recording '{recording_id}' as stopping")
        
        # Return immediately with stopping status
        return handle.get_info()
    
    async def finalize_recording(self, recording_id: str) -> dict[str, Any]:
        """
        Finalize a stopping recording (flush buffers, write metadata, generate thumbnail).
        Should be called as a background task after stop_recording.
        
        Args:
            recording_id: Recording ID
        
        Returns:
            Final recording info dictionary
        """
        handle = None
        async with self.lock:
            if recording_id not in self.active_recordings:
                logger.error(f"Recording '{recording_id}' not found in active recordings during finalization")
                raise KeyError(f"Recording '{recording_id}' not found")
            
            handle = self.active_recordings.pop(recording_id)
            logger.info(f"Finalizing recording '{recording_id}': Total {handle.frame_count} frames, {len(handle.frame_buffer)} remaining in buffer")
        
        # Flush any remaining frames in buffer
        if handle.frame_buffer:
            logger.info(f"Flushing {len(handle.frame_buffer)} remaining frames for recording {recording_id[:8]}")
            try:
                await asyncio.to_thread(handle.writer.write_batch, handle.frame_buffer)
                handle.frame_buffer.clear()
            except Exception as e:
                logger.error(f"Error flushing buffer for recording {recording_id}: {e}", exc_info=True)
        
        # Wait a brief moment for any in-flight writes to complete
        await asyncio.sleep(0.1)
        
        # Finalize recording file in thread pool (since it acquires the ZIP lock)
        info = None
        try:
            info = await asyncio.to_thread(handle.writer.finalize)
            actual_frame_count = info.get('frame_count')
            logger.info(f"Finalized ZIP file for recording {recording_id}: {actual_frame_count} frames written, {info.get('duration_seconds'):.2f}s")
            
            # Verify frame counts match (handle.frame_count should equal writer.frame_count)
            if handle.frame_count != actual_frame_count:
                logger.warning(
                    f"Frame count mismatch for recording {recording_id}: "
                    f"handle counted {handle.frame_count}, but ZIP has {actual_frame_count} frames"
                )
        except Exception as e:
            logger.error(f"Error finalizing ZIP for recording {recording_id}: {e}", exc_info=True)
            raise
        
        # Generate thumbnail asynchronously
        thumbnail_path = None
        file_path = Path(info["file_path"])
        try:
            from app.services.shared.thumbnail import generate_thumbnail_from_file
            
            thumbnail_output = file_path.with_suffix(".png")
            success = await asyncio.to_thread(
                generate_thumbnail_from_file,
                file_path,
                output_path=thumbnail_output,
                view="top"
            )
            if success:
                thumbnail_path = str(thumbnail_output)
                logger.info(f"Generated thumbnail: {thumbnail_path}")
        except Exception as e:
            logger.warning(f"Failed to generate thumbnail for recording {recording_id}: {e}")
        
        # Use the actual frame count from the ZIP file (authoritative source)
        actual_frame_count = info["frame_count"]
        
        logger.info(
            f"Finalized recording '{handle.node_id}' (ID: {recording_id}): "
            f"{actual_frame_count} frames, {info['duration_seconds']:.2f}s"
        )
        
        return {
            "recording_id": recording_id,
            "node_id": handle.node_id,
            "name": handle.metadata.get("name", handle.node_id),
            "file_path": info["file_path"],
            "file_size_bytes": info["file_size_bytes"],
            "frame_count": actual_frame_count,  # Use writer's count (authoritative)
            "duration_seconds": info["duration_seconds"],
            "average_fps": info["average_fps"],
            "metadata": handle.metadata,
            "thumbnail_path": thumbnail_path,
            "status": "stopped",
        }
    
    async def record_node_payload(self, node_id: str, points: Any, timestamp: float):
        """
        Record a native compute payload for all active recordings targeting this node.
        Uses batching for better performance - buffers frames and writes in batches.
        
        Args:
            node_id: Source Node ID
            points: N-dim point cloud NumPy Array
            timestamp: Unix timestamp
        """
        # Find all active recordings for this node (exclude 'stopping' state)
        # Use lock to prevent RuntimeError if dict changes during iteration
        async with self.lock:
            handles = [h for h in self.active_recordings.values() 
                       if h.node_id == node_id and h.status == "recording"]
        
        if not handles:
            return
        
        try:
            for handle in handles:
                # Add frame to buffer
                handle.frame_buffer.append((points, timestamp))
                handle.frame_count += 1
                handle.last_timestamp = timestamp
                
                # Check if we should flush the buffer
                should_flush = (
                    len(handle.frame_buffer) >= handle.batch_size or
                    (datetime.now(timezone.utc) - handle.last_flush_time).total_seconds() >= handle.flush_interval
                )
                
                if should_flush:
                    # Write batch in thread pool to avoid blocking event loop
                    batch = handle.frame_buffer.copy()
                    handle.frame_buffer.clear()
                    handle.last_flush_time = datetime.now(timezone.utc)
                    
                    await asyncio.to_thread(handle.writer.write_batch, batch)
                    
                    # Debug logging
                    duration_so_far = timestamp - (handle.writer.start_timestamp or timestamp)
                    logger.debug(
                        f"Recording '{handle.recording_id[:8]}' for node '{node_id}': "
                        f"Flushed {len(batch)} frames, Total: {handle.frame_count}, Duration: {duration_so_far:.2f}s"
                    )
        
        except Exception as e:
            logger.error(f"Error recording frame for node '{node_id}': {e}", exc_info=True)
    
    def get_active_recordings(self) -> list[dict[str, Any]]:
        """
        Get list of all active recordings with current stats.
        
        Returns:
            List of recording info dictionaries
        """
        return [handle.get_info() for handle in self.active_recordings.values()]
    
    def is_recording(self, node_id: str) -> bool:
        """
        Check if a node is currently being recorded.
        
        Args:
            node_id: Node ID
        
        Returns:
            True if recording, False otherwise
        """
        return any(h.node_id == node_id for h in self.active_recordings.values())
    
    def get_recording_for_node(self, node_id: str) -> dict[str, Any] | None:
        """
        Get active recording info for a specific node.
        
        Args:
            node_id: Node ID
        
        Returns:
            Recording info dictionary or None if not recording
        """
        for handle in self.active_recordings.values():
            if handle.node_id == node_id:
                return handle.get_info()
        return None
    
    async def stop_all_recordings(self) -> list[dict[str, Any]]:
        """
        Stop all active recordings.
        
        Returns:
            List of recording info dictionaries
        """
        results = []
        recording_ids = list(self.active_recordings.keys())
        
        for recording_id in recording_ids:
            try:
                info = await self.stop_recording(recording_id)
                results.append(info)
            except Exception as e:
                logger.error(f"Error stopping recording {recording_id}: {e}")
        
        return results


# Global singleton instance
_recorder: RecordingService | None = None


def get_recorder() -> RecordingService:
    """Get the global RecordingService instance."""
    global _recorder
    if _recorder is None:
        _recorder = RecordingService()
    return _recorder
