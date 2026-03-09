// ML Dashboard Component
// Main dashboard for ML operations, model management, and real-time visualization

import { Component, ViewChild, ElementRef, computed, signal, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import * as THREE from 'three';

// Import ML services and components
import { MLApiService } from '../../services/ml-api.service';
import { EnhancedWebsocketService } from '../../services/enhanced-websocket.service';
import { PointCloudRendererService } from '../../services/point-cloud-renderer.service';
import { BoundingBoxRendererService } from '../../services/bounding-box-renderer.service';
import { MlLabelLegendComponent } from '../ml-label-legend.component';
import { BoundingBoxOverlayComponent } from '../bounding-box-overlay.component';
import { MlNodeStatusComponent } from '../ml-node-status.component';

// Import existing components
import { PointCloudComponent } from '../../../features/workspaces/components/point-cloud/point-cloud.component';

@Component({
  selector: 'app-ml-dashboard',
  imports: [
    CommonModule,
    SynergyComponentsModule,
    PointCloudComponent,
    MlLabelLegendComponent,
    BoundingBoxOverlayComponent,
    MlNodeStatusComponent
  ],
  templateUrl: './ml-dashboard.html',
  styleUrl: './ml-dashboard.css',
})
export class MlDashboardComponent {
  
  @ViewChild(PointCloudComponent) pointCloudComponent!: PointCloudComponent;
  @ViewChild(BoundingBoxOverlayComponent) boxOverlayComponent!: BoundingBoxOverlayComponent;
  
  // Inject services
  private mlApi = inject(MLApiService);
  private wsService = inject(EnhancedWebsocketService);
  private pointCloudRenderer = inject(PointCloudRendererService);
  private boxRenderer = inject(BoundingBoxRendererService);
  
  // UI State signals
  private _isConnected = signal<boolean>(false);
  private _selectedModel = signal<string | null>(null);
  private _showSemanticColors = signal<boolean>(false);
  private _showBoundingBoxes = signal<boolean>(true);
  private _canvasSize = signal<{width: number; height: number}>({ width: 800, height: 600 });
  
  // Three.js references
  private scene?: THREE.Scene;
  public camera?: THREE.Camera;
  
  // Public computed properties
  isConnected = computed(() => this._isConnected());
  selectedModel = computed(() => this._selectedModel());
  showSemanticColors = computed(() => this._showSemanticColors());
  showBoundingBoxes = computed(() => this._showBoundingBoxes());
  canvasSize = computed(() => this._canvasSize());
  
  // ML data from WebSocket
  currentFrame = this.wsService.currentFrame;
  hasSemanticLabels = this.wsService.hasSemanticLabels;
  hasBoundingBoxes = this.wsService.hasBoundingBoxes;
  frameCount = this.wsService.frameCount;
  
  // Available models
  availableModels = this.mlApi.availableModels;
  
  // Current model for legend
  currentModelData = computed(() => {
    const modelKey = this._selectedModel();
    if (!modelKey) return null;
    
    return this.availableModels().find(m => m.model_key === modelKey) || null;
  });
  
  // Performance metrics
  performanceMetrics = signal<any>(null);
  
  constructor() {
    // Load available models
    this.mlApi.loadAvailableModels();
    
    // Setup WebSocket frame processing
    this.setupFrameProcessing();
    
    // Setup performance monitoring
    this.setupPerformanceMonitoring();
  }
  
  /**
   * Setup frame processing from WebSocket
   */
  private setupFrameProcessing(): void {
    this.wsService.frames$.subscribe(frame => {
      this.processFrame(frame);
    });
  }
  
  /**
   * Process incoming frame with ML data
   */
  private processFrame(frame: any): void {
    if (!this.pointCloudComponent || !this.scene) return;
    
    try {
      // Get point cloud geometry and material
      const pointCloud = this.getPointCloudObjects();
      if (!pointCloud) return;
      
      // Update point cloud with semantic labels if available
      this.pointCloudRenderer.updatePointCloudWithLabels(
        pointCloud.geometry,
        pointCloud.material,
        frame.positions,
        frame.point_count,
        frame.labels
      );
      
      // Update bounding boxes if available
      if (frame.boxes && this._showBoundingBoxes()) {
        this.boxRenderer.updateBoundingBoxes(frame.boxes);
      }
      
      // Update point cloud component
      this.pointCloudComponent.updatePoints(frame.positions, frame.point_count);
      
    } catch (error) {
      console.error('Error processing ML frame:', error);
    }
  }
  
  /**
   * Get references to Three.js point cloud objects
   */
  private getPointCloudObjects(): { geometry: THREE.BufferGeometry; material: THREE.PointsMaterial } | null {
    // This would need to be implemented based on the PointCloudComponent structure
    // For now, return null and implement later when we integrate
    return null;
  }
  
  /**
   * Setup performance monitoring
   */
  private setupPerformanceMonitoring(): void {
    // Update performance metrics every 2 seconds
    setInterval(() => {
      this.mlApi.getPerformanceMetrics().subscribe(metrics => {
        this.performanceMetrics.set(metrics);
      });
    }, 2000);
  }
  
  /**
   * Connect to WebSocket stream
   */
  connectToStream(url: string = 'ws://localhost:8000/ws'): void {
    this._isConnected.set(true);
    this.wsService.connect(url);
  }
  
  /**
   * Disconnect from WebSocket stream
   */
  disconnectFromStream(): void {
    this._isConnected.set(false);
    this.wsService.disconnect();
  }
  
  /**
   * Select ML model for visualization
   */
  selectModel(modelKey: string): void {
    this._selectedModel.set(modelKey);
  }
  
  /**
   * Toggle semantic color visualization
   */
  toggleSemanticColors(): void {
    const newState = !this._showSemanticColors();
    this._showSemanticColors.set(newState);
    this.pointCloudRenderer.setRenderingOptions({ enableSemanticColors: newState });
  }
  
  /**
   * Toggle bounding box visualization
   */
  toggleBoundingBoxes(): void {
    const newState = !this._showBoundingBoxes();
    this._showBoundingBoxes.set(newState);
    this.boxRenderer.setVisible(newState);
  }
  
  /**
   * Generate mock data for testing
   */
  generateMockData(): void {
    const mockFrame = this.mlApi.generateMockLidrV2Frame(1000, true, true);
    
    // Simulate WebSocket message
    this.wsService['processIncomingFrame'](mockFrame);
  }
  
  /**
   * Update canvas size (called by resize observer)
   */
  updateCanvasSize(width: number, height: number): void {
    this._canvasSize.set({ width, height });
  }
  
  /**
   * Setup Three.js scene references
   */
  onPointCloudInit(scene: THREE.Scene, camera: THREE.Camera): void {
    this.scene = scene;
    this.camera = camera;
    
    // Initialize bounding box renderer
    this.boxRenderer.initialize(scene);
  }
}
