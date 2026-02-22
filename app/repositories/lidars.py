from typing import Any, Dict, List

from .sqlite import db_conn, new_id


class LidarRepository:
    def list(self) -> List[Dict[str, Any]]:
        with db_conn() as conn:
            rows = conn.execute("SELECT * FROM lidars").fetchall()
            return [dict(row) for row in rows]

    def upsert(self, config: Dict[str, Any]) -> str:
        with db_conn() as conn:
            record_id = config.get("id") or new_id()
            conn.execute(
                """
                INSERT INTO lidars (id, name, launch_args, pipeline_name, mode, pcd_path, x, y, z, roll, pitch, yaw)
                VALUES (:id, :name, :launch_args, :pipeline_name, :mode, :pcd_path, :x, :y, :z, :roll, :pitch, :yaw)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    launch_args=excluded.launch_args,
                    pipeline_name=excluded.pipeline_name,
                    mode=excluded.mode,
                    pcd_path=excluded.pcd_path,
                    x=excluded.x, y=excluded.y, z=excluded.z,
                    roll=excluded.roll, pitch=excluded.pitch, yaw=excluded.yaw
                """,
                {**config, "id": record_id},
            )
            conn.commit()
            return record_id

    def delete(self, lidar_id: str) -> None:
        with db_conn() as conn:
            conn.execute("DELETE FROM lidars WHERE id = ?", (lidar_id,))
            conn.commit()
