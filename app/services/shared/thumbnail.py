"""Thumbnail generation for point cloud recordings."""
import logging
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def generate_thumbnail(
    points: np.ndarray,
    output_path: str | Path,
    size: tuple[int, int] = (300, 300),
    view: str = "top"
) -> bool:
    """
    Generate a thumbnail image from a point cloud.
    
    Args:
        points: Point cloud array (Nx3)
        output_path: Output file path for thumbnail
        size: Thumbnail dimensions (width, height)
        view: Camera view ("top", "front", "side", "isometric")
    
    Returns:
        True if successful, False otherwise
    """
    try:
        if points.shape[0] == 0:
            logger.warning("Empty point cloud, cannot generate thumbnail")
            return False
        
        # Filter out zero points (invalid returns)
        valid_mask = ~np.all(points == 0, axis=1)
        points = points[valid_mask]
        
        if points.shape[0] == 0:
            logger.warning("No valid points after filtering, cannot generate thumbnail")
            return False
        
        # Select projection based on view
        if view == "top":
            # Top-down view (X, Y)
            x_idx, y_idx = 0, 1
        elif view == "front":
            # Front view (X, Z)
            x_idx, y_idx = 0, 2
        elif view == "side":
            # Side view (Y, Z)
            x_idx, y_idx = 1, 2
        else:  # isometric
            # 45-degree isometric projection
            x_idx, y_idx = 0, 1
            # Apply rotation for isometric effect
            points = _apply_isometric_transform(points)
        
        # Project to 2D
        x = points[:, x_idx]
        y = points[:, y_idx]
        
        # Normalize to image size with padding
        padding = 0.1  # 10% padding
        x_min, x_max = x.min(), x.max()
        y_min, y_max = y.min(), y.max()
        
        x_range = x_max - x_min
        y_range = y_max - y_min
        
        if x_range == 0 and y_range == 0:
            logger.warning("Degenerate point cloud (single point pointcloud), cannot generate thumbnail")
            return False
        
        # Add padding
        x_min -= x_range * padding
        x_max += x_range * padding
        y_min -= y_range * padding
        y_max += y_range * padding
        
        # Normalize to image coordinates
        img_width, img_height = size
        
        if x_max > x_min:
            x_norm = ((x - x_min) / (x_max - x_min) * (img_width - 1)).astype(int)
        else:
            x_norm = np.full_like(x, img_width // 2, dtype=int)
            
        if y_max > y_min:
            y_norm = ((y - y_min) / (y_max - y_min) * (img_height - 1)).astype(int)
        else:
            y_norm = np.full_like(y, img_height // 2, dtype=int)
        
        # Flip Y (image coordinates are top-down)
        y_norm = img_height - 1 - y_norm
        
        # Create image
        img = Image.new("RGB", size, color=(42, 42, 43))  # Match workspace background
        draw = ImageDraw.Draw(img)
        
        # Draw points with slight blur effect for better visibility
        point_color = (59, 130, 246)  # Primary blue color
        point_size = 2
        
        for px, py in zip(x_norm, y_norm):
            if 0 <= px < img_width and 0 <= py < img_height:
                draw.ellipse(
                    [px - point_size, py - point_size, px + point_size, py + point_size],
                    fill=point_color
                )
        
        # Save thumbnail
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG", optimize=True)
        
        logger.info(f"Generated thumbnail: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to generate thumbnail: {e}", exc_info=True)
        return False


def _apply_isometric_transform(points: np.ndarray) -> np.ndarray:
    """Apply isometric projection transformation."""
    # Rotate 45 degrees around Z-axis, then tilt for isometric view
    angle = np.pi / 4  # 45 degrees
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    
    rotation_matrix = np.array([
        [cos_a, -sin_a, 0],
        [sin_a, cos_a, 0],
        [0, 0, 1]
    ])
    
    return points @ rotation_matrix.T


def generate_thumbnail_from_file(
    recording_path: str | Path,
    frame_index: int | None = None,
    output_path: str | Path | None = None,
    size: tuple[int, int] = (300, 300),
    view: str = "top"
) -> bool:
    """
    Generate thumbnail from a recording file.
    
    Args:
        recording_path: Path to .lidr recording file
        frame_index: Frame index to use (None = 10% into recording)
        output_path: Output path (None = auto-generate next to recording)
        size: Thumbnail dimensions
        view: Camera view
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from app.services.modules.lidar.protocol.recording import RecordingReader
        
        recording_path = Path(recording_path)
        
        # Auto-generate output path if not provided
        if output_path is None:
            output_path = recording_path.with_suffix(".png")
        
        # Open recording
        reader = RecordingReader(str(recording_path))
        
        # Handle specific frame index explicitly
        if frame_index is not None:
            if frame_index >= reader.frame_count:
                logger.warning(f"Frame index {frame_index} out of range (max: {reader.frame_count - 1})")
                frame_index = max(0, reader.frame_count - 1)
            frames_to_try = [frame_index]
        else:
            # Auto-select frames: try up to 10 frames starting from 10% to find a non-empty one
            if reader.frame_count == 0:
                logger.warning("Recording has 0 frames, cannot generate thumbnail")
                return False
                
            frames_to_try = []
            start_pct = 0.1
            for i in range(10):
                pct = start_pct + i * ((1.0 - start_pct) / 10.0)
                idx = min(int(reader.frame_count * pct), reader.frame_count - 1)
                if idx not in frames_to_try:
                    frames_to_try.append(idx)
                    
            if not frames_to_try:
                frames_to_try = [0]
        
        # Read frames and try generating
        for target_index in frames_to_try:
            points, _ = reader.get_frame(target_index)
            
            # Quick check if it's completely empty before attempting full generation
            if points.shape[0] == 0 or np.all(points == 0):
                continue
                
            success = generate_thumbnail(points, output_path, size, view)
            if success:
                return True
                
        logger.warning(f"All tried frames were empty or invalid for {recording_path}")
        return False
    
    except Exception as e:
        logger.error(f"Failed to generate thumbnail from file: {e}", exc_info=True)
        return False
