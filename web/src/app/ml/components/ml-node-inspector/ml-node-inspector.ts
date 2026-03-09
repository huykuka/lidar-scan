// ML Node Inspector Component
// Extension for existing node inspector to handle ML-specific properties

import { Component, input, output, computed, signal, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { MLApiService } from '../../services/ml-api.service';
import { MLModelInfo, MLSegmentationConfig, MLDetectionConfig } from '../../../core/models/ml.model';
import { NodeData } from '../../../core/models/node-plugin.model';
import { MlNodeStatusComponent } from '../ml-node-status.component';

@Component({
  selector: 'app-ml-node-inspector',
  imports: [CommonModule, FormsModule, SynergyComponentsModule, MlNodeStatusComponent],
  templateUrl: './ml-node-inspector.html',
  styleUrl: './ml-node-inspector.css',
})
export class MlNodeInspectorComponent {
  
  private mlApi = inject(MLApiService);
  
  // Input signals
  nodeData = input.required<NodeData>();
  
  // Output signals
  configChange = output<any>();
  loadModel = output<{ modelKey: string; device: string }>();
  
  // Internal signals
  private selectedDevice = signal<string>('cpu');
  public isLoading = signal<boolean>(false);
  
  // Available models and filtered options
  availableModels = this.mlApi.availableModels;
  
  // Computed properties
  nodeType = computed(() => this.nodeData().type);
  nodeConfig = computed(() => this.nodeData()['config'] || {});
  
  isSegmentationNode = computed(() => 
    this.nodeType() === 'ml_semantic_segmentation'
  );
  
  isDetectionNode = computed(() => 
    this.nodeType() === 'ml_object_detection'
  );
  
  // Filter models by task type
  segmentationModels = computed(() => 
    this.availableModels().filter(m => m.task === 'semantic_segmentation')
  );
  
  detectionModels = computed(() => 
    this.availableModels().filter(m => m.task === 'object_detection')
  );
  
  // Current model selection
  selectedModel = computed(() => {
    const config = this.nodeConfig();
    const modelName = config.model_name;
    if (!modelName) return null;
    
    return this.availableModels().find(m => m.model_name === modelName) || null;
  });
  
  // Dataset options for selected model type
  datasetOptions = computed(() => {
    const model = this.selectedModel();
    if (!model) return [];
    
    // Get unique datasets for this model type
    const modelType = this.isSegmentationNode() ? 'semantic_segmentation' : 'object_detection';
    return this.availableModels()
      .filter(m => m.task === modelType)
      .map(m => ({ name: m.dataset_name, value: m.dataset_name }))
      .filter((item, index, self) => 
        self.findIndex(i => i.value === item.value) === index
      );
  });
  
  // Device options
  deviceOptions = [
    { label: 'CPU', value: 'cpu' },
    { label: 'CUDA:0', value: 'cuda:0' },
    { label: 'CUDA:1', value: 'cuda:1' }
  ];
  
  constructor() {
    // Load available models on init
    effect(() => {
      this.mlApi.loadAvailableModels();
    });
  }
  
  /**
   * Update node configuration
   */
  updateConfig(field: string, value: any): void {
    const currentConfig = this.nodeConfig();
    const newConfig = { ...currentConfig, [field]: value };
    
    // Validate model/dataset combination
    if (field === 'model_name' || field === 'dataset_name') {
      this.validateModelDatasetCombo(newConfig);
    }
    
    this.configChange.emit(newConfig);
  }
  
  /**
   * Validate model/dataset combination is valid
   */
  private validateModelDatasetCombo(config: any): void {
    if (!config.model_name || !config.dataset_name) return;
    
    const isValid = this.availableModels().some(m => 
      m.model_name === config.model_name && m.dataset_name === config.dataset_name
    );
    
    if (!isValid) {
      console.warn('Invalid model/dataset combination:', config.model_name, config.dataset_name);
    }
  }
  
  /**
   * Pre-load selected model
   */
  onLoadModel(): void {
    const config = this.nodeConfig();
    const modelName = config.model_name;
    const datasetName = config.dataset_name;
    
    if (!modelName || !datasetName) {
      console.warn('Model name and dataset required for loading');
      return;
    }
    
    const model = this.availableModels().find(m => 
      m.model_name === modelName && m.dataset_name === datasetName
    );
    
    if (!model) {
      console.warn('Model not found:', modelName, datasetName);
      return;
    }
    
    this.isLoading.set(true);
    const device = this.selectedDevice();
    
    this.loadModel.emit({ modelKey: model.model_key, device });
    
    // Reset loading state after delay
    setTimeout(() => this.isLoading.set(false), 2000);
  }
  
  /**
   * Get current model status
   */
  getCurrentModelStatus() {
    const model = this.selectedModel();
    if (!model) return null;
    
    return this.mlApi.modelStatuses().get(model.model_key);
  }
  
  /**
   * Check if current configuration is valid
   */
  isConfigValid(): boolean {
    const config = this.nodeConfig();
    return !!(config.model_name && config.dataset_name && config.device);
  }
  
  /**
   * Handle throttle input changes
   */
  onThrottleChange(event: any): void {
    const value = +(event.target?.value || 0);
    this.updateConfig('throttle_ms', value);
  }
  
  /**
   * Handle num points input changes
   */
  onNumPointsChange(event: any): void {
    const value = +(event.target?.value || 0);
    this.updateConfig('num_points', value);
  }
  
  /**
   * Handle confidence threshold changes
   */
  onConfidenceChange(event: any): void {
    const value = +(event.target?.value || 0);
    this.updateConfig('confidence_threshold', value);
  }
}
