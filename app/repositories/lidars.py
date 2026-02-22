from typing import Any, Dict, List

from .sqlite import db_conn, new_id


class LidarRepository:
    def list(self) -> List[Dict[str, Any]]:
        with db_conn() as conn:
            rows = conn.execute("SELECT * FROM lidars").fetchall()
            res: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                d["enabled"] = bool(d.get("enabled", 1))
                res.append(d)
            return res

    def upsert(self, config: Dict[str, Any]) -> str:
        with db_conn() as conn:
            record_id = config.get("id") or new_id()

            # Preserve topic_prefix unless explicitly provided; allow user edits while
            # keeping it URL-friendly and unique.
            topic_prefix = config.get("topic_prefix", None)
            if topic_prefix is None:
                row = conn.execute(
                    "SELECT topic_prefix FROM lidars WHERE id = ?",
                    (record_id,),
                ).fetchone()
                topic_prefix = (row[0] if row else None)

            import re

            def _slugify(val: str) -> str:
                base = re.sub(r"[^A-Za-z0-9_-]+", "_", (val or "").strip())
                base = re.sub(r"_+", "_", base).strip("_-")
                return base or "sensor"

            desired = config.get("name") or record_id
            requested = _slugify(topic_prefix) if topic_prefix else _slugify(desired)

            in_use = {
                (r[0] or "").strip()
                for r in conn.execute(
                    "SELECT topic_prefix FROM lidars WHERE id != ? AND topic_prefix IS NOT NULL",
                    (record_id,),
                ).fetchall()
            }

            if requested not in in_use:
                topic_prefix = requested
            else:
                suffix = _slugify(record_id)[:8]
                candidate = f"{requested}_{suffix}" if suffix else f"{requested}_1"
                i = 2
                while candidate in in_use:
                    candidate = f"{requested}_{suffix}_{i}" if suffix else f"{requested}_{i}"
                    i += 1
                topic_prefix = candidate

            # Preserve enabled flag unless explicitly provided
            enabled = config.get("enabled", None)
            if enabled is None:
                row = conn.execute("SELECT enabled FROM lidars WHERE id = ?", (record_id,)).fetchone()
                enabled = (row[0] if row else 1)
            enabled_val = 1 if bool(enabled) else 0

            conn.execute(
                """
                INSERT INTO lidars (id, name, topic_prefix, launch_args, pipeline_name, mode, pcd_path, x, y, z, roll, pitch, yaw, enabled)
                VALUES (:id, :name, :topic_prefix, :launch_args, :pipeline_name, :mode, :pcd_path, :x, :y, :z, :roll, :pitch, :yaw, :enabled)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    topic_prefix=excluded.topic_prefix,
                    launch_args=excluded.launch_args,
                    pipeline_name=excluded.pipeline_name,
                    mode=excluded.mode,
                    pcd_path=excluded.pcd_path,
                    x=excluded.x, y=excluded.y, z=excluded.z,
                    roll=excluded.roll, pitch=excluded.pitch, yaw=excluded.yaw,
                    enabled=excluded.enabled
                """,
                {
                    **config,
                    "id": record_id,
                    "topic_prefix": topic_prefix,
                    "enabled": enabled_val,
                },
            )
            conn.commit()
            return record_id

    def set_enabled(self, lidar_id: str, enabled: bool) -> None:
        with db_conn() as conn:
            conn.execute(
                "UPDATE lidars SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, lidar_id),
            )
            conn.commit()

    def delete(self, lidar_id: str) -> None:
        with db_conn() as conn:
            conn.execute("DELETE FROM lidars WHERE id = ?", (lidar_id,))
            conn.commit()
