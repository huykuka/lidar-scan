from typing import Any, Dict, List

from .sqlite import db_conn, dumps_json, loads_json, new_id


class FusionRepository:
    def list(self) -> List[Dict[str, Any]]:
        with db_conn() as conn:
            rows = conn.execute("SELECT * FROM fusions").fetchall()
            res: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                d["sensor_ids"] = loads_json(d["sensor_ids"])
                res.append(d)
            return res

    def upsert(self, config: Dict[str, Any]) -> str:
        with db_conn() as conn:
            record_id = config.get("id") or new_id()
            sensor_ids_str = dumps_json(config.get("sensor_ids", []))
            conn.execute(
                """
                INSERT INTO fusions (id, name, topic, sensor_ids, pipeline_name)
                VALUES (:id, :name, :topic, :sensor_ids, :pipeline_name)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    topic=excluded.topic,
                    sensor_ids=excluded.sensor_ids,
                    pipeline_name=excluded.pipeline_name
                """,
                {**config, "id": record_id, "sensor_ids": sensor_ids_str},
            )
            conn.commit()
            return record_id

    def delete(self, fusion_id: str) -> None:
        with db_conn() as conn:
            conn.execute("DELETE FROM fusions WHERE id = ?", (fusion_id,))
            conn.commit()
