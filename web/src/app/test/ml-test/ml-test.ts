// ML Test Component
// Demonstrates ML API integration, mock data generation, and UI components

import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

// Import ML services and components
import { MLApiService } from '../../ml/services/ml-api.service';
import { MlLabelLegendComponent } from '../../ml/components/ml-label-legend.component';
import { MlNodeStatusComponent } from '../../ml/components/ml-node-status.component';

@Component({
  selector: 'app-ml-test',
  imports: [
    CommonModule,
    SynergyComponentsModule,
    MlLabelLegendComponent,
    MlNodeStatusComponent
  ],
  templateUrl: './ml-test.html',
  styleUrl: './ml-test.css',
})
export class MlTestComponent {
  
  private mlApi = inject(MLApiService);
  
  // Test state
  currentModelKey = signal<string>('RandLANet__SemanticKITTI');
  mockFrame = signal<any>(null);
  
  // Available models from API
  availableModels = this.mlApi.availableModels;
  
  constructor() {
    // Load models on init
    this.mlApi.loadAvailableModels();
  }
  
  /**
   * Generate and display mock ML frame data
   */
  generateMockFrame(): void {
    console.log('Generating mock LIDR v2 frame...');
    
    // Generate binary frame
    const frameBuffer = this.mlApi.generateMockLidrV2Frame(1000, true, true);
    console.log('Generated frame buffer size:', frameBuffer.byteLength);
    
    // Simulate parsed frame data for UI display
    const mockData = {
      point_count: 1000,
      version: 2,
      timestamp: Date.now(),
      has_labels: true,
      has_boxes: true,
      boxes: [
        {
          id: 0,
          label: 'car',
          label_index: 1,
          confidence: 0.85,
          center: [5, 2, 1.5],
          size: [4.5, 2, 1.8],
          yaw: 0.3,
          color: [245, 150, 100]
        },
        {
          id: 1,
          label: 'person',
          label_index: 6,
          confidence: 0.72,
          center: [-3, -1, 1.7],
          size: [0.6, 0.6, 1.75],
          yaw: 1.2,
          color: [30, 30, 255]
        }
      ]
    };
    
    this.mockFrame.set(mockData);
    console.log('Mock frame data:', mockData);
  }
  
  /**
   * Get current model data for legend
   */
  getCurrentModel() {
    const modelKey = this.currentModelKey();
    return this.availableModels().find(m => m.model_key === modelKey) || null;
  }
  
  /**
   * Test model status API
   */
  testModelStatus(modelKey: string): void {
    this.mlApi.getModelStatus(modelKey).subscribe(status => {
      console.log('Model status:', status);
    });
  }
  
  /**
   * Test model loading
   */
  testModelLoading(modelKey: string): void {
    this.mlApi.loadModel(modelKey, 'cpu').subscribe(result => {
      console.log('Load model result:', result);
    });
  }
  
  /**
   * Test performance metrics
   */
  testPerformanceMetrics(): void {
    this.mlApi.getPerformanceMetrics().subscribe(metrics => {
      console.log('Performance metrics:', metrics);
    });
  }
}
