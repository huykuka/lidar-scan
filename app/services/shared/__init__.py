"""
Shared cross-cutting utilities used across multiple modules.

This package contains utilities that don't belong to any specific module
but are used by multiple modules (lidar, fusion, pipeline).
"""
from .topics import TopicRegistry, slugify_topic_prefix, generate_unique_topic_prefix
from .binary import pack_points_binary, unpack_points_binary, MAGIC_BYTES, VERSION
from .recorder import RecordingService, RecordingHandle, get_recorder
from .recording import RecordingWriter, RecordingReader, get_recording_info
from .thumbnail import generate_thumbnail, generate_thumbnail_from_file

__all__ = [
    # Topics
    "TopicRegistry",
    "slugify_topic_prefix",
    "generate_unique_topic_prefix",
    # Binary protocol
    "pack_points_binary",
    "unpack_points_binary",
    "MAGIC_BYTES",
    "VERSION",
    # Recording
    "RecordingService",
    "RecordingHandle",
    "get_recorder",
    "RecordingWriter",
    "RecordingReader",
    "get_recording_info",
    # Thumbnail
    "generate_thumbnail",
    "generate_thumbnail_from_file",
]
