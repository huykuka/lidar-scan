# Lidar Recording API: Client Blueprint

Base URL: `http://<host>:<port>/api/v1`. Bodies are JSON.

## 1. Lifecycle

```
POST /recordings/start ──► status: "recording"
        │
POST /recordings/{id}/stop ──► status: "stopping" (returns immediately)
        │   (server finalizes in background: flush, compress, thumbnail, DB insert)
        ▼
GET /recordings ──► appears in `recordings[]` with status: "ready"
```

## 2. Endpoints

### Start recording
`POST /recordings/start`

Request:
```json
{
  "node_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "name": "outdoor-test-run-01",
  "metadata": { "environment": "outdoor", "weather": "clear" }
}
```
| Field | Type | Required | Notes |
|---|---|---|---|
| `node_id` | string | yes | Must be a node in the active graph |
| `name` | string | no | Defaults to `node_id` |
| `metadata` | object | no | Merged over server defaults (`mode`, `pipeline_name`, `pose`) |

Response `200`:
```json
{ "recording_id": "uuid", "file_path": "…/recording_<uuid>.mcap", "started_at": "ISO-8601" }
```
Errors: `404` node not in active graph, `400` invalid request, `500` internal error.

Starting the same node twice creates two independent recordings. There is no duplicate guard.

### Stop recording
`POST /recordings/{recording_id}/stop` (no body)

Response `200`:
```json
{
  "recording_id": "uuid",
  "node_id": "…",
  "status": "stopping",
  "frame_count": 412,
  "duration_seconds": 41.2,
  "message": "Recording is stopping, finalization in progress..."
}
```
Errors: `404` unknown ID (it returns 404 even if the recording has already stopped), `500` internal error.

### List and poll
`GET /recordings?node_id=<optional>`

```json
{
  "recordings": [
    { "id": "", "name": "", "node_id": "", "sensor_id": null, "file_path": "",
      "file_size_bytes": 0, "frame_count": 0, "duration_seconds": 0.0,
      "recording_timestamp": "", "metadata": {}, "thumbnail_path": null,
      "status": "ready", "created_at": "" }
  ],
  "active_recordings": [
    { "recording_id": "", "node_id": "", "frame_count": 0, "duration_seconds": 0.0,
      "started_at": "", "metadata": {}, "status": "recording" }
  ]
}
```
`active_recordings[].status` is `recording` or `stopping`. Saved recordings are `ready`.

### Other endpoints (same router)
Get, delete, download, rename, trim, upload, and thumbnail/frame endpoints. There is also a WebSocket at `/recordings/{id}/stream`. See `app/api/v1/recordings/handler.py`.

## 3. Client rules
1. Store `recording_id` from the start response, because stop needs it.
2. A successful stop does not mean the file is ready. Poll `GET /recordings` until the ID leaves `active_recordings` and appears in `recordings`. A 1–2 s interval is reasonable.
3. Finalization failures are only logged server-side. If the ID never appears in `recordings`, treat it as failed and apply a timeout (e.g. 60 s).
4. After a server restart, recover state by calling `GET /recordings` and checking `active_recordings`.

## 4. Reference snippets

**curl**
```bash
BASE=http://localhost:8005/api/v1
RID=$(curl -s -X POST $BASE/recordings/start -H 'content-type: application/json' \
  -d '{"node_id":"<id>","name":"run-01"}' | jq -r .recording_id)
curl -s -X POST $BASE/recordings/$RID/stop
```

**Python**
```python
import time, requests
BASE = "http://localhost:8005/api/v1"

rid = requests.post(f"{BASE}/recordings/start",
                    json={"node_id": NODE_ID, "name": "run-01"}).json()["recording_id"]
time.sleep(30)
requests.post(f"{BASE}/recordings/{rid}/stop").raise_for_status()

for _ in range(60):
    data = requests.get(f"{BASE}/recordings").json()
    done = next((r for r in data["recordings"] if r["id"] == rid), None)
    if done:
        break
    time.sleep(1)
```

**TypeScript**
```ts
const start = await fetch(`${BASE}/recordings/start`, {
  method: 'POST', headers: {'content-type': 'application/json'},
  body: JSON.stringify({ node_id, name })
}).then(r => r.json());
await fetch(`${BASE}/recordings/${start.recording_id}/stop`, { method: 'POST' });
```

The port in the examples (8005) is a placeholder. Replace it with your backend's port.
