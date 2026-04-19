import {TestBed} from '@angular/core/testing';
import * as THREE from 'three';
import {vi, describe, it, expect, beforeEach, afterEach} from 'vitest';
import {ShapeLayerService} from './shape-layer.service';
import {ShapeFrame, SHAPE_LAYER} from '@core/models/shapes.model';

function makeCubeFrame(id: string, overrides: Partial<any> = {}): ShapeFrame {
  return {
    timestamp: 1.0,
    shapes: [
      {
        id,
        node_name: 'test',
        type: 'cube',
        center: [0, 0, 0],
        size: [1, 1, 1],
        rotation: [0, 0, 0],
        color: '#ff0000',
        opacity: 0.5,
        wireframe: true,
        label: null,
        ...overrides,
      },
    ],
  };
}

function makePlaneFrame(id: string): ShapeFrame {
  return {
    timestamp: 1.0,
    shapes: [
      {
        id,
        node_name: 'test',
        type: 'plane',
        center: [0, 0, 0],
        normal: [0, 0, 1],
        width: 5,
        height: 5,
        color: '#0000ff',
        opacity: 0.3,
      },
    ],
  };
}

function makeLabelFrame(id: string): ShapeFrame {
  return {
    timestamp: 1.0,
    shapes: [
      {
        id,
        node_name: 'test',
        type: 'label',
        position: [1, 2, 3],
        text: 'Hello',
        font_size: 14,
        color: '#ffffff',
        background_color: '#000000cc',
        scale: 1.0,
      },
    ],
  };
}

describe('ShapeLayerService', () => {
  let service: ShapeLayerService;
  let scene: THREE.Scene;

  beforeEach(() => {
    TestBed.configureTestingModule({providers: [ShapeLayerService]});
    service = TestBed.inject(ShapeLayerService);
    scene = new THREE.Scene();
    service.init(scene);
  });

  afterEach(() => {
    service.disposeAll();
  });

  // ── Basic add ──────────────────────────────────────────────────────────────

  it('should add a new cube shape to the scene', () => {
    const addSpy = vi.spyOn(scene, 'add');
    service.applyFrame(makeCubeFrame('id1'));
    expect(addSpy).toHaveBeenCalled();
    expect(service.shapeCount).toBe(1);
  });

  it('should add a plane shape to the scene', () => {
    service.applyFrame(makePlaneFrame('plane1'));
    expect(service.shapeCount).toBe(1);
  });

  it('should add a label shape to the scene', () => {
    service.applyFrame(makeLabelFrame('lbl1'));
    expect(service.shapeCount).toBe(1);
  });

  // ── Update (no re-add) ─────────────────────────────────────────────────────

  it('should NOT call scene.add again when same id appears in next frame', () => {
    service.applyFrame(makeCubeFrame('id1'));

    const addSpy = vi.spyOn(scene, 'add');
    service.applyFrame(makeCubeFrame('id1', {color: '#00ff00'})); // same id, different color

    expect(addSpy).not.toHaveBeenCalled();
    expect(service.shapeCount).toBe(1);
  });

  // ── Remove stale ──────────────────────────────────────────────────────────

  it('should remove stale shape when id disappears from frame', () => {
    service.applyFrame(makeCubeFrame('id1'));
    const removeSpy = vi.spyOn(scene, 'remove');

    service.applyFrame({timestamp: 2.0, shapes: []}); // empty → all stale

    expect(removeSpy).toHaveBeenCalled();
    expect(service.shapeCount).toBe(0);
  });

  // ── Empty frame clears all ────────────────────────────────────────────────

  it('should clear all shapes on empty frame', () => {
    // Send a frame with two shapes at once
    service.applyFrame({
      timestamp: 1.0,
      shapes: [
        {
          id: 'a',
          node_name: 'test',
          type: 'cube',
          center: [0, 0, 0],
          size: [1, 1, 1],
          rotation: [0, 0, 0],
          color: '#ff0000',
          opacity: 0.5,
          wireframe: true,
          label: null,
        },
        {
          id: 'b',
          node_name: 'test',
          type: 'plane',
          center: [0, 0, 0],
          normal: [0, 0, 1],
          width: 5,
          height: 5,
          color: '#0000ff',
          opacity: 0.3,
        },
      ] as any,
    });
    expect(service.shapeCount).toBe(2);

    service.applyFrame({timestamp: 3.0, shapes: []});
    expect(service.shapeCount).toBe(0);
  });

  // ── Unknown type ──────────────────────────────────────────────────────────

  it('should skip unknown shape type and NOT throw', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(() => {
      service.applyFrame({
        timestamp: 1.0,
        shapes: [{id: 'x1', node_name: 'n', type: 'arrow'} as any],
      });
    }).not.toThrow();

    expect(service.shapeCount).toBe(0);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Unknown shape type'),
    );
    warnSpy.mockRestore();
  });

  // ── Empty id guard ─────────────────────────────────────────────────────────

  it('should skip shape with empty id and log contract violation', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    service.applyFrame(makeCubeFrame(''));
    expect(service.shapeCount).toBe(0);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('empty id'),
      expect.anything(),
    );
    warnSpy.mockRestore();
  });

  // ── Layer assignment ──────────────────────────────────────────────────────

  it('should assign SHAPE_LAYER to new shape objects', () => {
    service.applyFrame(makeCubeFrame('id_layer'));
    const obj = (scene.children as THREE.Object3D[]).find(
      (c) => c instanceof THREE.Group,
    ) as THREE.Group;
    expect(obj).toBeTruthy();
    expect(obj.layers.isEnabled(SHAPE_LAYER)).toBe(true);
  });

  // ── High shape count resilience ────────────────────────────────────────────

  it('should handle 500 shapes in a single frame without error', () => {
    const shapes = Array.from({length: 500}, (_, i) => ({
      id: `shape_${i}`,
      node_name: 'load_test',
      type: 'cube',
      center: [i * 0.1, 0, 0] as [number, number, number],
      size: [0.5, 0.5, 0.5] as [number, number, number],
      rotation: [0, 0, 0] as [number, number, number],
      color: '#00ff00',
      opacity: 0.4,
      wireframe: true,
      label: null,
    }));

    expect(() => service.applyFrame({timestamp: 1.0, shapes: shapes as any})).not.toThrow();
    expect(service.shapeCount).toBe(500);
  });

  // ── Anti-flicker: scene.add must be called exactly once per stable id ────

  it('should call scene.add exactly once for the same id across 10 consecutive frames (no-flicker)', () => {
    const addSpy = vi.spyOn(scene, 'add');

    // First frame — shape is new, must be added once.
    service.applyFrame(makeCubeFrame('stable_id'));
    expect(addSpy).toHaveBeenCalledTimes(1);
    addSpy.mockClear();

    // Nine more frames with identical content — must NOT trigger scene.add again.
    for (let i = 0; i < 9; i++) {
      service.applyFrame(makeCubeFrame('stable_id'));
    }
    expect(addSpy).not.toHaveBeenCalled();
    expect(service.shapeCount).toBe(1);
  });

  it('should call scene.add exactly once for the same id even when properties change (update in-place)', () => {
    service.applyFrame(makeCubeFrame('mut_id', {color: '#ff0000'}));

    const addSpy = vi.spyOn(scene, 'add');
    service.applyFrame(makeCubeFrame('mut_id', {color: '#00ff00'}));
    service.applyFrame(makeCubeFrame('mut_id', {color: '#0000ff', opacity: 0.9}));

    expect(addSpy).not.toHaveBeenCalled();
    expect(service.shapeCount).toBe(1);
  });

  // ── Standalone label — one object per id ─────────────────────────────────

  it('should maintain exactly one label object per unique id across repeated frames', () => {
    service.applyFrame(makeLabelFrame('lbl_unique'));
    const addSpy = vi.spyOn(scene, 'add');

    for (let i = 0; i < 5; i++) {
      service.applyFrame(makeLabelFrame('lbl_unique'));
    }
    expect(addSpy).not.toHaveBeenCalled();
    expect(service.shapeCount).toBe(1);
  });

  // ── disposeAll ────────────────────────────────────────────────────────────

  it('disposeAll should remove all shapes and clear the scene', () => {
    service.applyFrame(makeCubeFrame('d1'));
    service.applyFrame(makePlaneFrame('d2'));
    service.disposeAll();
    expect(service.shapeCount).toBe(0);
  });
});
