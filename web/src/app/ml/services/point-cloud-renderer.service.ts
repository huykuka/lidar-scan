// Enhanced Point Cloud Renderer Service
// Extends Three.js rendering to support semantic labels and color-by-label

import { Injectable } from '@angular/core';
import * as THREE from 'three';
import { SEMANTIC_KITTI_COLOR_MAP } from '../../core/models/ml.model';

export interface PointCloudRenderingOptions {
  enableSemanticColors: boolean;
  pointSize: number;
  colorMode: 'original' | 'semantic' | 'mixed';
  alphaBlending: number; // 0-1 for mixing original and semantic colors
}

@Injectable({
  providedIn: 'root'
})
export class PointCloudRendererService {
  
  private readonly MAX_POINTS = 100000;
  private renderingOptions: PointCloudRenderingOptions = {
    enableSemanticColors: false,
    pointSize: 0.1,
    colorMode: 'original',
    alphaBlending: 0.8
  };
  
  /**
   * Update point cloud with semantic label coloring support
   * @param geometry Three.js BufferGeometry to update
   * @param material Three.js PointsMaterial to configure
   * @param positions XYZ positions Float32Array
   * @param count Number of valid points
   * @param labels Optional semantic labels Int32Array
   * @param originalColors Optional original RGB colors Float32Array
   */
  updatePointCloudWithLabels(
    geometry: THREE.BufferGeometry,
    material: THREE.PointsMaterial,
    positions: Float32Array,
    count: number,
    labels?: Int32Array,
    originalColors?: Float32Array
  ): void {
    
    const actualCount = Math.min(count, this.MAX_POINTS);
    
    // Update positions
    const positionAttr = geometry.getAttribute('position') as THREE.BufferAttribute;
    if (positionAttr) {
      const positionsArray = positionAttr.array as Float32Array;
      const copyLength = Math.min(actualCount * 3, positions.length, positionsArray.length);
      positionsArray.set(positions.subarray(0, copyLength));
      positionAttr.needsUpdate = true;
    }
    
    // Handle color attributes based on options
    if (this.renderingOptions.enableSemanticColors && labels) {
      this.updateSemanticColors(geometry, material, labels, actualCount, originalColors);
    } else if (originalColors) {
      this.updateOriginalColors(geometry, material, originalColors, actualCount);
    } else {
      // Use material color
      material.vertexColors = false;
    }
    
    // Update draw range
    geometry.setDrawRange(0, actualCount);
    
    // Update point size
    material.size = this.renderingOptions.pointSize;
  }
  
  /**
   * Apply semantic label coloring to point cloud
   */
  private updateSemanticColors(
    geometry: THREE.BufferGeometry,
    material: THREE.PointsMaterial,
    labels: Int32Array,
    count: number,
    originalColors?: Float32Array
  ): void {
    
    // Ensure color attribute exists
    let colorAttr = geometry.getAttribute('color') as THREE.BufferAttribute;
    if (!colorAttr) {
      const colors = new Float32Array(this.MAX_POINTS * 3);
      colorAttr = new THREE.BufferAttribute(colors, 3);
      geometry.setAttribute('color', colorAttr);
    }
    
    const colors = colorAttr.array as Float32Array;
    const colorMode = this.renderingOptions.colorMode;
    const alpha = this.renderingOptions.alphaBlending;
    
    for (let i = 0; i < count; i++) {
      const labelIndex = labels[i] || 0; // fallback to unlabelled
      const semanticColor = this.getSemanticColor(labelIndex);
      
      let finalColor: number[];
      
      if (colorMode === 'semantic' || !originalColors) {
        // Pure semantic coloring
        finalColor = semanticColor;
      } else if (colorMode === 'mixed' && originalColors) {
        // Blend semantic and original colors
        const origR = originalColors[i * 3] || 0;
        const origG = originalColors[i * 3 + 1] || 0;
        const origB = originalColors[i * 3 + 2] || 0;
        
        finalColor = [
          (semanticColor[0] * alpha + origR * (1 - alpha)) / 255,
          (semanticColor[1] * alpha + origG * (1 - alpha)) / 255,
          (semanticColor[2] * alpha + origB * (1 - alpha)) / 255
        ];
      } else {
        // Original coloring
        finalColor = [
          originalColors[i * 3] / 255,
          originalColors[i * 3 + 1] / 255,
          originalColors[i * 3 + 2] / 255
        ];
      }
      
      colors[i * 3] = finalColor[0];
      colors[i * 3 + 1] = finalColor[1];  
      colors[i * 3 + 2] = finalColor[2];
    }
    
    colorAttr.needsUpdate = true;
    material.vertexColors = true;
  }
  
  /**
   * Apply original colors to point cloud (no semantic coloring)
   */
  private updateOriginalColors(
    geometry: THREE.BufferGeometry,
    material: THREE.PointsMaterial,
    originalColors: Float32Array,
    count: number
  ): void {
    
    let colorAttr = geometry.getAttribute('color') as THREE.BufferAttribute;
    if (!colorAttr) {
      const colors = new Float32Array(this.MAX_POINTS * 3);
      colorAttr = new THREE.BufferAttribute(colors, 3);
      geometry.setAttribute('color', colorAttr);
    }
    
    const colors = colorAttr.array as Float32Array;
    
    for (let i = 0; i < count; i++) {
      colors[i * 3] = originalColors[i * 3] / 255;
      colors[i * 3 + 1] = originalColors[i * 3 + 1] / 255;
      colors[i * 3 + 2] = originalColors[i * 3 + 2] / 255;
    }
    
    colorAttr.needsUpdate = true;
    material.vertexColors = true;
  }
  
  /**
   * Get RGB color for semantic class index
   * @param labelIndex Semantic class index (0-19 for SemanticKITTI)
   * @returns RGB array [0-255, 0-255, 0-255]
   */
  private getSemanticColor(labelIndex: number): number[] {
    if (labelIndex >= 0 && labelIndex < SEMANTIC_KITTI_COLOR_MAP.length) {
      return SEMANTIC_KITTI_COLOR_MAP[labelIndex];
    }
    return [128, 128, 128]; // Gray fallback for unknown labels
  }
  
  /**
   * Update rendering options
   */
  setRenderingOptions(options: Partial<PointCloudRenderingOptions>): void {
    this.renderingOptions = { ...this.renderingOptions, ...options };
  }
  
  /**
   * Get current rendering options
   */
  getRenderingOptions(): PointCloudRenderingOptions {
    return { ...this.renderingOptions };
  }
  
  /**
   * Toggle semantic coloring on/off
   */
  toggleSemanticColors(): void {
    this.renderingOptions.enableSemanticColors = !this.renderingOptions.enableSemanticColors;
  }
  
  /**
   * Set color mode
   */
  setColorMode(mode: 'original' | 'semantic' | 'mixed'): void {
    this.renderingOptions.colorMode = mode;
  }
  
  /**
   * Apply original colors to point cloud (public method)
   */
  applyOriginalColors(
    geometry: THREE.BufferGeometry,
    material: THREE.PointsMaterial,
    originalColors?: Float32Array,
    count?: number
  ): void {
    if (!originalColors) {
      // Fallback to material color
      material.vertexColors = false;
      return;
    }
    
    const actualCount = count || (originalColors.length / 3);
    this.updateOriginalColors(geometry, material, originalColors, actualCount);
  }
}