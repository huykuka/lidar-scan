import { TestBed } from '@angular/core/testing';
import { Component, ViewChild } from '@angular/core';
import { PointCloudComponent } from '../features/workspaces/components/point-cloud/point-cloud.component';
import { MLApiService } from '../ml/services/ml-api.service';
import { PointCloudRendererService } from '../ml/services/point-cloud-renderer.service';
import { BoundingBoxRendererService } from '../ml/services/bounding-box-renderer.service';

@Component({
  template: `
    <div style="width: 800px; height: 600px;">
      <app-point-cloud 
        #pointCloud
        [enableMLRendering]="true"
        [semanticColorMode]="'semantic'"
        [pointSize]="0.1">
      </app-point-cloud>
    </div>
  `,
  imports: [PointCloudComponent],
})
class TestHostComponent {
  @ViewChild('pointCloud') pointCloudComponent!: PointCloudComponent;
}

describe('ML Integration Tests', () => {
  let component: TestHostComponent;
  let fixture: any;
  let mlApiService: MLApiService;
  let pointCloudRenderer: PointCloudRendererService;
  let boundingBoxRenderer: BoundingBoxRendererService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TestHostComponent],
      providers: [
        MLApiService,
        PointCloudRendererService,
        BoundingBoxRendererService,
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(TestHostComponent);
    component = fixture.componentInstance;
    mlApiService = TestBed.inject(MLApiService);
    pointCloudRenderer = TestBed.inject(PointCloudRendererService);
    boundingBoxRenderer = TestBed.inject(BoundingBoxRendererService);
  });

  it('should create ML-enhanced point cloud component', () => {
    expect(component).toBeTruthy();
    fixture.detectChanges();
    expect(component.pointCloudComponent).toBeTruthy();
  });

  it('should load mock ML models', () => {
    mlApiService.loadAvailableModels();
    const models = mlApiService.availableModels();
    
    expect(models.length).toBe(4);
    expect(models.find(m => m.model_key === 'RandLANet__SemanticKITTI')).toBeTruthy();
    expect(models.find(m => m.task === 'semantic_segmentation')).toBeTruthy();
    expect(models.find(m => m.task === 'object_detection')).toBeTruthy();
  });

  it('should generate mock LIDR v2 frames with ML data', () => {
    const frameBuffer = mlApiService.generateMockLidrV2Frame(1000, true, true);
    
    expect(frameBuffer).toBeInstanceOf(ArrayBuffer);
    expect(frameBuffer.byteLength).toBeGreaterThan(12000); // Header + points + labels + boxes
  });

  it('should handle semantic label color modes', () => {
    fixture.detectChanges();
    const pointCloud = component.pointCloudComponent;
    
    // Add a point cloud with ML data
    pointCloud.addOrUpdatePointCloud('test', '#00ff00');
    
    const positions = new Float32Array([0, 0, 0, 1, 1, 1, 2, 2, 2]);
    const labels = new Int32Array([0, 1, 2]); // road, sidewalk, building
    
    pointCloud.updatePointsWithMLData('test', positions, 3, labels);
    
    expect(pointCloud.getTotalPointCount()).toBe(3);
    
    // Test color mode changes
    pointCloud.setSemanticColorMode('semantic');
    pointCloud.setSemanticColorMode('mixed');
    pointCloud.setSemanticColorMode('original');
    
    // No errors should be thrown
    expect(true).toBe(true);
  });

  it('should render bounding boxes', () => {
    fixture.detectChanges();
    const pointCloud = component.pointCloudComponent;
    
    const mockBoxes = [
      {
        id: 0,
        label: 'car',
        label_index: 1,
        confidence: 0.85,
        center: [5, 2, 1.5],
        size: [4.5, 2, 1.8],
        yaw: 0.3,
        color: [245, 150, 100]
      }
    ];
    
    pointCloud.updateBoundingBoxes(mockBoxes);
    
    expect(boundingBoxRenderer.getActiveBoxCount()).toBe(1);
  });

  it('should handle keyboard shortcuts', () => {
    fixture.detectChanges();
    const pointCloud = component.pointCloudComponent;
    
    // Focus the component first
    pointCloud.focusComponent();
    
    // Mock keyboard events
    const keyEvent = new KeyboardEvent('keydown', { key: 'l' });
    
    // Test that keyboard handler exists
    expect(pointCloud.onKeyDown).toBeTruthy();
    
    // Call keyboard handler directly (since DOM events are complex to test)
    pointCloud.onKeyDown(keyEvent);
    
    // Should not throw errors
    expect(true).toBe(true);
  });

  it('should toggle ML rendering modes', () => {
    fixture.detectChanges();
    const pointCloud = component.pointCloudComponent;
    
    // Test ML rendering toggle
    pointCloud.setMLRenderingEnabled(true);
    pointCloud.setMLRenderingEnabled(false);
    
    // Should not throw errors
    expect(true).toBe(true);
  });

  it('should handle performance with large point clouds', () => {
    fixture.detectChanges();
    const pointCloud = component.pointCloudComponent;
    
    pointCloud.addOrUpdatePointCloud('large-test', '#ff0000');
    
    // Generate 10k points
    const positions = new Float32Array(30000); // 10k * 3
    const labels = new Int32Array(10000);
    
    for (let i = 0; i < 10000; i++) {
      positions[i * 3] = Math.random() * 20 - 10;
      positions[i * 3 + 1] = Math.random() * 20 - 10;
      positions[i * 3 + 2] = Math.random() * 20 - 10;
      labels[i] = Math.floor(Math.random() * 19);
    }
    
    const startTime = performance.now();
    pointCloud.updatePointsWithMLData('large-test', positions, 10000, labels);
    const endTime = performance.now();
    
    expect(endTime - startTime).toBeLessThan(100); // Should be fast (<100ms)
    expect(pointCloud.getTotalPointCount()).toBe(10000);
  });
});