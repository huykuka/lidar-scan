# Open3D-ML Integration — Requirements Checklist

**Feature:** Open3D-ML DAG Node Integration  
**Status:** Planning  
**Date:** 2026-03-08  
**Author:** @architecture

## BA/PM Acceptance Criteria

### Core Feature Requirements
- [ ] ML node category appears in Angular flow-canvas node palette
- [ ] `ml_semantic_segmentation` node can be dropped and connected to pipeline
- [ ] `ml_object_detection` node can be dropped and connected to pipeline
- [ ] Node inspector allows model selection from dropdown (populated by API)
- [ ] System downloads model weights automatically on first use
- [ ] Model weights are cached locally and persist across server restarts
- [ ] ML nodes load selected model once and reuse for all frames
- [ ] Inference runs on threadpool without blocking FastAPI event loop

### Semantic Segmentation Requirements
- [ ] Segmentation node outputs augmented point cloud with semantic_label attribute
- [ ] Frontend color-codes points by semantic_label when node output is selected
- [ ] Per-point labels are carried via WebSocket LIDR v2 protocol extension
- [ ] 15th column (semantic_label) added to numpy payload schema

### Object Detection Requirements
- [ ] Detection node outputs original point cloud unchanged plus bounding_boxes metadata
- [ ] Frontend renders 3D wireframe bounding boxes in Three.js scene
- [ ] Bounding boxes data carried via WebSocket LIDR v2 JSON blob section
- [ ] Detection results include class labels and confidence scores

### Model Management Requirements
- [ ] REST endpoints for listing available models (`GET /api/v1/ml/models`)
- [ ] REST endpoints for model status checking (`GET /api/v1/ml/models/{model_key}/status`)
- [ ] REST endpoints for pre-loading models (`POST /api/v1/ml/models/{model_key}/load`)
- [ ] REST endpoints for unloading models (`DELETE /api/v1/ml/models/{model_key}`)
- [ ] Model registry service manages singleton model instances

### Performance Requirements
- [ ] Inference latency ≤ 200ms for 65k-point frame on CPU (RandLA-Net with 4096 points)
- [ ] Model loading is asynchronous and non-blocking
- [ ] ML nodes honor existing throttle_ms mechanism
- [ ] System gracefully handles missing torch installation
- [ ] Node status panel shows inference latency, model name, and device

### Compatibility Requirements
- [ ] System starts without errors when torch is NOT installed
- [ ] All existing pipeline tests pass unchanged
- [ ] LIDR v1 clients remain unaffected by v2 protocol extension
- [ ] 14-column numpy payload schema unchanged for non-ML nodes

## Final Acceptance Tests
- [ ] RandLA-Net/SemanticKITTI produces non-zero labels for live SICK sensor feed
- [ ] PointPillars/KITTI emits bounding_boxes metadata for static .pcd test file
- [ ] Three.js viewer color-codes points by semantic class
- [ ] Wireframe bounding boxes render correctly in 3D scene
- [ ] Model weights cached and not re-downloaded on server restart