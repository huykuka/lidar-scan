// LIDR v2 WebSocket Frame Decoder Service
// Extends existing WebSocket service for v2 binary frame parsing

import { Injectable } from '@angular/core';
import { LidrV2Frame, DetectionFrameMetadata } from '../../core/models/ml.model';

@Injectable({
  providedIn: 'root'
})
export class LidrV2DecoderService {
  
  /**
   * Decode LIDR v2 binary frame from WebSocket ArrayBuffer
   * @param buffer ArrayBuffer from WebSocket message
   * @returns Parsed LidrV2Frame or null if invalid
   */
  decodeLidrV2Frame(buffer: ArrayBuffer): LidrV2Frame | null {
    try {
      if (buffer.byteLength < 20) {
        console.warn('LIDR frame too small:', buffer.byteLength);
        return null;
      }
      
      const view = new DataView(buffer);
      let offset = 0;
      
      // Read header
      const magicBytes = view.getUint32(offset, false); offset += 4;
      const magic = String.fromCharCode(
        (magicBytes >> 24) & 0xFF,
        (magicBytes >> 16) & 0xFF, 
        (magicBytes >> 8) & 0xFF,
        magicBytes & 0xFF
      );
      
      if (magic !== 'LIDR') {
        console.warn('Invalid LIDR magic bytes:', magic);
        return null;
      }
      
      const version = view.getUint32(offset, true); offset += 4;
      if (version !== 2) {
        console.warn('Unsupported LIDR version:', version);
        return null;
      }
      
      const timestamp = Number(view.getBigUint64(offset, true)); offset += 8;
      const point_count = view.getUint32(offset, true); offset += 4;
      const flags = view.getUint32(offset, true); offset += 4;
      
      const has_labels = (flags & 1) !== 0;
      const has_boxes = (flags & 2) !== 0;
      
      // Calculate expected sizes
      const positionsSize = point_count * 12; // 3 floats per point
      const labelsSize = has_labels ? point_count * 4 : 0; // 1 int32 per point
      
      if (buffer.byteLength < offset + positionsSize + labelsSize) {
        console.warn('LIDR frame incomplete - expected size:', offset + positionsSize + labelsSize, 'actual:', buffer.byteLength);
        return null;
      }
      
      // Read XYZ positions
      const positions = new Float32Array(buffer, offset, point_count * 3);
      offset += positionsSize;
      
      // Read semantic labels (conditional)
      let labels: Int32Array | undefined;
      if (has_labels) {
        labels = new Int32Array(buffer, offset, point_count);
        offset += labelsSize;
      }
      
      // Read bounding boxes metadata (conditional)
      let metadata: DetectionFrameMetadata | undefined;
      if (has_boxes && offset < buffer.byteLength) {
        try {
          const jsonLength = view.getUint32(offset, true); offset += 4;
          
          if (offset + jsonLength <= buffer.byteLength) {
            const jsonBytes = new Uint8Array(buffer, offset, jsonLength);
            const jsonString = new TextDecoder().decode(jsonBytes);
            metadata = JSON.parse(jsonString) as DetectionFrameMetadata;
          }
        } catch (err) {
          console.warn('Failed to parse LIDR v2 metadata:', err);
        }
      }
      
      return {
        magic,
        version,
        timestamp,
        point_count,
        flags,
        positions,
        labels,
        metadata
      };
      
    } catch (err) {
      console.error('LIDR v2 decode error:', err);
      return null;
    }
  }
  
  /**
   * Check if ArrayBuffer contains a valid LIDR frame (any version)
   * @param buffer ArrayBuffer to check
   * @returns Version number or 0 if invalid
   */
  detectLidrVersion(buffer: ArrayBuffer): number {
    if (buffer.byteLength < 8) return 0;
    
    const view = new DataView(buffer);
    const magicBytes = view.getUint32(0, false);
    const magic = String.fromCharCode(
      (magicBytes >> 24) & 0xFF,
      (magicBytes >> 16) & 0xFF, 
      (magicBytes >> 8) & 0xFF,
      magicBytes & 0xFF
    );
    
    if (magic !== 'LIDR') return 0;
    
    const version = view.getUint32(4, true);
    return version;
  }
  
  /**
   * Legacy v1 decoder for backward compatibility
   * @param buffer ArrayBuffer from WebSocket
   * @returns Basic point cloud data
   */
  decodeLidrV1Frame(buffer: ArrayBuffer): { positions: Float32Array; point_count: number } | null {
    // Simplified v1 decoder - assumes just XYZ positions
    if (buffer.byteLength < 12) return null;
    
    try {
      const point_count = Math.floor(buffer.byteLength / 12);
      const positions = new Float32Array(buffer, 0, point_count * 3);
      
      return { positions, point_count };
    } catch (err) {
      console.error('LIDR v1 decode error:', err);
      return null;
    }
  }
}