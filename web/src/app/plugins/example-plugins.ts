import { NodePlugin } from '../core/models/node-plugin.model';

/**
 * Example: Transform Node Plugin
 *
 * This plugin demonstrates how to create a custom node that applies
 * transformations to point cloud data.
 */
export const transformNodePlugin: NodePlugin = {
  type: 'transform',
  displayName: 'Transform Node',
  description: 'Apply transformations to point clouds',
  icon: 'transform',
  category: 'transform',
  style: {
    color: '#f59e0b', // amber
    backgroundColor: '#fffbeb',
  },
  ports: {
    inputs: [
      {
        id: 'input',
        label: 'Point Cloud Input',
        dataType: 'pointcloud',
        multiple: false,
      },
    ],
    outputs: [
      {
        id: 'output',
        label: 'Transformed Output',
        dataType: 'pointcloud',
        multiple: true,
      },
    ],
  },
  createInstance: () => ({
    type: 'transform',
    name: 'New Transform',
    enabled: false,
    translation: { x: 0, y: 0, z: 0 },
    rotation: { roll: 0, pitch: 0, yaw: 0 },
    scale: 1.0,
  }),
  renderBody: (data) => {
    const transformData = data as any;
    return {
      fields: [
        {
          label: 'Translation',
          value: `(${transformData.translation?.x || 0}, ${transformData.translation?.y || 0}, ${transformData.translation?.z || 0})`,
        },
        {
          label: 'Rotation',
          value: `(${transformData.rotation?.roll || 0}, ${transformData.rotation?.pitch || 0}, ${transformData.rotation?.yaw || 0})`,
        },
        {
          label: 'Scale',
          value: transformData.scale || 1.0,
          type: 'number',
        },
      ],
    };
  },
  validate: (data) => {
    const errors = [];
    const transformData = data as any;

    if (!transformData.name) {
      errors.push('Name is required');
    }

    if (transformData.scale && transformData.scale <= 0) {
      errors.push('Scale must be positive');
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  },
  // Note: You would create a TransformEditorComponent similar to LidarEditorComponent
  // editorComponent: TransformEditorComponent,
};

/**
 * Example: Filter Node Plugin
 *
 * This plugin demonstrates a statistical outlier filter node.
 */
export const filterNodePlugin: NodePlugin = {
  type: 'filter',
  displayName: 'Filter Node',
  category: 'filter',
  description: 'Filter outliers from point clouds',
  icon: 'filter_alt',
  style: {
    color: '#8b5cf6', // purple
    backgroundColor: '#f5f3ff',
  },
  ports: {
    inputs: [
      {
        id: 'input',
        label: 'Point Cloud Input',
        dataType: 'pointcloud',
        multiple: false,
      },
    ],
    outputs: [
      {
        id: 'output',
        label: 'Filtered Output',
        dataType: 'pointcloud',
        multiple: true,
      },
    ],
  },
  createInstance: () => ({
    type: 'filter',
    name: 'New Filter',
    enabled: false,
    filterType: 'statistical',
    neighbors: 50,
    stdRatio: 2.0,
  }),
  renderBody: (data) => {
    const filterData = data as any;
    return {
      fields: [
        { label: 'Type', value: filterData.filterType || 'statistical' },
        { label: 'Neighbors', value: filterData.neighbors || 50, type: 'number' },
        { label: 'Std Ratio', value: filterData.stdRatio || 2.0, type: 'number' },
      ],
    };
  },
  validate: (data) => {
    const errors = [];
    const filterData = data as any;

    if (!filterData.name) {
      errors.push('Name is required');
    }

    if (filterData.neighbors && filterData.neighbors < 1) {
      errors.push('Neighbors must be at least 1');
    }

    if (filterData.stdRatio && filterData.stdRatio <= 0) {
      errors.push('Standard deviation ratio must be positive');
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  },
};

/**
 * Example: Recording Node Plugin
 *
 * Records point cloud data to disk.
 */
export const recordingNodePlugin: NodePlugin = {
  type: 'recording',
  displayName: 'Recording Node',
  description: 'Record point clouds to disk',
  category: 'recording',
  icon: 'fiber_manual_record',
  style: {
    color: '#ef4444', // red
    backgroundColor: '#fef2f2',
  },
  ports: {
    inputs: [
      {
        id: 'input',
        label: 'Point Cloud Input',
        dataType: 'pointcloud',
        multiple: false,
      },
    ],
  },
  createInstance: () => ({
    type: 'recording',
    name: 'New Recording',
    enabled: false,
    outputPath: '/recordings',
    format: 'pcd',
    maxFiles: 1000,
  }),
  renderBody: (data) => {
    const recordData = data as any;
    return {
      fields: [
        { label: 'Path', value: recordData.outputPath || '/recordings' },
        { label: 'Format', value: recordData.format || 'pcd' },
        { label: 'Max Files', value: recordData.maxFiles || 1000, type: 'number' },
      ],
    };
  },
  validate: (data) => {
    const errors = [];
    const recordData = data as any;

    if (!recordData.name) {
      errors.push('Name is required');
    }

    if (!recordData.outputPath) {
      errors.push('Output path is required');
    }

    if (recordData.maxFiles && recordData.maxFiles < 1) {
      errors.push('Max files must be at least 1');
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  },
};
