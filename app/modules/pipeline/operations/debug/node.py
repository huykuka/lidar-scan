from typing import List, Any, Callable, Optional
import time
import json
import os
import ftplib
import open3d as o3d
import numpy as np
from ...base import PipelineOperation, _tensor_map_keys

BASE_OUTPUT_DIR = "data/pcd"


class DebugSave(PipelineOperation):
    """
    Saves the current state of the point cloud to a PCD file for debugging.
    Files are written to  data/pcd/<folder>/  on the local filesystem.
    Optionally uploads each file to an FTP server after saving.

    Args:
        folder (str): Sub-folder under data/pcd/ (e.g. "session1" → data/pcd/session1/).
        prefix (str): Prefix for the saved PCD files.
        max_keeps (int): Maximum number of recent local files to keep. Older files are deleted.
        ftp_enabled (bool): Whether to upload files to an FTP server.
        ftp_host (str): FTP server hostname or IP.
        ftp_port (int): FTP server port (default 21).
        ftp_user (str): FTP username.
        ftp_password (str): FTP password.
        ftp_remote_dir (str): Remote directory to upload files into.
    """

    def __init__(
        self,
        folder: str = "debug",
        prefix: str = "pcd",
        max_keeps: int = 10,
        ftp_enabled: bool = False,
        ftp_host: str = "",
        ftp_port: int = 21,
        ftp_user: str = "",
        ftp_password: str = "",
        ftp_remote_dir: str = "/",
    ):
        self.output_dir = os.path.join(BASE_OUTPUT_DIR, folder)
        self.prefix = prefix
        self.max_keeps = int(max_keeps)
        self.saved_files: list[str] = []

        self.ftp_enabled = bool(ftp_enabled)
        self.ftp_host = ftp_host
        self.ftp_port = int(ftp_port)
        self.ftp_user = ftp_user
        self.ftp_password = ftp_password
        self.ftp_remote_dir = ftp_remote_dir

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_pcd(self, filename: str, pcd: Any) -> None:
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            o3d.t.io.write_point_cloud(filename, pcd, write_ascii=True)
        else:
            o3d.io.write_point_cloud(filename, pcd, write_ascii=True)

    def _ftp_upload(self, local_path: str) -> str:
        """Upload *local_path* to the configured FTP server.

        Returns the remote path on success, raises on failure.
        """
        remote_name = os.path.basename(local_path)
        remote_path = self.ftp_remote_dir.rstrip("/") + "/" + remote_name

        with ftplib.FTP() as ftp:
            ftp.connect(self.ftp_host, self.ftp_port, timeout=10)
            ftp.login(self.ftp_user, self.ftp_password)
            # Ensure remote directory exists (best-effort)
            try:
                ftp.mkd(self.ftp_remote_dir)
            except ftplib.error_perm:
                pass  # Already exists
            ftp.cwd(self.ftp_remote_dir)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_name}", f)

        return remote_path

    # ------------------------------------------------------------------
    # PipelineOperation interface
    # ------------------------------------------------------------------

    def apply(self, pcd: Any):
        timestamp = int(time.time() * 1000)
        filename = os.path.join(self.output_dir, f"{self.prefix}_{timestamp}.pcd")

        self._write_pcd(filename, pcd)

        self.saved_files.append(filename)
        while len(self.saved_files) > self.max_keeps:
            oldest = self.saved_files.pop(0)
            if os.path.exists(oldest):
                os.remove(oldest)

        meta: dict = {"debug_file": filename}

        if self.ftp_enabled and self.ftp_host:
            try:
                remote_path = self._ftp_upload(filename)
                meta["ftp_remote_file"] = remote_path
            except Exception as exc:
                meta["ftp_error"] = str(exc)

        return pcd, meta
