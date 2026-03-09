"""Logs endpoint handlers - Pure business logic without routing configuration."""

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Any
from datetime import datetime
import os
import json
import asyncio

from app.core.logging import LOG_FILE


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a log line into structured components."""
    # New format: "2024-02-23 10:30:45 | INFO     | app.services | Message"
    parts = line.split(' | ', 3)
    if len(parts) >= 4:
        return {
            "timestamp": parts[0].strip(),
            "level": parts[1].strip(),
            "module": parts[2].strip(),
            "message": parts[3].strip()
        }
    return None


def get_logs(level: Optional[str], search: Optional[str], offset: int, limit: int) -> List[Dict[str, Any]]:
    """Get paginated application log entries."""
    if not os.path.exists(LOG_FILE):
        return []

    results = []
    count = 0
    with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    entries = (parse_log_line(l) for l in reversed(lines))
    
    for entry in entries:
        if not entry:
            continue
        if level and entry['level'] != level.upper():
            continue
        if search and search.lower() not in entry['message'].lower():
            continue
        if count < offset:
            count += 1
            continue
        results.append(entry)
        count += 1
        if len(results) >= min(limit, 500):
            break

    return results


def download_logs(level: Optional[str], search: Optional[str]):
    """Download filtered log entries as a plain-text file."""
    if not os.path.exists(LOG_FILE):
        raise HTTPException(status_code=404, detail="Log file not found")

    def generate():
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                entry = parse_log_line(line)
                if not entry:
                    continue
                if level and entry['level'] != level.upper():
                    continue
                if search and search.lower() not in entry['message'].lower():
                    continue
                # Format: [2024-02-23 10:30:45] [INFO    ] [app.services] Message
                formatted = f"[{entry['timestamp']}] [{entry['level'].ljust(8)}] [{entry['module'].ljust(20)}] {entry['message']}\n"
                yield formatted

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=lidar_logs_{timestamp}.txt"}
    )


async def logs_websocket_endpoint(websocket: WebSocket, level: Optional[str] = None, search: Optional[str] = None):
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()
    last_inode = None
    position = 0
    logf = None
    try:
        # Seek to end initially if position is 0 to avoid streaming history
        if os.path.exists(LOG_FILE):
            position = os.path.getsize(LOG_FILE)
            
        while True:
            if not os.path.exists(LOG_FILE):
                await asyncio.sleep(1)
                continue
                
            stat = os.stat(LOG_FILE)
            inode = stat.st_ino
            
            if logf is None or inode != last_inode:
                if logf:
                    logf.close()
                logf = open(LOG_FILE, "r", encoding="utf-8", errors="ignore")
                if last_inode is not None and inode != last_inode:
                    # If rotated, start from beginning
                    position = 0
                logf.seek(position)
                last_inode = inode
            
            # Read new lines
            lines = logf.readlines()
            position = logf.tell()
            
            for line in lines:
                entry = parse_log_line(line)
                if not entry:
                    continue
                if level and entry["level"] != level.upper():
                    continue
                if search and search.lower() not in entry["message"].lower():
                    continue
                await websocket.send_text(json.dumps(entry))
                
            await asyncio.sleep(0.5)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if logf:
            try:
                logf.close()
            except Exception:
                pass