"""Service for managing LiDAR data recordings."""
import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.lidar.protocol.recording import RecordingWriter

logger = logging.getLogger(__name__)


class RecordingHandle:
    """Handle for an active recording session."""
    
    def __init__(self, recording_id: str, topic: str, writer: RecordingWriter, metadata: dict[str, Any]):
        self.recording_id = recording_id
        self.topic = topic
        self.writer = writer
        self.metadata = metadata
        self.started_at = datetime.utcnow()
        self.frame_count = 0
        self.last_timestamp: float | None = None
    
    def get_info(self) -> dict[str, Any]:
        """Get current recording info."""
        duration = (datetime.utcnow() - self.started_at).total_seconds()
        return {
            "recording_id": self.recording_id,
            "topic": self.topic,
            "frame_count": self.frame_count,
            "duration_seconds": duration,
            "started_at": self.started_at.isoformat(),
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
            recordings_dir = Path("config") / "recordings"
        
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        
        self.active_recordings: dict[str, RecordingHandle] = {}
        self.lock = asyncio.Lock()
        
        logger.info(f"RecordingService initialized with directory: {self.recordings_dir}")
    
    async def start_recording(
        self,
        topic: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> tuple[str, str]:
        """
        Start recording a topic.
        
        Args:
            topic: WebSocket topic to record
            name: Optional display name for the recording
            metadata: Optional metadata to store with recording
        
        Returns:
            Tuple of (recording_id, file_path)
        
        Raises:
            ValueError: If topic is already being recorded
        """
        async with self.lock:
            # Check if topic is already being recorded
            for handle in self.active_recordings.values():
                if handle.topic == topic:
                    raise ValueError(f"Topic '{topic}' is already being recorded")
            
            # Generate recording ID and file path
            recording_id = str(uuid.uuid4())
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{topic}_{timestamp}_{recording_id[:8]}.lidr"
            file_path = self.recordings_dir / filename
            
            # Prepare metadata
            if metadata is None:
                metadata = {}
            
            metadata.update({
                "topic": topic,
                "name": name or topic,
                "recording_timestamp": datetime.utcnow().isoformat(),
            })
            
            # Create recording writer
            writer = RecordingWriter(file_path, metadata)
            
            # Create handle
            handle = RecordingHandle(recording_id, topic, writer, metadata)
            self.active_recordings[recording_id] = handle
            
            logger.info(f"Started recording '{topic}' (ID: {recording_id}) to {file_path}")
            
            return recording_id, str(file_path)
    
    async def stop_recording(self, recording_id: str) -> dict[str, Any]:
        """
        Stop an active recording and finalize the file.
        
        Args:
            recording_id: Recording ID
        
        Returns:
            Recording info dictionary
        
        Raises:
            KeyError: If recording_id not found
        """
        async with self.lock:
            if recording_id not in self.active_recordings:
                raise KeyError(f"Recording '{recording_id}' not found")
            
            handle = self.active_recordings.pop(recording_id)
            
            # Finalize recording file
            info = handle.writer.finalize()
            
            # Generate thumbnail asynchronously
            thumbnail_path = None
            file_path = Path(info["file_path"])
            try:
                from app.services.lidar.io.thumbnail import generate_thumbnail_from_file
                
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
            
            logger.info(
                f"Stopped recording '{handle.topic}' (ID: {recording_id}): "
                f"{handle.frame_count} frames, {info['duration_seconds']:.2f}s"
            )
            
            return {
                "recording_id": recording_id,
                "topic": handle.topic,
                "name": handle.metadata.get("name", handle.topic),
                "file_path": info["file_path"],
                "file_size_bytes": info["file_size_bytes"],
                "frame_count": handle.frame_count,
                "duration_seconds": info["duration_seconds"],
                "average_fps": info["average_fps"],
                "metadata": handle.metadata,
                "thumbnail_path": thumbnail_path,
            }
    
    async def record_frame(self, topic: str, frame_data: bytes):
        """
        Record a frame for all active recordings on this topic.
        Called by WebSocket manager during broadcasts.
        
        Args:
            topic: WebSocket topic
            frame_data: LIDR binary frame data
        """
        # Import here to avoid circular dependency
        from app.services.lidar.protocol.binary import unpack_points_binary
        
        # Find all recordings for this topic
        handles = [h for h in self.active_recordings.values() if h.topic == topic]
        
        if not handles:
            return
        
        try:
            # Unpack frame
            points, timestamp = unpack_points_binary(frame_data)
            
            # Write to all active recordings for this topic
            for handle in handles:
                handle.writer.write_frame(points, timestamp)
                handle.frame_count += 1
                handle.last_timestamp = timestamp
        
        except Exception as e:
            logger.error(f"Error recording frame for topic '{topic}': {e}", exc_info=True)
    
    def get_active_recordings(self) -> list[dict[str, Any]]:
        """
        Get list of all active recordings with current stats.
        
        Returns:
            List of recording info dictionaries
        """
        return [handle.get_info() for handle in self.active_recordings.values()]
    
    def is_recording(self, topic: str) -> bool:
        """
        Check if a topic is currently being recorded.
        
        Args:
            topic: WebSocket topic
        
        Returns:
            True if recording, False otherwise
        """
        return any(h.topic == topic for h in self.active_recordings.values())
    
    def get_recording_for_topic(self, topic: str) -> dict[str, Any] | None:
        """
        Get active recording info for a specific topic.
        
        Args:
            topic: WebSocket topic
        
        Returns:
            Recording info dictionary or None if not recording
        """
        for handle in self.active_recordings.values():
            if handle.topic == topic:
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
