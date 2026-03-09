# Open3D-ML Integration — QA Tasks & Test Cases

**Feature:** Open3D-ML DAG Node Integration  
**Assigned to:** @qa  
**Status:** Planning → Development → Testing → Complete  
**Date Created:** 2026-03-09  

---

## 📋 Overview

This document defines comprehensive QA tasks and test cases for the Open3D-ML integration feature. Testing follows a **Test-Driven Development (TDD)** approach:

1. **Tests are written FIRST** (before implementation is complete)
2. **Tests fail initially** as features are still being developed
3. **Tests pass once** implementation is complete
4. **All test artifacts** are committed alongside code

Testing is organized across **five core concern areas**:
- **Unit Tests** (Backend Python / Frontend TypeScript)
- **Integration Tests** (Backend DAG + API)
- **Protocol Tests** (LIDR v2 binary encoding/decoding)
- **Performance Tests** (Latency, memory, non-blocking async)
- **Graceful Degradation** (Torch unavailable, missing dependencies)

---

## 🎯 TDD Preparation Phase

Before development begins on any feature, all test scaffolds must exist (marked as `[ ]`):

### Backend Test Files
- [ ] `tests/test_ml_registry.py` — ML Model Registry unit tests
- [ ] `tests/test_ml_nodes.py` — Semantic Segmentation & Object Detection node tests
- [ ] `tests/test_ml_api.py` — REST API endpoint tests
- [ ] `tests/test_lidr_v2.py` — WebSocket protocol v2 packing/unpacking tests
- [ ] `tests/fixtures/ml_test_fixtures.py` — Mocked models, synthetic data

### Frontend Test Files
- [ ] `web/src/app/ml/services/lidr-v2-decoder.service.spec.ts` — v2 frame decoder tests
- [ ] `web/src/app/ml/services/ml-api.service.spec.ts` — API service mock tests
- [ ] `web/src/app/ml/services/bounding-box-renderer.service.spec.ts` — Three.js pool management
- [ ] `web/src/app/ml/components/ml-node-inspector.component.spec.ts` — Node config UI
- [ ] `web/src/app/ml/components/ml-label-legend.component.spec.ts` — Label legend rendering
- [ ] `web/src/app/ml/components/bounding-box-overlay.component.spec.ts` — Box label overlays
- [ ] `tests/e2e/ml-workflow.e2e.spec.ts` — End-to-end workflow tests

---

## 1️⃣ UNIT TESTS — Backend (ML Model Registry & Nodes)

### Registry Singleton & Availability

**QA-BE-UNIT-001:** MLModelRegistry Singleton Instance Sharing
```
GIVEN: MLModelRegistry class with _instance class variable
WHEN: get_instance() called twice in same process
THEN: both calls return identical object (same id())
ACCEPTANCE: assertEqual(id(reg1), id(reg2))
```
- **Test File:** `tests/test_ml_registry.py::test_registry_singleton`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-BE-UNIT-002:** List Available Models
```
GIVEN: MLModelRegistry.list_available() called
WHEN: no models have been loaded yet
THEN: returns list of exactly 4 MLModelInfo dicts
  AND: each has model_key format "Name__Dataset" (double underscore)
  AND: keys are: RandLANet__SemanticKITTI, KPFCNN__SemanticKITTI, PointPillars__KITTI, PointRCNN__KITTI
ACCEPTANCE: 
  - len(models) == 4
  - all('__' in m.model_key for m in models)
```
- **Test File:** `tests/test_ml_registry.py::test_list_available_models`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-BE-UNIT-003:** Get Status for Never-Loaded Model
```
GIVEN: MLModelRegistry initialized
WHEN: get_status("RandLANet__SemanticKITTI") called
  AND: model has never been loaded
THEN: status field is "not_loaded"
  AND: loaded_at is None
  AND: weight_cached is determined by os.path.exists(weights_dir)
ACCEPTANCE: response.status == "not_loaded"
```
- **Test File:** `tests/test_ml_registry.py::test_status_not_loaded`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-BE-UNIT-004:** Weight Cache Hit (File Exists)
```
GIVEN: MLModelRegistry with mocked os.path.exists returning True
WHEN: get_or_load("RandLANet__SemanticKITTI", device="cpu") called
THEN: no HTTP download is triggered
  AND: status transitions: not_loaded → loading → ready (skips downloading)
  AND: weight_cached is True
ACCEPTANCE: 
  - mock_urllib.urlretrieve NOT called
  - status changes reflect load → ready path
```
- **Test File:** `tests/test_ml_registry.py::test_weight_cache_hit`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Setup:** Use `unittest.mock.patch('os.path.exists', return_value=True)`

**QA-BE-UNIT-005:** Weight Cache Miss (File Missing, Download Required)
```
GIVEN: MLModelRegistry with mocked os.path.exists returning False
WHEN: get_or_load("RandLANet__SemanticKITTI", device="cpu") called
THEN: HTTP download is triggered via urllib.urlretrieve
  AND: status transitions: not_loaded → downloading → loading → ready
  AND: download_progress_pct increments from 0 → 100
ACCEPTANCE: 
  - mock_urllib.urlretrieve is called exactly once
  - status == "downloading" during download phase
  - download_progress_pct > 0
```
- **Test File:** `tests/test_ml_registry.py::test_weight_cache_miss_triggers_download`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Mock Data:** Provide mock 100-byte file instead of real weights

---

### Semantic Segmentation Node Tests

**QA-BE-UNIT-006:** SemanticSegmentationNode Output Shape (Happy Path)
```
GIVEN: SemanticSegmentationNode configured with RandLANet model
  AND: mocked MLModelRegistry returning status="ready"
  AND: input payload with numpy array (N=100, 14 columns)
WHEN: on_input(payload) called with model status ready
THEN: output payload has:
  - points shape (100, 15) — one extra label column
  - ml_labels key with shape (100,) and dtype int32
  - ml_scores key with shape (100, 19) for SemanticKITTI classes
  - ml_num_classes = 19
  - ml_class_names contains 19 class strings
  - ml_color_map is 19×3 RGB list
ACCEPTANCE:
  - output_payload['points'].shape == (100, 15)
  - output_payload['ml_labels'].dtype == np.int32
  - output_payload['ml_labels'].shape == (100,)
```
- **Test File:** `tests/test_ml_nodes.py::test_semantic_seg_output_shape`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Mock:** `MLModelRegistry.get_or_load()` returns mock pipeline with `run_inference()` returning synthetic labels

**QA-BE-UNIT-007:** SemanticSegmentationNode Warm-Up Pass-Through
```
GIVEN: SemanticSegmentationNode 
  AND: mocked registry returning status="loading" (model not ready)
WHEN: on_input(payload) called with (100, 14) input
THEN: output points shape remains (100, 14) — unchanged
  AND: ml_labels key is NOT added to payload
  AND: payload is forwarded unmodified to downstream
ACCEPTANCE:
  - output_payload['points'].shape == (100, 14)
  - 'ml_labels' NOT in output_payload
```
- **Test File:** `tests/test_ml_nodes.py::test_semantic_seg_warmup_passthrough`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-BE-UNIT-008:** SemanticSegmentationNode Inference Latency Tracking
```
GIVEN: SemanticSegmentationNode 
WHEN: on_input() called multiple times (5+ calls)
THEN: get_status() returns:
  - inference_count incremented correctly
  - avg_inference_ms is rolling average of all calls (not just last)
  - last_inference_at timestamp is recent
ACCEPTANCE:
  - inference_count == 5 after 5 calls
  - avg_inference_ms is within expected range (mock timing)
  - avg changes only slightly on new measurements
```
- **Test File:** `tests/test_ml_nodes.py::test_semantic_seg_latency_tracking`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-BE-UNIT-009:** SemanticSegmentationNode Error Recovery
```
GIVEN: SemanticSegmentationNode 
  AND: mocked pipeline.run_inference() raising RuntimeError("CUDA OOM")
WHEN: on_input(payload) called
THEN: 
  - original payload is forwarded unmodified to downstream (no data loss)
  - last_error field is set to error message in node status
  - no exception bubbles up (error caught and logged)
ACCEPTANCE:
  - manager.forward_data() is called with original payload
  - get_status()['last_error'] contains error message
```
- **Test File:** `tests/test_ml_nodes.py::test_semantic_seg_error_recovery`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

### Object Detection Node Tests

**QA-BE-UNIT-010:** ObjectDetectionNode Output (Points Unchanged)
```
GIVEN: ObjectDetectionNode configured with PointPillars model
  AND: mocked registry returning status="ready"
  AND: input payload with (N=500, 14) points
WHEN: on_input(payload) called
THEN: output points shape is (500, 14) — EXACTLY same as input
  AND: bounding_boxes key is in output payload
  AND: bounding_boxes contains BoundingBox3D dicts with fields: id, label, confidence, center, size, yaw, color
ACCEPTANCE:
  - output_payload['points'].shape == input_shape
  - 'bounding_boxes' in output_payload
  - len(output_payload['bounding_boxes']) > 0
```
- **Test File:** `tests/test_ml_nodes.py::test_object_detection_output`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-BE-UNIT-011:** ObjectDetectionNode Confidence Threshold Filtering
```
GIVEN: ObjectDetectionNode with confidence_threshold=0.5
  AND: mocked pipeline returning 10 boxes: 7 with confidence ≥ 0.5, 3 with < 0.5
WHEN: on_input(payload) called
THEN: output bounding_boxes list contains exactly 7 boxes
  AND: all boxes have confidence ≥ 0.5
ACCEPTANCE:
  - len(output_payload['bounding_boxes']) == 7
  - all(box['confidence'] >= 0.5 for box in boxes)
```
- **Test File:** `tests/test_ml_nodes.py::test_detection_confidence_threshold`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-BE-UNIT-012:** ObjectDetectionNode Pass-Through on Load
```
GIVEN: ObjectDetectionNode 
  AND: registry returning status="loading"
WHEN: on_input(payload) called
THEN: output points and payload are forwarded unchanged
  AND: bounding_boxes is NOT added
ACCEPTANCE:
  - output_payload == input_payload (bit-for-bit)
  - 'bounding_boxes' NOT in output_payload
```
- **Test File:** `tests/test_ml_nodes.py::test_detection_warmup_passthrough`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

## 2️⃣ UNIT TESTS — Frontend (Angular Services & Components)

### LIDR v2 Decoder Service

**QA-FE-UNIT-001:** Decode v1 Frame (Backward Compatibility)
```
GIVEN: LidrV2DecoderService
  AND: binary buffer with magic="LIDR", version=1, N=100 points
WHEN: decode(buffer) called
THEN: returns object with:
  - timestamp: number
  - positions: Float32Array (N×3 points)
  - labels: null
  - boxes: []
ACCEPTANCE:
  - result.version == 1
  - result.labels === null
  - result.boxes.length == 0
```
- **Test File:** `web/src/app/ml/services/lidr-v2-decoder.service.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Test Data:** Use `ArrayBuffer` constructed with typed arrays (no file I/O)

**QA-FE-UNIT-002:** Decode v2 Frame with Labels Only
```
GIVEN: LidrV2DecoderService
  AND: v2 buffer with has_labels=1, has_boxes=0, N=250 points
WHEN: decode(buffer) called
THEN: returns:
  - labels: Int32Array with N elements
  - boxes: empty array
  - positions: correct Float32Array
ACCEPTANCE:
  - result.labels !== null
  - result.labels.length == 250
  - result.boxes.length == 0
```
- **Test File:** `web/src/app/ml/services/lidr-v2-decoder.service.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-FE-UNIT-003:** Decode v2 Frame with Boxes Only
```
GIVEN: LidrV2DecoderService
  AND: v2 buffer with has_labels=0, has_boxes=1, N=150 points, 3 boxes in JSON
WHEN: decode(buffer) called
THEN: returns:
  - labels: null
  - boxes: array of 3 BoundingBox3D objects
  - each box has: id, label, label_index, confidence, center, size, yaw, color
ACCEPTANCE:
  - result.labels === null
  - result.boxes.length == 3
  - result.boxes[0].hasOwnProperty('confidence')
```
- **Test File:** `web/src/app/ml/services/lidr-v2-decoder.service.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-FE-UNIT-004:** Decode v2 Frame with Both Labels and Boxes
```
GIVEN: LidrV2DecoderService
  AND: v2 buffer with both flags set, N=500 points, 5 boxes
WHEN: decode(buffer) called
THEN: both labels and boxes are populated correctly
ACCEPTANCE:
  - result.labels !== null && result.labels.length == 500
  - result.boxes.length == 5
```
- **Test File:** `web/src/app/ml/services/lidr-v2-decoder.service.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-FE-UNIT-005:** Zero-Copy Float32Array View
```
GIVEN: LidrV2DecoderService
  AND: source ArrayBuffer with 100 points
WHEN: decode(buffer) called
THEN: returned positions Float32Array is a VIEW (not copy)
  AND: modifying positions[0] affects source buffer
ACCEPTANCE:
  - result.positions.buffer === source.buffer
  - byteOffset is 24 (correct)
```
- **Test File:** `web/src/app/ml/services/lidr-v2-decoder.service.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

### ML API Service (Mocked)

**QA-FE-UNIT-006:** MlApiService getModels() Observable
```
GIVEN: MlApiService with mocked HttpClient
WHEN: getModels() called
THEN: returns Observable that emits MlModelInfo[] with 4 items
  AND: each item matches api-spec.md §8 mock data
ACCEPTANCE:
  - observable emits exactly once
  - data.length == 4
  - data[0].model_key == "RandLANet__SemanticKITTI"
```
- **Test File:** `web/src/app/ml/services/ml-api.service.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Setup:** Use `HttpTestingController` or `of()` stub

**QA-FE-UNIT-007:** MlApiService getModelStatus() on 404
```
GIVEN: MlApiService 
  AND: HttpClient mock configured to return 404 for unknown model
WHEN: getModelStatus("UnknownModel") called
THEN: Observable throws HttpErrorResponse with status 404
ACCEPTANCE:
  - subscribe error handler called
  - error.status == 404
```
- **Test File:** `web/src/app/ml/services/ml-api.service.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

### BoundingBoxRendererService

**QA-FE-UNIT-008:** BoundingBoxRendererService Initialization
```
GIVEN: BoundingBoxRendererService initialized with THREE.Scene
WHEN: constructor called
THEN: 256 THREE.LineSegments objects are created
  AND: all 256 are added to scene with visible=false
  AND: no allocations happen afterward on update()
ACCEPTANCE:
  - scene.children.length >= 256
  - all objects have type "LineSegments"
```
- **Test File:** `web/src/app/ml/services/bounding-box-renderer.service.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Setup:** Use THREE mock or minimal Three.js in test

**QA-FE-UNIT-009:** BoundingBoxRendererService Update (No Allocations)
```
GIVEN: BoundingBoxRendererService with 256 pool objects
  AND: Chrome DevTools memory tracking
WHEN: update([box1, box2, box3]) called (3 boxes)
  AND: update([box1, box2]) called (2 boxes) — different data
  AND: update([]) called (clear)
THEN: no new geometry objects allocated per call
  AND: only visibility flags change
ACCEPTANCE:
  - AllocatedObjectCount remains constant
  - pool[0].visible === true after update (3 boxes)
  - pool[3].visible === false after update (3 boxes)
```
- **Test File:** `web/src/app/ml/services/bounding-box-renderer.service.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

### ML Node Inspector Component

**QA-FE-UNIT-010:** MlNodeInspectorComponent Model Dropdown
```
GIVEN: MlNodeInspectorComponent for ml_semantic_segmentation node type
  AND: MlApiService mock returning 4 models
WHEN: component initialized
THEN: model_name dropdown populated with:
  - RandLANet
  - KPFCNN
  - PointTransformer
  (object detection models filtered out)
ACCEPTANCE:
  - dropdown options contain exactly 3 segmentation models
  - detectChanges triggers Signal update
```
- **Test File:** `web/src/app/ml/components/ml-node-inspector.component.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

### ML Label Legend Component

**QA-FE-UNIT-011:** MlLabelLegendComponent Rendering
```
GIVEN: MlLabelLegendComponent
  AND: input classNames: ["unlabelled", "car", "bicycle", ... ] (19 items)
  AND: input colorMap: [[0,0,0], [245,150,100], ... ] (19 items)
WHEN: component rendered
THEN: 19 rows displayed in legend
  AND: each row has:
    - colour swatch matching colorMap[i]
    - class name text
ACCEPTANCE:
  - querySelectorAll('.legend-item').length == 19
  - first item text contains "unlabelled"
```
- **Test File:** `web/src/app/ml/components/ml-label-legend.component.spec.ts`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

## 3️⃣ INTEGRATION TESTS — Backend API

### REST Endpoint Tests

**QA-INT-API-001:** GET /api/v1/ml/models — Valid Response
```
GIVEN: FastAPI test client
WHEN: GET /api/v1/ml/models called
THEN: response status is 200
  AND: body is JSON array with 4 items
  AND: each item is valid MLModelInfo (Pydantic model)
  AND: all required fields present per api-spec.md §1
ACCEPTANCE:
  - response.status_code == 200
  - len(response.json()) == 4
  - response.json()[0]['model_key'] in expected keys
```
- **Test File:** `tests/test_ml_api.py::test_get_models`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-INT-API-002:** GET /api/v1/ml/models/{model_key}/status — Valid Model
```
GIVEN: FastAPI test client
WHEN: GET /api/v1/ml/models/RandLANet__SemanticKITTI/status called
THEN: response status is 200
  AND: body is valid MLModelStatus Pydantic model
  AND: status field is "not_loaded" (never loaded before)
ACCEPTANCE:
  - response.status_code == 200
  - response.json()['status'] in ["not_loaded", "downloading", "loading", "ready", "error"]
```
- **Test File:** `tests/test_ml_api.py::test_get_status_valid`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-INT-API-003:** GET /api/v1/ml/models/{model_key}/status — Invalid Model
```
GIVEN: FastAPI test client
WHEN: GET /api/v1/ml/models/FakeModel__Unknown/status called
THEN: response status is 404
  AND: body contains "detail" field with error message
ACCEPTANCE:
  - response.status_code == 404
  - "Unknown model_key" in response.json()['detail']
```
- **Test File:** `tests/test_ml_api.py::test_get_status_invalid_key`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-INT-API-004:** POST /api/v1/ml/models/{model_key}/load — First Call
```
GIVEN: FastAPI test client
  AND: model registry with RandLANet not loaded
WHEN: POST /api/v1/ml/models/RandLANet__SemanticKITTI/load with body {"device": "cpu"}
THEN: response status is 202 Accepted
  AND: body contains message "loading initiated in background"
ACCEPTANCE:
  - response.status_code == 202
  - response.json()['status'] in ["downloading", "loading"]
```
- **Test File:** `tests/test_ml_api.py::test_load_model_first_call`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-INT-API-005:** POST /api/v1/ml/models/{model_key}/load — Already Loading
```
GIVEN: FastAPI test client
  AND: model RandLANet is already in "loading" state
WHEN: POST /api/v1/ml/models/RandLANet__SemanticKITTI/load called again
THEN: response status is 409 Conflict
  AND: body indicates model already loading
ACCEPTANCE:
  - response.status_code == 409
  - "already loaded" in response.json()['message'].lower() or response.status_code == 202 (idempotent is OK too)
```
- **Test File:** `tests/test_ml_api.py::test_load_model_already_loading`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-INT-API-006:** DELETE /api/v1/ml/models/{model_key} — Loaded Model
```
GIVEN: FastAPI test client
  AND: RandLANet currently loaded in registry
WHEN: DELETE /api/v1/ml/models/RandLANet__SemanticKITTI called
THEN: response status is 200
  AND: subsequent GET /status returns "not_loaded"
ACCEPTANCE:
  - response.status_code == 200
  - response.json()['status'] == "unloaded"
```
- **Test File:** `tests/test_ml_api.py::test_delete_model_loaded`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-INT-API-007:** DELETE /api/v1/ml/models/{model_key} — Not Loaded
```
GIVEN: FastAPI test client
  AND: RandLANet is NOT in registry (never loaded)
WHEN: DELETE /api/v1/ml/models/RandLANet__SemanticKITTI called
THEN: response status is 404
ACCEPTANCE:
  - response.status_code == 404
```
- **Test File:** `tests/test_ml_api.py::test_delete_model_not_loaded`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-INT-API-008:** ML Router Mounted at Correct Path
```
GIVEN: FastAPI app with ML router registered
WHEN: GET /api/v1/ml/models called
THEN: response is 200 (not 404 "path not found")
ACCEPTANCE:
  - response.status_code in [200, 400, 401, 403] (any valid response, not 404)
```
- **Test File:** `tests/test_ml_api.py::test_ml_router_mounted`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-INT-API-009:** Regression — Existing API Endpoints Unaffected
```
GIVEN: FastAPI test client
WHEN: GET /api/v1/nodes called
  AND: GET /api/v1/edges called
  AND: other existing endpoints called
THEN: all endpoints return same status as before ML feature integration
ACCEPTANCE:
  - no existing endpoints return 500 errors due to ML imports
```
- **Test File:** `tests/test_ml_api.py::test_existing_endpoints_unaffected`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

## 4️⃣ PROTOCOL TESTS — LIDR v2

### Frame Packing

**QA-PROT-001:** Pack v2 Frame with Labels
```
GIVEN: LIDR frame packer with payload containing ml_labels (100 items)
WHEN: pack_frame(payload, topic="/test") called
THEN: output bytes contain:
  - Magic bytes "LIDR" at offset 0
  - Version uint32=2 at offset 4
  - Flags with bit 0 set (has_labels)
  - XYZ block at offset 24
  - Labels block at offset 24 + 100*12
ACCEPTANCE:
  - bytes[0:4] == b'LIDR'
  - struct.unpack('<I', bytes[4:8])[0] == 2
  - struct.unpack('<I', bytes[20:24])[0] & 0x01 == 1
```
- **Test File:** `tests/test_lidr_v2.py::test_pack_v2_with_labels`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-PROT-002:** Pack v2 Frame with Boxes
```
GIVEN: LIDR frame packer with payload containing bounding_boxes list
WHEN: pack_frame(payload) called
THEN: output bytes contain:
  - Flags with bit 1 set (has_boxes)
  - JSON blob appended after labels (or XYZ if no labels)
  - JSON blob prefixed with uint32 byte length
ACCEPTANCE:
  - flags & 0x02 == 2
  - JSON is valid (can be decoded)
```
- **Test File:** `tests/test_lidr_v2.py::test_pack_v2_with_boxes`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-PROT-003:** Pack v1 Fallback (No ML Keys)
```
GIVEN: LIDR frame packer with payload containing NO ml_labels, NO bounding_boxes
WHEN: pack_frame(payload) called
THEN: output uses LIDR v1 format:
  - Version field == 1
  - No flags field (or flags ignored)
  - Backward compatible with v1 decoders
ACCEPTANCE:
  - struct.unpack('<I', bytes[4:8])[0] == 1
```
- **Test File:** `tests/test_lidr_v2.py::test_pack_v1_fallback`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-PROT-004:** Byte Offset Alignment
```
GIVEN: LIDR v2 frame with N=65536 points
WHEN: pack_frame() called with labels and boxes
THEN: verify byte offsets:
  - XYZ starts at byte 24
  - Labels start at byte 24 + N*12 (exactly)
  - JSON length uint32 starts at byte 24 + N*12 + N*4
  - JSON blob starts at above + 4
ACCEPTANCE:
  - All offsets match expected calculations
```
- **Test File:** `tests/test_lidr_v2.py::test_byte_offset_alignment`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

### Round-Trip Decoding

**QA-PROT-005:** Round-Trip Encode/Decode with Labels
```
GIVEN: Original numpy array points (100, 14) and labels (100,)
WHEN: backend pack_frame() → serialize to bytes
  AND: frontend decode() consumes bytes
THEN: decoded positions and labels match original (within float32 precision)
ACCEPTANCE:
  - np.allclose(original_xyz, decoded_positions, atol=1e-6)
  - np.array_equal(original_labels, decoded_labels)
```
- **Test File:** `tests/test_lidr_v2.py::test_roundtrip_labels`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-PROT-006:** Large Frame (65k Points)
```
GIVEN: LIDR frame with N=65536 points, labels, and 50 boxes
WHEN: pack_frame() called
THEN: no buffer overflow; frame size correct
  AND: decode() unpacks without error
ACCEPTANCE:
  - frame_size == 24 + 65536*12 + 65536*4 + json_size + 4
  - decode() succeeds without truncation
```
- **Test File:** `tests/test_lidr_v2.py::test_large_frame_65k_points`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

## 5️⃣ PERFORMANCE TESTS

### Inference Latency

**QA-PERF-001:** NFR-01 RandLA-Net Inference Latency ≤ 200ms
```
GIVEN: RandLA-Net model loaded on CPU (no GPU)
  AND: 65k-point numpy array
WHEN: run_inference() called 5 times (warm run, exclude first cold start)
THEN: average latency ≤ 200ms
ACCEPTANCE:
  - avg(latencies[1:]) <= 0.200 seconds
  - Log actual value to qa-report.md
```
- **Test File:** `tests/test_ml_perf.py::test_nfr01_randlanet_latency`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Execution:** Must run with `pytest --benchmark` on reference hardware

**QA-PERF-002:** Memory Footprint
```
GIVEN: RandLA-Net model loading on CPU
WHEN: psutil.Process().memory_info().rss sampled before load, after load
THEN: increase ≤ 700 MB (per technical.md table)
ACCEPTANCE:
  - (after_memory - before_memory) / 1e6 <= 700
```
- **Test File:** `tests/test_ml_perf.py::test_memory_footprint`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Note:** Install `psutil` for testing

**QA-PERF-003:** Throttle Mechanism Effectiveness
```
GIVEN: Segmentation node with throttle_ms=200
  AND: input frames arriving at 30 fps (33ms intervals)
WHEN: 10 seconds of frames sent to node
THEN: inference is executed ≤ 50 times (not 300 times)
ACCEPTANCE:
  - inference_count <= 50 (5 fps max)
```
- **Test File:** `tests/test_ml_perf.py::test_throttle_effectiveness`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-PERF-004:** AsyncIO Non-Blocking
```
GIVEN: FastAPI app with ML inference running in thread
  AND: concurrent /health endpoint check
WHEN: heavy inference task runs in background
  AND: /health endpoint is called
THEN: /health response time < 50ms (event loop not blocked)
ACCEPTANCE:
  - health_check_latency < 0.050 seconds
```
- **Test File:** `tests/test_ml_perf.py::test_asyncio_non_blocking`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-PERF-005:** LRU Eviction Under Memory Pressure
```
GIVEN: MLModelRegistry with capacity 2 models
  AND: first two models loaded
WHEN: third model load requested
THEN: oldest model is unloaded (evicted)
  AND: memory is freed
ACCEPTANCE:
  - registry._models contains only newest 2 models
  - memory usage drops after eviction
```
- **Test File:** `tests/test_ml_perf.py::test_lru_eviction`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-PERF-006:** Three.js Frame Rate with 65k Points + Labels
```
GIVEN: Angular viewer with 65k-point cloud, colour-by-label active
WHEN: browser DevTools FPS monitor running
THEN: sustained FPS ≥ 55 (no drops below 55)
ACCEPTANCE:
  - Chrome DevTools reports average FPS >= 55 over 10 seconds
  - No jank visible in visual recording
```
- **Test File:** `tests/e2e/ml-performance.e2e.spec.ts::test_three_js_fps`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Execution:** Requires headless Chrome + Lighthouse

---

## 6️⃣ GRACEFUL DEGRADATION TESTS

### Torch Unavailable Scenario

**QA-DEGRAD-001:** Server Start Without Torch
```
GIVEN: environment variable DISABLE_TORCH=1 (mock torch unavailable)
WHEN: FastAPI server started
THEN: server starts successfully (no exception)
  AND: logging shows "torch not available" at startup
ACCEPTANCE:
  - Server port listening
  - No traceback in stdout
```
- **Test File:** `tests/test_graceful_degradation.py::test_server_start_no_torch`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Setup:** Use `unittest.mock.patch('builtins.__import__')` to simulate missing torch

**QA-DEGRAD-002:** Load Model Endpoint Without Torch
```
GIVEN: torch unavailable
WHEN: POST /api/v1/ml/models/RandLANet__SemanticKITTI/load called
THEN: response status is 503 Service Unavailable (or 400 Bad Request)
  AND: body contains "torch not available" message
ACCEPTANCE:
  - response.status_code in [400, 503]
  - "torch" in response.json()['detail'].lower()
```
- **Test File:** `tests/test_graceful_degradation.py::test_load_without_torch`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-DEGRAD-003:** ML Node Status Without Torch
```
GIVEN: torch unavailable
  AND: ml_semantic_segmentation node in DAG
WHEN: get_status() called on ML node
THEN: status field shows "torch not available"
  AND: running field is false
  AND: no crash
ACCEPTANCE:
  - node.get_status()['last_error'] contains "torch"
  - node.get_status()['running'] == false
```
- **Test File:** `tests/test_graceful_degradation.py::test_ml_node_status_no_torch`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-DEGRAD-004:** Data Pass-Through Without Torch
```
GIVEN: torch unavailable
  AND: ml_semantic_segmentation node with data flowing through
WHEN: on_input(payload) called 10 times
THEN: all 10 payloads are forwarded unmodified to downstream
  AND: no data loss
ACCEPTANCE:
  - all 10 payloads forwarded
  - shapes match input (no columns added)
```
- **Test File:** `tests/test_graceful_degradation.py::test_data_passthrough_no_torch`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-DEGRAD-005:** GET /api/v1/ml/models Without Torch
```
GIVEN: torch unavailable
WHEN: GET /api/v1/ml/models called
THEN: response status is 200 (not 503)
  AND: model catalogue is returned (static config)
  AND: all models have status "not_loaded" (not "error")
ACCEPTANCE:
  - response.status_code == 200
  - len(response.json()) == 4
  - all(m['status'] in ["not_loaded", "available"] for m in response.json())
```
- **Test File:** `tests/test_graceful_degradation.py::test_models_catalogue_no_torch`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

## 7️⃣ ACCEPTANCE CRITERIA VALIDATION

These tests verify that each functional requirement from `requirements.md` is met.

**QA-AC-001:** FR-01 — Drop Segmentation Node & Connect Downstream
```
Given: Angular flow-canvas open
When: ml_semantic_segmentation node dragged onto canvas
  AND: connected downstream of downsample node
Then: node appears in canvas, port icons match
  AND: backend GraphQL query returns valid node config
Acceptance: Visual verification + backend node data structure check
```
- **Test File:** `tests/e2e/ml-workflow.e2e.spec.ts::test_fr01_drop_segmentation_node`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-002:** FR-02 — Model Dropdown Populates from API
```
Given: ml_semantic_segmentation node inspector open
When: "Model" dropdown clicked
Then: dropdown options come from GET /api/v1/ml/models
  AND: options are NOT hardcoded
  AND: changing backend mock changes UI options
Acceptance: HTTP request logged in DevTools; model list matches API response
```
- **Test File:** `tests/e2e/ml-workflow.e2e.spec.ts::test_fr02_model_dropdown_dynamic`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-003:** FR-03 — Weight Auto-Download & Caching
```
Given: RandLA-Net weights not in local cache
When: POST /api/v1/ml/models/RandLANet__SemanticKITTI/load called
  AND: download completes
  AND: server restarted
  AND: load called again
Then: second load is instant (file already cached)
  AND: no re-download
Acceptance: File exists in ./models/ after first load; no HTTP request on restart
```
- **Test File:** `tests/test_ml_acceptance.py::test_fr03_weight_cache`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass
- **Note:** Requires filesystem write access

**QA-AC-004:** FR-04 — Single Model Load (No Per-Frame Reload)
```
Given: SemanticSegmentationNode with RandLA-Net
When: on_input() called 100 times
Then: pipeline.load_ckpt() is called exactly once
  AND: subsequent calls reuse same loaded model
Acceptance: Instrumented load_ckpt() call count == 1
```
- **Test File:** `tests/test_ml_acceptance.py::test_fr04_single_load`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-005:** FR-05 — Inference on Threadpool (Non-Blocking)
```
Given: SemanticSegmentationNode running heavy inference
  AND: asyncio event loop monitoring via asyncio debug mode
When: on_input() called
Then: run_inference() is called via asyncio.to_thread()
  AND: event loop responsiveness remains > 99%
Acceptance: asyncio.get_event_loop().set_debug(True) logs no stalls
```
- **Test File:** `tests/test_ml_acceptance.py::test_fr05_threadpool_non_blocking`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-006:** FR-06 — Segmentation Output Shape
```
Given: SemanticSegmentationNode with ready model
When: on_input(payload with shape (N, 14)) called
Then: output payload['points'].shape == (N, 15)
  AND: output payload['ml_labels'].shape == (N,)
  AND: output payload['ml_labels'].dtype == int32
Acceptance: Assertion checks in test
```
- **Test File:** `tests/test_ml_acceptance.py::test_fr06_segmentation_output_shape`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-007:** FR-07 — Detection Output (Points Unchanged + Boxes)
```
Given: ObjectDetectionNode with ready model
When: on_input(payload with shape (N, 14)) called
Then: output payload['points'].shape == (N, 14) — unchanged
  AND: output payload['bounding_boxes'] is a list
Acceptance: Shape match + isinstance check
```
- **Test File:** `tests/test_ml_acceptance.py::test_fr07_detection_output`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-008:** FR-08 — Colour-by-Label in Viewer
```
Given: Angular viewer with segmentation node connected
When: v2 frame with labels received
Then: Three.js points rendered with per-point colours
  AND: colours match SemanticKITTI palette
Acceptance: Visual inspection; pixel colour sampled from canvas
```
- **Test File:** `tests/e2e/ml-viewer.e2e.spec.ts::test_fr08_color_by_label`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-009:** FR-09 — Bounding Box Rendering
```
Given: Angular viewer with detection node connected
When: v2 frame with boxes received
Then: 3D wireframe boxes rendered at correct positions
Acceptance: Visual inspection; box edge visibility verified
```
- **Test File:** `tests/e2e/ml-viewer.e2e.spec.ts::test_fr09_bounding_box_rendering`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-010:** FR-10 — Node Status Panel Shows Metrics
```
Given: ML node inspector panel open
When: model is loaded and inferencing
Then: status panel shows:
  - Model name
  - Inference latency (ms)
  - Device (cpu/cuda:0)
  - Status badge (loading/ready)
Acceptance: All fields visible and non-empty
```
- **Test File:** `tests/e2e/ml-workflow.e2e.spec.ts::test_fr10_node_status_panel`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-011:** FR-11 — Warm-Up Pass-Through
```
Given: ML node during model loading
When: data flows through node
Then: data is forwarded unmodified
  AND: no labels/boxes added
Acceptance: Output == input (byte comparison)
```
- **Test File:** `tests/test_ml_acceptance.py::test_fr11_warmup_passthrough`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

**QA-AC-012:** FR-12 — Download Progress Reporting
```
Given: Large model being downloaded
When: GET /api/v1/ml/models/{key}/status called multiple times
Then: download_progress_pct increments from 0 → 100
Acceptance: Assertion on progress values
```
- **Test File:** `tests/test_ml_acceptance.py::test_fr12_download_progress`
- **Status:** [ ] Scaffold [ ] Implement [ ] Pass

---

## 📊 Test Execution Checklist

### Before Development Starts
- [ ] All test files created with scaffold (empty test functions)
- [ ] Pytest fixtures and mocks in place
- [ ] Angular test harnesses configured
- [ ] `npm test` and `pytest` both pass (with skipped/pending tests)

### During Development (Parallel with @be-dev & @fe-dev)
- [ ] **Backend tests** checked-in as @be-dev completes each phase
  - [ ] Phase 1: Model Registry tests should PASS
  - [ ] Phase 2: Node tests should PASS
  - [ ] Phase 3: API tests should PASS
  - [ ] Phase 4: Protocol tests should PASS
- [ ] **Frontend tests** checked-in as @fe-dev completes each phase
  - [ ] Decoder service unit tests PASS
  - [ ] API service mocks verified working
  - [ ] Component tests PASS
- [ ] **Regressions caught immediately** via CI/CD hook

### Before PR Submission
- [ ] All unit tests PASS: `pytest tests/ -x`
- [ ] All frontend tests PASS: `ng test --watch=false`
- [ ] Code coverage ≥ 80% for new modules
- [ ] No regressions in existing tests
- [ ] Performance benchmarks logged
- [ ] E2E tests PASS on reference hardware

---

## 📝 Test Results Tracking

Each test section above has a `[ ] Status` field with three checkboxes:

```
[ ] Scaffold     ← Test file created; test function exists (may be empty or skip())
[ ] Implement    ← Test logic fully written; may not yet pass
[ ] Pass         ← Test executes successfully; feature is working
```

---

## 🔗 References

- **Requirements:** [requirements.md](requirements.md)
- **Technical Design:** [technical.md](technical.md)
- **API Specification:** [api-spec.md](api-spec.md)
- **Backend Tasks:** [backend-tasks.md](backend-tasks.md)
- **Frontend Tasks:** [frontend-tasks.md](frontend-tasks.md)

---

**Last Updated:** 2026-03-09  
**QA Owner:** @qa  
**Status:** PLANNING → DEVELOPMENT (awaiting feature teams)