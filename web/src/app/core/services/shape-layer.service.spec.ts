import {TestBed} from '@angular/core/testing';
import * as THREE from 'three';
import {vi, describe, it, expect, beforeEach, afterEach} from 'vitest';
import {ShapeLayerService} from './shape-layer.service';
import {ShapeFrame, SHAPE_LAYER} from '@core/models/shapes.model';

// ── Frame factories ────────────────────────────────────────────────────────────

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

/**
 * Helper: create a standalone ShapeLayerService instance **without** TestBed.
 * This mirrors how Angular creates per-component instances when the service
 * is listed in a component's `providers` array (not `providedIn: 'root'`).
 */
function makeService(): ShapeLayerService {
  return new ShapeLayerService();
}

// ── Single-scene (baseline) tests ──────────────────────────────────────────────

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

// ── Split-view isolation tests ────────────────────────────────────────────────
//
// These tests simulate a split-view workspace with two independent
// PointCloudComponent instances — each owning its own ShapeLayerService,
// its own THREE.Scene, and its own WebGL renderer.
//
// Key invariants verified:
//   1. Shapes are present in BOTH scenes after applyFrame (no "one view only")
//   2. scene.add is called exactly once per service per shape id (no duplicates)
//   3. Shapes in scene A are independent from shapes in scene B
//   4. Disposing pane A does NOT remove objects from pane B
//   5. Replacing a scene (hot-reload / pane remount) cleans up the old scene

describe('ShapeLayerService — split-view isolation', () => {
  // Two service instances simulating two PointCloudComponent panes
  let serviceA: ShapeLayerService;
  let serviceB: ShapeLayerService;
  let sceneA: THREE.Scene;
  let sceneB: THREE.Scene;

  beforeEach(() => {
    // Directly instantiate — mirrors Angular's per-component provider behavior
    serviceA = makeService();
    serviceB = makeService();
    sceneA = new THREE.Scene();
    sceneB = new THREE.Scene();
    serviceA.init(sceneA);
    serviceB.init(sceneB);
  });

  afterEach(() => {
    serviceA.disposeAll();
    serviceB.disposeAll();
  });

  it('each pane has its own isolated shapeMap — shape counts are independent', () => {
    // Send a single frame with two shapes to pane A
    const twoShapeFrame: ShapeFrame = {
      timestamp: 1.0,
      shapes: [
        {
          id: 'cube1',
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
          id: 'plane1',
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
    };
    serviceA.applyFrame(twoShapeFrame);

    // Pane B only gets the cube
    serviceB.applyFrame(makeCubeFrame('cube1'));

    // Pane A has two shapes; pane B has only one
    expect(serviceA.shapeCount).toBe(2);
    expect(serviceB.shapeCount).toBe(1);
  });

  it('both panes receive identical shapes when fed the same frame — no "one view only" bug', () => {
    const frame: ShapeFrame = {
      timestamp: 2.0,
      shapes: [
        {
          id: 'shared_cube',
          node_name: 'Detector',
          type: 'cube',
          center: [1, 0, 0],
          size: [1, 1, 1],
          rotation: [0, 0, 0],
          color: '#00ff00',
          opacity: 0.5,
          wireframe: true,
          label: 'Object',
        } as any,
        {
          id: 'shared_label',
          node_name: 'Info',
          type: 'label',
          position: [0, 0, 2],
          text: 'Annotation',
          font_size: 14,
          color: '#ffff00',
          background_color: '#000000cc',
          scale: 1.0,
        } as any,
      ],
    };

    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);

    // Both panes must have both shapes
    expect(serviceA.shapeCount).toBe(2);
    expect(serviceB.shapeCount).toBe(2);

    // Both scenes must have had objects added
    const groupsA = sceneA.children.filter((c) => c instanceof THREE.Group);
    const groupsB = sceneB.children.filter((c) => c instanceof THREE.Group);
    expect(groupsA.length).toBeGreaterThanOrEqual(1);
    expect(groupsB.length).toBeGreaterThanOrEqual(1);
  });

  it('scene.add is called exactly once per pane per shape id — no duplicates on repeated frames', () => {
    const addSpyA = vi.spyOn(sceneA, 'add');
    const addSpyB = vi.spyOn(sceneB, 'add');

    const frame = makeCubeFrame('dup_test');

    // First frame — both panes add the object once
    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);
    expect(addSpyA).toHaveBeenCalledTimes(1);
    expect(addSpyB).toHaveBeenCalledTimes(1);
    addSpyA.mockClear();
    addSpyB.mockClear();

    // Subsequent frames — object already tracked; scene.add must NOT be called
    for (let i = 0; i < 5; i++) {
      serviceA.applyFrame(frame);
      serviceB.applyFrame(frame);
    }
    expect(addSpyA).not.toHaveBeenCalled();
    expect(addSpyB).not.toHaveBeenCalled();
  });

  it('objects in sceneA and sceneB are distinct Three.js instances (no shared Object3D)', () => {
    const frame = makeCubeFrame('iso_cube');
    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);

    const objA = sceneA.children.find((c) => c instanceof THREE.Group);
    const objB = sceneB.children.find((c) => c instanceof THREE.Group);

    expect(objA).toBeDefined();
    expect(objB).toBeDefined();
    // Each scene owns a separate Three.js object — NOT the same reference
    expect(objA).not.toBe(objB);
  });

  it('disposeAll on pane A does NOT remove or dispose objects from pane B', () => {
    const frame = makeCubeFrame('survivor');
    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);

    const removeSpyB = vi.spyOn(sceneB, 'remove');

    // Destroy pane A (simulates the component being unmounted)
    serviceA.disposeAll();

    expect(serviceA.shapeCount).toBe(0);
    expect(serviceB.shapeCount).toBe(1); // pane B untouched
    expect(removeSpyB).not.toHaveBeenCalled(); // sceneB.remove was never called
  });

  it('adding pane C mid-session does not duplicate shapes in A or B', () => {
    const serviceC = makeService();
    const sceneC = new THREE.Scene();
    serviceC.init(sceneC);

    const frame = makeCubeFrame('late_join');

    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);

    // Pane C joins late — should independently add its own copy
    const addSpyA = vi.spyOn(sceneA, 'add');
    const addSpyB = vi.spyOn(sceneB, 'add');

    serviceC.applyFrame(frame);

    // Pane C has the shape; A and B were NOT touched by C's init/applyFrame
    expect(serviceC.shapeCount).toBe(1);
    expect(addSpyA).not.toHaveBeenCalled();
    expect(addSpyB).not.toHaveBeenCalled();

    serviceC.disposeAll();
  });

  it('removing a pane and remounting (scene swap) cleans up the old scene', () => {
    serviceA.applyFrame(makeCubeFrame('remount_cube'));
    expect(sceneA.children.length).toBeGreaterThan(0);

    const sceneANew = new THREE.Scene();
    const removeSpyOld = vi.spyOn(sceneA, 'remove');

    // Simulate pane A being destroyed and recreated with a fresh scene
    serviceA.init(sceneANew);

    // Old scene should have had all objects removed
    expect(removeSpyOld).toHaveBeenCalled();
    // Service's internal map is cleared (objects disposed from old scene)
    expect(serviceA.shapeCount).toBe(0);
    // New scene has no orphan objects yet
    expect(sceneANew.children.length).toBe(0);

    serviceA.disposeAll();
  });

  it('label deduplication: at most one label object per id per scene', () => {
    const labelFrame = makeLabelFrame('dedup_lbl');

    serviceA.applyFrame(labelFrame);
    serviceB.applyFrame(labelFrame);

    // Apply 10 more frames
    for (let i = 0; i < 10; i++) {
      serviceA.applyFrame(labelFrame);
      serviceB.applyFrame(labelFrame);
    }

    // Each scene: exactly one sprite for the label id
    const spritesA = sceneA.children.filter((c) => c instanceof THREE.Sprite);
    const spritesB = sceneB.children.filter((c) => c instanceof THREE.Sprite);

    expect(spritesA.length).toBe(1);
    expect(spritesB.length).toBe(1);
    expect(serviceA.shapeCount).toBe(1);
    expect(serviceB.shapeCount).toBe(1);
  });

  it('stale shape removal in pane A does not affect identical id in pane B', () => {
    const frame = makeCubeFrame('stale_test');
    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);

    // Pane A clears all shapes (e.g. topic unsubscribed)
    serviceA.applyFrame({timestamp: 99.0, shapes: []});

    expect(serviceA.shapeCount).toBe(0);
    // Pane B still has the shape
    expect(serviceB.shapeCount).toBe(1);
    const objsInB = sceneB.children.filter((c) => c instanceof THREE.Group);
    expect(objsInB.length).toBeGreaterThanOrEqual(1);
  });

  it('four-pane (2×2 grid) scenario: all panes independently track the same shape set', () => {
    const serviceC = makeService();
    const serviceD = makeService();
    const sceneC = new THREE.Scene();
    const sceneD = new THREE.Scene();
    serviceC.init(sceneC);
    serviceD.init(sceneD);

    const frame: ShapeFrame = {
      timestamp: 5.0,
      shapes: Array.from({length: 3}, (_, i) => ({
        id: `quad_${i}`,
        node_name: 'Quad',
        type: 'cube',
        center: [i, 0, 0] as [number, number, number],
        size: [0.5, 0.5, 0.5] as [number, number, number],
        rotation: [0, 0, 0] as [number, number, number],
        color: '#aabbcc',
        opacity: 0.6,
        wireframe: false,
        label: null,
      })) as any,
    };

    [serviceA, serviceB, serviceC, serviceD].forEach((s) => s.applyFrame(frame));

    // All four panes must have exactly 3 shapes each
    expect(serviceA.shapeCount).toBe(3);
    expect(serviceB.shapeCount).toBe(3);
    expect(serviceC.shapeCount).toBe(3);
    expect(serviceD.shapeCount).toBe(3);

    // Apply 5 more frames — no additional objects created
    for (let i = 0; i < 5; i++) {
      [serviceA, serviceB, serviceC, serviceD].forEach((s) => s.applyFrame(frame));
    }
    expect(serviceA.shapeCount).toBe(3);
    expect(serviceB.shapeCount).toBe(3);
    expect(serviceC.shapeCount).toBe(3);
    expect(serviceD.shapeCount).toBe(3);

    serviceC.disposeAll();
    serviceD.disposeAll();
  });
});
