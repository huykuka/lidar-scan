# Open3D-ML Integration — Technical Implementation Checklist

**Feature:** Open3D-ML DAG Node Integration  
**Status:** Architecture Design  
**Date:** 2026-03-08  
**Author:** @architecture

## Architecture Implementation Tasks

### Backend ML Module Structure
- [ ] Create `app/modules/ml/` directory structure
- [ ] Implement `app/modules/ml/__init__.py` with module registration
- [ ] Create `app/modules/ml/registry.py` for NodeFactory registration
- [ ] Implement `app/modules/ml/ml_node.py` base class (MLNode)
- [ ] Implement `app/modules/ml/segmentation_node.py` (SemanticSegmentationNode)
- [ ] Implement `app/modules/ml/detection_node.py` (ObjectDetectionNode)
- [ ] Implement `app/modules/ml/model_registry.py` singleton service

### ML Model Registry Implementation
- [ ] Singleton pattern for process-level model management
- [ ] Dict storage for loaded ml3d.pipelines instances keyed by (model_name, dataset_name)
- [ ] Async weight download via asyncio.to_thread(download_weights)
- [ ] Async model initialization via asyncio.to_thread(pipeline.load_ckpt)
- [ ] Status tracking (downloading | loading | ready | error)
- [ ] Threadpool-wrapped run_inference() method
- [ ] LRU eviction for max 2 concurrent loaded models

### DAG Node Integration
- [ ] MLNode base class with torch availability validation
- [ ] Reference to LoadedModel from MLModelRegistry
- [ ] Warm-up pass-through pattern implementation (FR-11)
- [ ] Status reporting: inference_latency_ms, model_name, device
- [ ] Segmentation node: XYZ+intensity extraction to {"point": (N,3), "feat": (N,1)}
- [ ] Segmentation node: append semantic_label as 15th column (int32 cast to float32)
- [ ] Detection node: XYZ extraction to {"point": (N,3)}
- [ ] Detection node: pass-through original numpy unchanged + bounding_boxes metadata

### WebSocket Protocol Extension (LIDR v2)
- [ ] Extend LIDR protocol with version=2 support
- [ ] Add flags field: bit 0 (has_labels), bit 1 (has_boxes)
- [ ] Labels section: N×4 int32 semantic labels after XYZ
- [ ] Boxes section: JSON blob with length prefix
- [ ] Backward compatibility: v1 clients unaffected
- [ ] WebSocket broadcaster detects ml_labels key for v1 vs v2 encoding

### Node Schema Definitions
- [ ] ml_semantic_segmentation NodeDefinition with ML category
- [ ] Property schemas: model_name, dataset_name, device, throttle_ms, num_points
- [ ] ml_object_detection NodeDefinition with ML category  
- [ ] Property schemas: model_name, dataset_name, device, throttle_ms, confidence_threshold
- [ ] Icon assignments: "psychology" for segmentation, "view_in_ar" for detection

### REST API Implementation
- [ ] GET /api/v1/ml/models endpoint (list available models)
- [ ] GET /api/v1/ml/models/{model_key}/status endpoint
- [ ] POST /api/v1/ml/models/{model_key}/load endpoint
- [ ] DELETE /api/v1/ml/models/{model_key} endpoint
- [ ] Pydantic models: MLModelInfo, MLModelStatus, MLLoadRequest, BoundingBox3D

### Frontend Architecture
- [ ] PointCloudRenderer service v2 frame support
- [ ] Label buffer reading after XYZ block
- [ ] SEMANTIC_COLOR_MAP (SemanticKITTI palette - 20 classes)
- [ ] In-place RGB writing to BufferGeometry color attribute
- [ ] BoundingBoxRenderer service (new) with LineSegments pool
- [ ] Box wireframe rendering (12 line segments per cube)
- [ ] CSS overlay for box labels with Vector3.project() positioning

### Angular Components
- [ ] MlLabelLegendComponent (color-to-class mapping panel)
- [ ] BoundingBoxOverlayComponent (CSS overlay for box labels)
- [ ] MlNodeStatusComponent (model loading progress + inference latency)
- [ ] Integration with existing node inspector and flow-canvas

### Environment Setup
- [ ] Create requirements-ml.txt with optional ML dependencies
- [ ] Conditional import pattern for torch availability
- [ ] MLNode.__init__() torch validation with clear error messages
- [ ] Asyncio compatibility for all ML operations
- [ ] Memory footprint documentation and guidelines

## Technical Risk Mitigations
- [ ] PyTorch version pinning in requirements-ml.txt
- [ ] Default throttle_ms=200 for real-time performance
- [ ] CPU fallback when GPU unavailable
- [ ] Local cache check before model download
- [ ] PyTorch-only backend (skip TensorFlow)
- [ ] Model memory management with LRU eviction