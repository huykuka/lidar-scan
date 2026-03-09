# Open3D-ML Integration — API Specification Checklist

**Feature:** Open3D-ML DAG Node Integration  
**Version:** v1.0  
**Date:** 2026-03-08  
**Author:** @architecture

## Backend Payload Creation Tasks

### ML Models Catalogue API
- [ ] Implement GET /api/v1/ml/models endpoint
- [ ] Return array of MLModelInfo with preconfigured model definitions
- [ ] Include model_key, model_name, dataset_name, task type
- [ ] Include num_classes, class_names, color_map arrays
- [ ] Include weight_url, weight_filename, weight_size_mb
- [ ] Include config_file path and status field
- [ ] Support RandLANet, KPFCNN, PointPillars, PointRCNN models
- [ ] SemanticKITTI and KITTI dataset configurations

### Model Status API
- [ ] Implement GET /api/v1/ml/models/{model_key}/status endpoint
- [ ] Return MLModelStatus with current loading state
- [ ] Status enum: not_loaded, downloading, loading, ready, error
- [ ] Include device, loaded_at timestamp, weight_cached boolean
- [ ] Include download_progress_pct, inference metrics
- [ ] Handle 404 for unknown model_key
- [ ] Real-time status updates during download/loading

### Model Management API
- [ ] Implement POST /api/v1/ml/models/{model_key}/load endpoint
- [ ] Accept MLLoadRequest with device specification
- [ ] Return 202 Accepted for background loading initiation
- [ ] Return 409 Conflict if already loaded
- [ ] Implement DELETE /api/v1/ml/models/{model_key} endpoint
- [ ] Return 200 OK for successful unloading
- [ ] Return 404 if model not currently loaded

### WebSocket Protocol Extension
- [ ] LIDR v2 frame format implementation
- [ ] Magic bytes "LIDR" + version=2 + timestamp + point_count
- [ ] Flags field: bit 0 (has_labels), bit 1 (has_boxes)
- [ ] XYZ block: N×12 bytes float32 positions
- [ ] Labels block: N×4 bytes int32 semantic labels (conditional)
- [ ] Boxes block: JSON length prefix + UTF-8 blob (conditional)
- [ ] BoundingBox3D JSON schema with id, label, confidence, center, size, yaw
- [ ] DetectionFrameMetadata with boxes array and inference timing

### Node Configuration Integration
- [ ] ml_semantic_segmentation config schema via existing PATCH /api/v1/nodes/{node_id}
- [ ] Include op_type, model_name, dataset_name, device, throttle_ms, num_points
- [ ] ml_object_detection config schema
- [ ] Include op_type, model_name, dataset_name, device, throttle_ms, confidence_threshold
- [ ] Validation for model_name and dataset_name combinations
- [ ] Device validation: cpu | cuda:0 | cuda:1 pattern

### Pydantic Model Definitions
- [ ] MLModelInfo BaseModel with all required fields
- [ ] Task literal: "semantic_segmentation" | "object_detection"
- [ ] Status literal for model availability states
- [ ] MLModelStatus BaseModel with runtime status fields
- [ ] Optional fields with proper defaults
- [ ] MLLoadRequest BaseModel with device field validation
- [ ] BoundingBox3D BaseModel with geometry and metadata
- [ ] DetectionFrameMetadata BaseModel for WebSocket payload

### Data Payload Specifications
- [ ] 15-column numpy array for segmentation output (semantic_label in column 14)
- [ ] ml_labels, ml_scores, ml_num_classes keys in payload dict
- [ ] Original 14-column passthrough for detection nodes
- [ ] bounding_boxes metadata list in payload dict
- [ ] Frame timestamp and inference timing metadata
- [ ] Color mapping for semantic classes and detection boxes

## Frontend Mock Data Contract
- [ ] Mock GET /api/v1/ml/models with 4-item model array
- [ ] Mock model status responses for each model_key
- [ ] Generate synthetic WebSocket v2 frames with N=1000 points
- [ ] Random XYZ coordinates and semantic labels [0..18]
- [ ] Pack data according to LIDR v2 binary layout
- [ ] Synthetic bounding boxes with realistic coordinates
- [ ] Inference timing and metadata simulation