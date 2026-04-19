# API Contract — 3D Shape Rendering

**Feature:** Real-time 3D shape overlay  
**WebSocket Topic:** `shapes`  
**Transport:** JSON over WebSocket (not binary LIDR)  
**Direction:** Server → Client (broadcast only, read-only channel)

---

## 1. WebSocket Endpoint

```
GET /ws/{topic}
topic = "shapes"
```

Follows the existing WebSocket topic lifecycle (see `protocols.md`). Connection close with code `1001` means the topic was intentionally removed (treat as stream complete). Any other close code should trigger reconnect.

---

## 2. Message Schema

Every message is a single `ShapeFrame` JSON object published once per processed frame.

### `ShapeFrame`

```json
{
  "timestamp": 1713523800.123,
  "shapes": [ /* array of ShapeDescriptor */ ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `float` | Unix epoch seconds (float64) — matches the originating sensor frame |
| `shapes` | `ShapeDescriptor[]` | All currently active shapes from all nodes. Empty array clears all shapes on the frontend. |

---

## 3. Shape Descriptor — Common Fields

Every shape includes these base fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | ✅ | Backend-assigned stable unique ID (16-char hex). Same geometry from the same node always produces the same id. |
| `node_name` | `string` | ✅ | Human-readable name of the emitting DAG node (e.g. `"Cluster Detector"`) |
| `type` | `string` | ✅ | Shape discriminator: `"cube"` \| `"plane"` \| `"label"` |

---

## 4. Shape Types

### 4.1 `cube`

Represents a 3D axis-aligned or oriented bounding box. Derived from Open3D `AxisAlignedBoundingBox` or `OrientedBoundingBox`.

```json
{
  "id": "a3f9c21b88d41e02",
  "node_name": "Cluster Detector",
  "type": "cube",
  "center": [1.2, 0.5, 0.3],
  "size": [0.8, 0.6, 1.2],
  "rotation": [0.0, 0.0, 0.0],
  "color": "#00ff00",
  "opacity": 0.4,
  "wireframe": true,
  "label": "Person (conf: 0.91)"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `center` | `[float, float, float]` | required | World position `[x, y, z]` in meters |
| `size` | `[float, float, float]` | required | Full extents `[sx, sy, sz]` in meters |
| `rotation` | `[float, float, float]` | `[0,0,0]` | Euler rotation `[rx, ry, rz]` in radians (XYZ order) |
| `color` | `string` | `"#00ff00"` | CSS hex color string |
| `opacity` | `float` | `0.4` | 0.0 (transparent) to 1.0 (opaque) |
| `wireframe` | `bool` | `true` | If true, render as wireframe edges only; false = solid fill |
| `label` | `string \| null` | `null` | Optional text label attached to the top of the box |

---

### 4.2 `plane`

Represents an infinite or bounded planar surface (e.g., ground plane fitted via RANSAC).

```json
{
  "id": "b7e41ca099f33d10",
  "node_name": "Ground Segmenter",
  "type": "plane",
  "center": [0.0, 0.0, -0.05],
  "normal": [0.0, 0.0, 1.0],
  "width": 20.0,
  "height": 20.0,
  "color": "#4488ff",
  "opacity": 0.2
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `center` | `[float, float, float]` | required | Plane center in world space |
| `normal` | `[float, float, float]` | required | Unit normal vector |
| `width` | `float` | `10.0` | Rendered patch width in meters |
| `height` | `float` | `10.0` | Rendered patch height in meters |
| `color` | `string` | `"#4488ff"` | CSS hex color string |
| `opacity` | `float` | `0.25` | 0.0 to 1.0 |

---

### 4.3 `label`

Camera-facing billboard (always visible, never occluded by Three.js depth). Used for text annotations in 3D space.

```json
{
  "id": "c1f08bb452aa71e9",
  "node_name": "Cluster Detector",
  "type": "label",
  "position": [1.2, 0.5, 1.5],
  "text": "Cluster A  (42 pts)",
  "font_size": 14,
  "color": "#ffffff",
  "background_color": "#000000cc",
  "scale": 1.0
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `position` | `[float, float, float]` | required | World position `[x, y, z]` |
| `text` | `string` | required | Text to display |
| `font_size` | `int` | `14` | Canvas font size in pixels |
| `color` | `string` | `"#ffffff"` | Text color |
| `background_color` | `string` | `"#000000cc"` | Background fill (supports alpha hex) |
| `scale` | `float` | `1.0` | World-space scale multiplier |

---

## 5. Example Full Frame Payload

```json
{
  "timestamp": 1713523800.341,
  "shapes": [
    {
      "id": "a3f9c21b88d41e02",
      "node_name": "Cluster Detector",
      "type": "cube",
      "center": [1.2, 0.5, 0.3],
      "size": [0.8, 0.6, 1.2],
      "rotation": [0.0, 0.0, 0.0],
      "color": "#00ff00",
      "opacity": 0.4,
      "wireframe": true,
      "label": "Person (conf: 0.91)"
    },
    {
      "id": "b7e41ca099f33d10",
      "node_name": "Ground Segmenter",
      "type": "plane",
      "center": [0.0, 0.0, -0.05],
      "normal": [0.0, 0.0, 1.0],
      "width": 20.0,
      "height": 20.0,
      "color": "#4488ff",
      "opacity": 0.2
    },
    {
      "id": "c1f08bb452aa71e9",
      "node_name": "Cluster Detector",
      "type": "label",
      "position": [1.2, 0.5, 1.5],
      "text": "Person (conf: 0.91)",
      "font_size": 14,
      "color": "#ffffff",
      "background_color": "#000000cc",
      "scale": 1.0
    },
    {
      "id": "d4e52f3711bc90a7",
      "node_name": "Cluster Detector",
      "type": "cube",
      "center": [-3.1, 1.2, 0.7],
      "size": [1.5, 0.9, 1.8],
      "rotation": [0.0, 0.52, 0.0],
      "color": "#ff8800",
      "opacity": 0.35,
      "wireframe": true,
      "label": "Vehicle"
    }
  ]
}
```

---

## 6. Empty Frame (Clear All Shapes)

When no shapes are active (e.g., no objects detected, or all nodes disabled), the server publishes an empty frame. The frontend MUST clear all existing shape objects from the scene on receiving this.

```json
{
  "timestamp": 1713523800.512,
  "shapes": []
}
```

---

## 7. Frontend Mock Data (for parallel development)

The `@fe-dev` MUST mock the WebSocket topic using the example payload in §5 while the backend is being developed.

Suggested mock service stub:

```typescript
// In ShapesWsService — mock mode
if (environment.mockShapes) {
  return of(MOCK_SHAPE_FRAME).pipe(delay(0), repeat({ delay: 100 }));
}
```

`MOCK_SHAPE_FRAME` should include at least one shape of each type to exercise all Three.js builder paths.

---

## 8. Schema Versioning & Forward Compatibility

- Future shape types are added by introducing new `type` string values.
- Existing fields on existing shape types are never removed — only optional fields may be added.
- The frontend MUST silently skip any `type` value it does not recognize (log `console.warn` only).
- The backend MUST NOT change the `id` hashing algorithm without bumping a version field (no version field today; add `"schema_version": 1` to `ShapeFrame` when this becomes necessary).

---

## 9. Error Cases

| Condition | Backend behavior | Frontend behavior |
|-----------|-----------------|-------------------|
| No active shapes | Publish `shapes: []` | Clear all shape objects |
| Node emits shape with empty string `id` | Backend fills id before broadcast (never empty) | If id is `""`, generate a temp local id and log a contract violation warning |
| Malformed JSON from WS | N/A (server-side) | Catch parse error, drop frame, keep existing shapes |
| Unknown `type` field | Forward as-is | Skip silently, log `console.warn` |
| Shape count > 500 | Backend caps and logs warning | Frontend renders whatever arrives |
