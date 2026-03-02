"""
Topic prefix generation and management utilities for WebSocket topics.
"""
import re
from typing import Set


def slugify_topic_prefix(name: str) -> str:
    """
    Converts a name into a URL-friendly, stable topic prefix.
    
    Rules:
    - Convert to lowercase for case-insensitive uniqueness
    - Replace non-alphanumeric characters (except _ and -) with underscore
    - Collapse multiple underscores into one
    - Strip leading/trailing underscores and hyphens
    - Return "sensor" as default if result is empty
    
    Args:
        name: Raw name to convert
    
    Returns:
        Lowercase slugified topic prefix
    
    Examples:
        >>> slugify_topic_prefix("Front Lidar #1")
        'front_lidar_1'
        >>> slugify_topic_prefix("Crop Filter")
        'crop_filter'
        >>> slugify_topic_prefix("test__sensor--name")
        'test_sensor_name'
        >>> slugify_topic_prefix("")
        'sensor'
    """
    # Convert to lowercase first
    base = (name or "").strip().lower()
    
    # Replace non [a-z0-9_-] with underscore
    base = re.sub(r"[^a-z0-9_-]+", "_", base)
    
    # Collapse repeats, strip edges
    base = re.sub(r"_+", "_", base).strip("_-")
    
    return base or "sensor"


def generate_unique_topic_prefix(
    desired: str,
    sensor_id: str,
    existing_prefixes: Set[str]
) -> str:
    """
    Generates a unique topic prefix, adding suffixes if needed to avoid collisions.
    
    Strategy:
    1. Try the slugified desired prefix (lowercase)
    2. If taken, append a shortened sensor_id suffix
    3. If still taken, append incrementing numbers
    
    Args:
        desired: Desired topic prefix (will be slugified to lowercase)
        sensor_id: Sensor ID to use for suffix generation
        existing_prefixes: Set of already-used topic prefixes
    
    Returns:
        Unique lowercase topic prefix (not in existing_prefixes)
    
    Examples:
        >>> generate_unique_topic_prefix("Front", "abc123", {"rear"})
        'front'
        >>> generate_unique_topic_prefix("Front", "abc123", {"front"})
        'front_abc123'
        >>> generate_unique_topic_prefix("Front", "abc123", {"front", "front_abc123"})
        'front_abc123_2'
    """
    base = slugify_topic_prefix(desired)
    
    # Try base first
    if base not in existing_prefixes:
        return base
    
    # Generate suffix from sensor_id (first 8 chars after slugifying)
    suffix = slugify_topic_prefix(sensor_id)[:8]
    candidate = f"{base}_{suffix}" if suffix else f"{base}_1"
    
    # Try with suffix
    if candidate not in existing_prefixes:
        return candidate
    
    # Append incrementing numbers
    i = 2
    while True:
        candidate = f"{base}_{suffix}_{i}" if suffix else f"{base}_{i}"
        if candidate not in existing_prefixes:
            return candidate
        i += 1


class TopicRegistry:
    """
    Registry for managing topic prefix uniqueness.
    """
    
    def __init__(self):
        self._prefixes: Set[str] = set()
    
    def register(self, desired: str, sensor_id: str) -> str:
        """
        Registers a new topic prefix, ensuring uniqueness.
        
        Args:
            desired: Desired topic prefix
            sensor_id: Sensor ID for suffix generation
        
        Returns:
            Unique topic prefix that has been registered
        """
        prefix = generate_unique_topic_prefix(desired, sensor_id, self._prefixes)
        self._prefixes.add(prefix)
        return prefix
    
    def unregister(self, prefix: str) -> None:
        """
        Removes a topic prefix from the registry.
        
        Args:
            prefix: Topic prefix to remove
        """
        self._prefixes.discard(prefix)
    
    def clear(self) -> None:
        """Clears all registered prefixes."""
        self._prefixes.clear()
    
    def get_all(self) -> Set[str]:
        """Returns all registered prefixes."""
        return self._prefixes.copy()
