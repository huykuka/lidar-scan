import { Injectable } from '@angular/core';
import { LidarProfile } from '../models/lidar-profile.model';

interface LidarImageMapping {
  [key: string]: string;
}

@Injectable({
  providedIn: 'root'
})
export class LidarImagesService {
  
  // Mapping of LiDAR model_id to their specific image paths
  // Currently using placeholder for all, but easily extensible for real images
  private lidarImageMap: LidarImageMapping = {
    'multiscan': '/lidar-placeholder.svg',
    'tim_5xx': '/lidar-placeholder.svg',
    'tim_7xx': '/lidar-placeholder.svg',
    'tim_4xx': '/lidar-placeholder.svg',
    'tim_2xx': '/lidar-placeholder.svg',
    'lms_1xx': '/lidar-placeholder.svg',
    'lms_5xx': '/lidar-placeholder.svg',
    'lms_4xxx': '/lidar-placeholder.svg',
    'mrs_1xxx': '/lidar-placeholder.svg',
    'mrs_6xxx': '/lidar-placeholder.svg',
  };

  /**
   * Gets the image path for a given LiDAR device model
   * @param modelId - The model_id from LidarProfile
   * @returns The path to the device image
   */
  getImagePath(modelId: string): string {
    return this.lidarImageMap[modelId] || '/lidar-placeholder.svg';
  }

  /**
   * Updates the image mapping for a specific LiDAR model
   * This will be useful when real device images are provided
   * @param modelId - The model_id to update
   * @param imagePath - The new path to the device image
   */
  updateImagePath(modelId: string, imagePath: string): void {
    this.lidarImageMap[modelId] = imagePath;
  }

  /**
   * Bulk update of image mappings
   * @param mappings - Object containing model_id to image path mappings
   */
  updateImageMappings(mappings: LidarImageMapping): void {
    this.lidarImageMap = { ...this.lidarImageMap, ...mappings };
  }

  /**
   * Gets all current image mappings
   * Useful for debugging or configuration purposes
   */
  getAllImageMappings(): LidarImageMapping {
    return { ...this.lidarImageMap };
  }
}
