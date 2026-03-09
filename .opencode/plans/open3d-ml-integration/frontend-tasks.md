# Open3D-ML Integration — Frontend Tasks

**Feature:** Open3D-ML DAG Node Integration  
**Assignee:** @fe-dev  
**Status:** Ready for Development  
**Date:** 2026-03-08

## Environment Setup and Dependencies
- [x] Verify Angular 20 signals-based architecture compatibility
- [x] Ensure Three.js and Synergy UI integration readiness
- [x] Set up TypeScript interfaces for ML API responses
- [x] Configure dev environment to mock ML API endpoints
- [x] Test WebSocket binary data handling capabilities

## ML API Integration (Mock Implementation)
- [x] Create `MLApiService` with mock data from api-spec.md
- [x] Mock GET /api/v1/ml/models returning 4-item model array
- [x] Mock GET /api/v1/ml/models/{model_key}/status responses
- [x] Mock POST /api/v1/ml/models/{model_key}/load (202 Accepted)
- [x] Mock DELETE /api/v1/ml/models/{model_key} (200 OK)
- [x] Implement proper TypeScript interfaces for all API responses
- [x] Add loading states and error handling for all API calls
- [x] Service integration with Angular signals for reactive updates

## Flow Canvas ML Node Integration
- [x] Add ML category to existing node palette
- [x] Register ml_semantic_segmentation node definition
- [x] Register ml_object_detection node definition  
- [x] Set node icons: "psychology" for segmentation, "view_in_ar" for detection
- [x] Node property panels with model/dataset selection dropdowns
- [x] Device selection dropdown (CPU/CUDA) in node inspector
- [x] Throttle and confidence threshold controls
- [x] Node status indicator showing loading/ready/error states

## Node Inspector ML Extensions
- [x] Extend existing node inspector for ML-specific properties
- [x] Model selection dropdown populated from MLApiService.getModels()
- [x] Dataset selection dropdown with filtered options per model type
- [x] Real-time model status updates (loading progress)
- [x] Pre-load model button for performance optimization
- [x] Inference metrics display in node status panel
- [x] Device utilization indicators (CPU/GPU usage)
- [x] Configuration validation and user feedback

## Three.js Scene Integration
- [ ] Integrate bounding box rendering with existing scene graph
- [ ] Layer management for labels and boxes vs point clouds
- [ ] Camera controls compatibility with new rendering elements
- [ ] Picking/selection support for bounding boxes
- [ ] Performance monitoring for ML-enhanced rendering
- [ ] LOD (Level of Detail) for boxes at distance
- [ ] Frustum culling for off-screen boxes
- [ ] Z-fighting prevention between boxes and points

## User Experience Enhancements
- [ ] Smooth transitions when enabling/disabling label colors
- [ ] Loading spinners during model warm-up periods
- [ ] Toast notifications for model loading completion
- [ ] Keyboard shortcuts for toggling ML visualizations
- [ ] Context menus for ML-specific actions
- [ ] Help tooltips explaining ML node functionality
- [ ] Performance warnings for heavy inference operations
- [ ] Accessibility support for colorblind users

## Mock Data Generation
- [x] Synthetic WebSocket v2 frame generation service
- [x] Generate N=1000 random XYZ points for testing
- [x] Random semantic labels [0..18] for segmentation testing
- [x] Realistic bounding box coordinates and rotations
- [x] Frame timing simulation matching real inference latency
- [x] Multiple test scenarios: empty frames, dense labels, many boxes
- [x] Animation loops for continuous testing
- [x] Debug modes with frame inspection tools

## Performance Optimization
- [ ] WebGL buffer management for large labeled point clouds
- [ ] Efficient color array updates without GPU memory transfer
- [ ] Batch operations for multiple bounding box updates
- [ ] Memory pooling for temporary calculation arrays
- [ ] Frame rate monitoring with ML rendering enabled
- [ ] Degraded rendering modes for slower hardware
- [ ] Progressive loading for large model datasets
- [ ] Background processing for non-critical ML UI updates

## Integration Testing
- [ ] Unit tests for WebSocket v2 frame parsing
- [ ] Component tests for ML-specific UI elements
- [ ] Integration tests with mocked ML API responses
- [ ] Visual regression tests for semantic color rendering
- [ ] Performance tests for bounding box rendering at scale
- [ ] Cross-browser compatibility testing
- [ ] Mobile responsiveness for ML UI components
- [ ] End-to-end user workflow testing

## Error Handling and Edge Cases
- [ ] Graceful handling of malformed WebSocket frames
- [ ] Fallback rendering when ML models fail to load
- [ ] Error boundaries for ML component failures
- [ ] Network timeout handling for model API calls
- [ ] Invalid label data handling and user notification
- [ ] Empty detection results display
- [ ] Memory exhaustion recovery for large datasets
- [ ] Torch unavailable state handling and user messaging