# Open3D-ML Integration — Backend Tasks

**Feature:** Open3D-ML DAG Node Integration  
**Assignee:** @be-dev  
**Status:** Ready for Development  
**Date:** 2026-03-08

## Environment Setup
- [x] Create `requirements-ml.txt` with PyTorch and ML dependencies
- [x] Add torch>=2.0.0, scikit-learn>=0.21, pandas>=1.0, pyyaml>=5.4.1
- [x] Add addict, tqdm, pyquaternion dependencies
- [ ] Test installation in isolated venv and verify compatibility with existing open3d
- [ ] Document ML dependencies as optional in README

## ML Module Structure
- [x] Create `app/modules/ml/__init__.py` with module imports
- [x] Create `app/modules/ml/registry.py` for NodeFactory.register() calls
- [x] Implement `app/modules/ml/ml_node.py` - MLNode(ModuleNode) base class
- [ ] Implement `app/modules/ml/segmentation_node.py` - SemanticSegmentationNode
- [ ] Implement `app/modules/ml/detection_node.py` - ObjectDetectionNode  
- [x] Implement `app/modules/ml/model_registry.py` - MLModelRegistry singleton
- [ ] Register ml_semantic_segmentation and ml_object_detection with NodeFactory

## MLModelRegistry Implementation
- [x] Singleton pattern with _instance class variable
- [x] Dict storage: {model_key: LoadedModel} for pipeline instances
- [x] get_or_load() method with async model loading
- [x] download_weights() wrapped in asyncio.to_thread()
- [x] pipeline.load_ckpt() initialization in threadpool
- [x] Status tracking: downloading, loading, ready, error states
- [x] run_inference() wrapper for threadpool execution
- [ ] LRU eviction policy for max 2 concurrent models
- [ ] Proper cleanup and memory management

## MLNode Base Class
- [x] Inherit from ModuleNode with ML-specific initialization
- [x] Torch availability check in __init__() with ImportError handling
- [x] Reference to LoadedModel from MLModelRegistry.get_or_load()
- [x] Warm-up pass-through pattern when model status != "ready"
- [x] get_status() override with inference_latency_ms, model_name, device
- [x] Error handling integration with existing OperationNode pattern
- [x] Throttling mechanism integration with existing throttle_ms config

## SemanticSegmentationNode Implementation
- [ ] process_data() method with XYZ + intensity extraction
- [ ] Convert 14-column numpy to {"point": (N,3), "feat": (N,1)} format
- [ ] Call registry.run_inference() via asyncio.to_thread()
- [ ] Process {"predict_labels": (N,), "predict_scores": (N,C)} result
- [ ] Append semantic_label as column 14 (int32 cast to float32)
- [ ] Add ml_labels, ml_scores, ml_num_classes to payload dict
- [ ] Forward augmented (N,15) numpy array to manager.forward_data()
- [ ] Handle model loading states with appropriate fallbacks

## ObjectDetectionNode Implementation  
- [ ] process_data() method with XYZ-only extraction
- [ ] Convert 14-column numpy to {"point": (N,3)} format for inference
- [ ] Call registry.run_inference() via asyncio.to_thread()
- [ ] Process {"predict_boxes": [...]} result into BoundingBox3D objects
- [ ] Pass-through original (N,14) numpy array UNCHANGED
- [ ] Add bounding_boxes list to payload metadata
- [ ] Forward original point cloud + detection metadata
- [ ] Confidence threshold filtering based on node config

## REST API Endpoints
- [ ] Create `app/api/v1/ml/` router module
- [ ] Implement GET /api/v1/ml/models with hardcoded model catalog
- [ ] Implement GET /api/v1/ml/models/{model_key}/status
- [ ] Implement POST /api/v1/ml/models/{model_key}/load
- [ ] Implement DELETE /api/v1/ml/models/{model_key}
- [ ] Return proper HTTP status codes and error handling
- [ ] Include router in main FastAPI app
- [ ] Add request/response validation with Pydantic models

## WebSocket Protocol Extension
- [ ] Extend LIDR broadcaster with v2 frame format support
- [ ] Check for ml_labels key in payload to determine v1 vs v2
- [ ] Implement v2 frame packing: version=2, flags, XYZ, labels, boxes
- [ ] Flags bit manipulation: bit 0 for has_labels, bit 1 for has_boxes
- [ ] Int32 labels array serialization after XYZ block
- [ ] JSON blob serialization for bounding boxes with length prefix
- [ ] Maintain backward compatibility with v1 clients
- [ ] Test frame size limits and performance impact

## Node Schema Registration
- [ ] Define ml_semantic_segmentation NodeDefinition
- [ ] Property schemas: model_name (select), dataset_name (select), device, throttle_ms, num_points
- [ ] Define ml_object_detection NodeDefinition  
- [ ] Property schemas: model_name (select), dataset_name (select), device, throttle_ms, confidence_threshold
- [ ] Register both schemas with NodeRegistry on module import
- [ ] Set category="ml" and appropriate icons
- [ ] Validate property combinations and constraints

## Model Storage and Caching
- [ ] Implement configurable ML_MODELS_DIR (default: ./models/)
- [ ] Local cache checking before attempting downloads
- [ ] urllib or wget-based weight file downloading
- [ ] Progress tracking during download with callback updates
- [ ] File integrity verification after download
- [ ] Cleanup of partial downloads on failure
- [ ] Disk space management and cleanup policies

## Error Handling and Graceful Degradation
- [ ] Conditional imports with try/except for torch dependencies
- [ ] Clear error messages when torch not available
- [ ] Model download failure handling with retries
- [ ] Model loading failure handling and status reporting  
- [ ] Inference failure handling with fallback to pass-through
- [ ] Memory exhaustion handling during model loading
- [ ] GPU unavailability graceful fallback to CPU

## Testing and Integration
- [ ] Unit tests for MLModelRegistry singleton behavior
- [ ] Unit tests for node data processing pipelines
- [ ] Integration tests with mock ml3d pipelines
- [ ] WebSocket v2 protocol serialization/deserialization tests
- [ ] API endpoint tests with FastAPI TestClient
- [ ] Error condition testing (missing torch, failed downloads, etc.)
- [ ] Performance testing: inference latency, memory usage
- [ ] Compatibility testing with existing pipeline nodes