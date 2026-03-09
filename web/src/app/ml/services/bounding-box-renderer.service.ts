// Bounding Box Renderer Service
// Efficient 3D bounding box rendering for object detection results

import { Injectable } from '@angular/core';
import * as THREE from 'three';
import { BoundingBox3D } from '../../core/models/ml.model';

interface BoxRenderData {
  mesh: THREE.LineSegments;
  geometry: THREE.BufferGeometry;
  material: THREE.LineBasicMaterial;
  isActive: boolean;
  distance?: number;
  lodLevel?: number;
}

@Injectable({
  providedIn: 'root'
})
export class BoundingBoxRendererService {
  
  private readonly MAX_BOXES = 256;
  private boxPool: BoxRenderData[] = [];
  private scene?: THREE.Scene;
  private camera?: THREE.Camera;
  private activeBoxCount = 0;
  
  // LOD configuration
  private readonly LOD_DISTANCES = {
    HIGH_DETAIL: 20,    // Full wireframe within 20 units
    MID_DETAIL: 50,     // Simplified wireframe 20-50 units
    LOW_DETAIL: 100,    // Point representation 50-100 units
    CULL_DISTANCE: 150  // Hide beyond 150 units
  };
  
  // Z-fighting prevention
  private readonly Z_OFFSET = 0.001; // Small offset to prevent z-fighting with point clouds
  
  // Performance monitoring
  private lastFrameTime = 0;
  private renderingTooSlow = false;
  
  /**
   * Initialize bounding box renderer with Three.js scene and camera
   * @param scene Three.js scene to add boxes to
   * @param camera Camera for LOD calculations and frustum culling
   */
  initialize(scene: THREE.Scene, camera?: THREE.Camera): void {
    this.scene = scene;
    this.camera = camera;
    this.createBoxPool();
  }
  
  /**
   * Update bounding boxes for current frame with LOD and frustum culling
   * @param boxes Array of bounding box data
   */
  updateBoundingBoxes(boxes: BoundingBox3D[]): void {
    if (!this.scene) {
      console.warn('BoundingBoxRenderer not initialized with scene');
      return;
    }
    
    const startTime = performance.now();
    
    // Hide all boxes first
    this.hideAllBoxes();
    
    // Update active boxes with LOD and culling
    const numBoxes = Math.min(boxes.length, this.MAX_BOXES);
    this.activeBoxCount = 0;
    
    for (let i = 0; i < numBoxes; i++) {
      const box = boxes[i];
      
      // Calculate distance from camera
      const distance = this.calculateDistanceFromCamera(box.center);
      
      // Apply frustum culling
      if (this.camera && !this.isInCameraFrustum(box)) {
        continue;
      }
      
      // Apply distance culling
      if (distance > this.LOD_DISTANCES.CULL_DISTANCE) {
        continue;
      }
      
      // Determine LOD level
      const lodLevel = this.calculateLODLevel(distance);
      
      // Update box with LOD
      this.updateBoxWithLOD(this.activeBoxCount, box, distance, lodLevel);
      this.activeBoxCount++;
    }
    
    // Performance monitoring
    const frameTime = performance.now() - startTime;
    this.lastFrameTime = frameTime;
    this.renderingTooSlow = frameTime > 16.67; // 60 FPS threshold
  }
  
  /**
   * Update a single bounding box with LOD considerations
   */
  private updateBoxWithLOD(index: number, box: BoundingBox3D, distance: number, lodLevel: number): void {
    const boxData = this.boxPool[index];
    if (!boxData) return;
    
    boxData.distance = distance;
    boxData.lodLevel = lodLevel;
    
    // Update geometry based on LOD level
    this.updateBoxGeometryWithLOD(boxData.geometry, box, lodLevel);
    
    // Update material properties based on distance
    this.updateMaterialForLOD(boxData.material, distance, lodLevel);
    
    // Update material color
    const color = new THREE.Color(
      box.color[0] / 255,
      box.color[1] / 255, 
      box.color[2] / 255
    );
    boxData.material.color = color;
    
    // Set visibility and active state
    boxData.mesh.visible = true;
    boxData.isActive = true;
    
    // Update position with z-fighting prevention
    boxData.mesh.position.set(
      box.center[0],
      box.center[1], 
      box.center[2] + this.Z_OFFSET
    );
    
    // Update rotation (yaw only for simplicity)
    boxData.mesh.rotation.set(0, 0, box.yaw);
  }
  
  /**
   * Calculate distance from camera to box center
   */
  private calculateDistanceFromCamera(center: number[]): number {
    if (!this.camera) return 0;
    
    const boxPosition = new THREE.Vector3(center[0], center[1], center[2]);
    return this.camera.position.distanceTo(boxPosition);
  }
  
  /**
   * Check if bounding box is within camera frustum
   */
  private isInCameraFrustum(box: BoundingBox3D): boolean {
    if (!this.camera) return true;
    
    // Simple bounding sphere frustum check
    const boxCenter = new THREE.Vector3(box.center[0], box.center[1], box.center[2]);
    const boxRadius = Math.max(...box.size) / 2;
    
    // Create frustum from camera
    const frustum = new THREE.Frustum();
    const matrix = new THREE.Matrix4().multiplyMatrices(
      (this.camera as THREE.PerspectiveCamera).projectionMatrix,
      (this.camera as THREE.PerspectiveCamera).matrixWorldInverse
    );
    frustum.setFromProjectionMatrix(matrix);
    
    // Test bounding sphere against frustum
    const sphere = new THREE.Sphere(boxCenter, boxRadius);
    return frustum.intersectsSphere(sphere);
  }
  
  /**
   * Calculate LOD level based on distance
   */
  private calculateLODLevel(distance: number): number {
    if (distance <= this.LOD_DISTANCES.HIGH_DETAIL) return 0; // Full detail
    if (distance <= this.LOD_DISTANCES.MID_DETAIL) return 1;  // Mid detail
    if (distance <= this.LOD_DISTANCES.LOW_DETAIL) return 2;  // Low detail
    return 3; // Minimal detail
  }
  private updateBoxGeometry(geometry: THREE.BufferGeometry, box: BoundingBox3D): void {
    const [dx, dy, dz] = box.size;
    const halfX = dx / 2;
    const halfY = dy / 2; 
    const halfZ = dz / 2;
    
    // 8 vertices of the box (relative to center)
    const vertices = [
      [-halfX, -halfY, -halfZ], // 0: bottom-front-left
      [+halfX, -halfY, -halfZ], // 1: bottom-front-right
      [+halfX, +halfY, -halfZ], // 2: bottom-back-right
      [-halfX, +halfY, -halfZ], // 3: bottom-back-left
      [-halfX, -halfY, +halfZ], // 4: top-front-left
      [+halfX, -halfY, +halfZ], // 5: top-front-right
      [+halfX, +halfY, +halfZ], // 6: top-back-right
      [-halfX, +halfY, +halfZ], // 7: top-back-left
    ];
    
    // 12 lines (24 points) forming the wireframe
    const lines = [
      // Bottom face
      [0, 1], [1, 2], [2, 3], [3, 0],
      // Top face  
      [4, 5], [5, 6], [6, 7], [7, 4],
      // Vertical edges
      [0, 4], [1, 5], [2, 6], [3, 7]
    ];
    
    const positions = new Float32Array(lines.length * 6); // 24 points * 3 coordinates
    
    for (let i = 0; i < lines.length; i++) {
      const [startIdx, endIdx] = lines[i];
      const start = vertices[startIdx];
      const end = vertices[endIdx];
      
      // Start point
      positions[i * 6] = start[0];
      positions[i * 6 + 1] = start[1];
      positions[i * 6 + 2] = start[2];
      
      // End point
      positions[i * 6 + 3] = end[0];
      positions[i * 6 + 4] = end[1];
      positions[i * 6 + 5] = end[2];
    }
    
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.attributes['position'].needsUpdate = true;
  }
  
  /**
   * Create pool of reusable box objects
   */
  private createBoxPool(): void {
    if (!this.scene) return;
    
    this.boxPool = [];
    
    for (let i = 0; i < this.MAX_BOXES; i++) {
      // Create geometry
      const geometry = new THREE.BufferGeometry();
      // Initialize with dummy box
      this.updateBoxGeometry(geometry, {
        id: i,
        label: 'temp',
        label_index: 0,
        confidence: 1.0,
        center: [0, 0, 0],
        size: [1, 1, 1],
        yaw: 0,
        color: [255, 255, 255]
      });
      
      // Create material
      const material = new THREE.LineBasicMaterial({
        color: 0xffffff,
        linewidth: 2,
        transparent: true,
        opacity: 0.8
      });
      
      // Create mesh
      const mesh = new THREE.LineSegments(geometry, material);
      mesh.visible = false;
      
      // Enable custom frustum culling instead of Three.js built-in
      mesh.frustumCulled = true;
      
      // Coordinate system transformation (LiDAR to Three.js)
      mesh.rotation.x = -Math.PI / 2;
      mesh.rotation.z = -Math.PI / 2;
      
      this.scene.add(mesh);
      
      this.boxPool.push({
        mesh,
        geometry,
        material,
        isActive: false
      });
    }
    
    console.log(`BoundingBoxRenderer: Created pool of ${this.MAX_BOXES} boxes`);
  }
  
  /**
   * Hide all bounding boxes
   */
  private hideAllBoxes(): void {
    for (const boxData of this.boxPool) {
      boxData.mesh.visible = false;
      boxData.isActive = false;
    }
    this.activeBoxCount = 0;
  }
  
  /**
   * Set camera reference for LOD calculations
   */
  setCamera(camera: THREE.Camera): void {
    this.camera = camera;
  }
  
  /**
   * Get performance metrics
   */
  getPerformanceMetrics(): { lastFrameTime: number; isRenderingTooSlow: boolean; activeBoxCount: number } {
    return {
      lastFrameTime: this.lastFrameTime,
      isRenderingTooSlow: this.renderingTooSlow,
      activeBoxCount: this.activeBoxCount
    };
  }
  
  /**
   * Enable/disable degraded rendering for performance
   */
  setDegradedMode(enabled: boolean): void {
    if (enabled) {
      // Reduce LOD distances for better performance
      this.LOD_DISTANCES.HIGH_DETAIL = 10;
      this.LOD_DISTANCES.MID_DETAIL = 25;
      this.LOD_DISTANCES.LOW_DETAIL = 50;
      this.LOD_DISTANCES.CULL_DISTANCE = 75;
    } else {
      // Restore default distances
      this.LOD_DISTANCES.HIGH_DETAIL = 20;
      this.LOD_DISTANCES.MID_DETAIL = 50;
      this.LOD_DISTANCES.LOW_DETAIL = 100;
      this.LOD_DISTANCES.CULL_DISTANCE = 150;
    }
  }
  
  /**
   * Get current number of active boxes
   */
  getActiveBoxCount(): number {
    return this.activeBoxCount;
  }
  
  /**
   * Set opacity for all boxes
   */
  setOpacity(opacity: number): void {
    for (const boxData of this.boxPool) {
      boxData.material.opacity = Math.max(0, Math.min(1, opacity));
    }
  }
  
  /**
   * Update geometry with LOD considerations
   */
  private updateBoxGeometryWithLOD(geometry: THREE.BufferGeometry, box: BoundingBox3D, lodLevel: number): void {
    switch (lodLevel) {
      case 0: // High detail - full wireframe
        this.updateBoxGeometry(geometry, box);
        break;
      case 1: // Mid detail - simplified wireframe (8 lines instead of 12)
        this.updateSimplifiedBoxGeometry(geometry, box);
        break;
      case 2: // Low detail - corner markers only
        this.updateCornerMarkersGeometry(geometry, box);
        break;
      case 3: // Minimal detail - single point
        this.updatePointGeometry(geometry, box);
        break;
    }
  }
  
  /**
   * Update material properties for LOD
   */
  private updateMaterialForLOD(material: THREE.LineBasicMaterial, distance: number, lodLevel: number): void {
    // Adjust opacity based on distance
    const maxOpacity = 0.8;
    const fadeStart = this.LOD_DISTANCES.MID_DETAIL;
    const fadeEnd = this.LOD_DISTANCES.CULL_DISTANCE;
    
    if (distance <= fadeStart) {
      material.opacity = maxOpacity;
    } else {
      const fadeRatio = (distance - fadeStart) / (fadeEnd - fadeStart);
      material.opacity = maxOpacity * (1 - fadeRatio * 0.5); // Fade to 50% opacity
    }
    
    // Adjust line width based on LOD
    switch (lodLevel) {
      case 0: material.linewidth = 2; break;
      case 1: material.linewidth = 1.5; break;
      case 2: material.linewidth = 1; break;
      case 3: material.linewidth = 3; break; // Point markers need to be more visible
    }
  }
  
  /**
   * Generate simplified 8-line cube wireframe (corners only)
   */
  private updateSimplifiedBoxGeometry(geometry: THREE.BufferGeometry, box: BoundingBox3D): void {
    const [dx, dy, dz] = box.size;
    const halfX = dx / 2;
    const halfY = dy / 2; 
    const halfZ = dz / 2;
    
    // Only draw 4 vertical edges and 4 corner connections
    const lines = [
      // Vertical edges
      [[-halfX, -halfY, -halfZ], [-halfX, -halfY, +halfZ]], // front-left
      [[+halfX, -halfY, -halfZ], [+halfX, -halfY, +halfZ]], // front-right
      [[+halfX, +halfY, -halfZ], [+halfX, +halfY, +halfZ]], // back-right
      [[-halfX, +halfY, -halfZ], [-halfX, +halfY, +halfZ]], // back-left
      // Top corners only
      [[-halfX, -halfY, +halfZ], [+halfX, -halfY, +halfZ]], // top-front
      [[+halfX, -halfY, +halfZ], [+halfX, +halfY, +halfZ]], // top-right
      [[+halfX, +halfY, +halfZ], [-halfX, +halfY, +halfZ]], // top-back
      [[-halfX, +halfY, +halfZ], [-halfX, -halfY, +halfZ]], // top-left
    ];
    
    const positions = new Float32Array(lines.length * 6);
    
    for (let i = 0; i < lines.length; i++) {
      const [start, end] = lines[i];
      
      positions[i * 6] = start[0];
      positions[i * 6 + 1] = start[1];
      positions[i * 6 + 2] = start[2];
      
      positions[i * 6 + 3] = end[0];
      positions[i * 6 + 4] = end[1];
      positions[i * 6 + 5] = end[2];
    }
    
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.attributes['position'].needsUpdate = true;
  }
  
  /**
   * Generate corner markers (small crosses at each corner)
   */
  private updateCornerMarkersGeometry(geometry: THREE.BufferGeometry, box: BoundingBox3D): void {
    const [dx, dy, dz] = box.size;
    const halfX = dx / 2;
    const halfY = dy / 2; 
    const halfZ = dz / 2;
    const markerSize = Math.min(dx, dy, dz) * 0.1; // 10% of smallest dimension
    
    const corners = [
      [-halfX, -halfY, -halfZ], [+halfX, -halfY, -halfZ],
      [+halfX, +halfY, -halfZ], [-halfX, +halfY, -halfZ],
      [-halfX, -halfY, +halfZ], [+halfX, -halfY, +halfZ],
      [+halfX, +halfY, +halfZ], [-halfX, +halfY, +halfZ]
    ];
    
    const lines: number[][] = [];
    
    // Create small cross at each corner
    for (const corner of corners) {
      const [x, y, z] = corner;
      // X-axis marker
      lines.push([x - markerSize, y, z], [x + markerSize, y, z]);
      // Y-axis marker
      lines.push([x, y - markerSize, z], [x, y + markerSize, z]);
      // Z-axis marker
      lines.push([x, y, z - markerSize], [x, y, z + markerSize]);
    }
    
    const positions = new Float32Array(lines.length * 3);
    
    for (let i = 0; i < lines.length; i++) {
      positions[i * 3] = lines[i][0];
      positions[i * 3 + 1] = lines[i][1];
      positions[i * 3 + 2] = lines[i][2];
    }
    
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.attributes['position'].needsUpdate = true;
  }
  
  /**
   * Generate single point geometry for maximum distance
   */
  private updatePointGeometry(geometry: THREE.BufferGeometry, box: BoundingBox3D): void {
    const positions = new Float32Array(6); // Single line with no length (point)
    
    // Center point repeated twice to create a degenerate line (appears as point)
    positions[0] = 0; positions[1] = 0; positions[2] = 0;
    positions[3] = 0; positions[4] = 0; positions[5] = 0;
    
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.attributes['position'].needsUpdate = true;
  }
  
  /**
   * Generate 12-line cube wireframe geometry (full detail)
   */
  setLineWidth(width: number): void {
    for (const boxData of this.boxPool) {
      boxData.material.linewidth = Math.max(1, width);
    }
  }
  
  /**
   * Toggle visibility of all bounding boxes
   */
  setVisible(visible: boolean): void {
    for (const boxData of this.boxPool) {
      if (boxData.isActive) {
        boxData.mesh.visible = visible;
      }
    }
  }
  
  /**
   * Dispose of all resources
   */
  dispose(): void {
    this.boxPool.forEach(box => {
      if (this.scene) {
        this.scene.remove(box.mesh);
      }
      box.geometry.dispose();
      box.material.dispose();
    });
    this.boxPool = [];
    this.activeBoxCount = 0;
  }
  
  /**
   * Clear all bounding boxes from scene
   */
  clearBoundingBoxes(): void {
    this.hideAllBoxes();
    this.activeBoxCount = 0;
  }
}