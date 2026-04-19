import {TestBed} from '@angular/core/testing';
import * as THREE from 'three';
import {vi, describe, it, expect, beforeEach, afterEach} from 'vitest';
import {ShapeLayerService, SHAPE_DECAY_MS, SHAPE_FADE_WINDOW_MS, SHAPE_LERP_ALPHA} from './shape-layer.service';
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

const EMPTY_FRAME: ShapeFrame = {timestamp: 99.0, shapes: []};

/**
 * Helper: create a standalone ShapeLayerService instance **without** TestBed.
 * This mirrors how Angular creates per-component instances when the service
 * is listed in a component's `providers` array (not `providedIn: 'root'`).
 */
function makeService(): ShapeLayerService {
  return new ShapeLayerService();
}

/** Create a service with a controllable clock. */
function makeTimedService(): {service: ShapeLayerService; clock: {now: number}} {
  const clock = {now: 1000};
  const service = new ShapeLayerService();
  service.now = () => clock.now;
  return {service, clock};
}

// ── Single-scene (baseline) tests ──────────────────────────────────────────────

describe('ShapeLayerService', () => {
  let service: ShapeLayerService;
  let scene: THREE.Scene;
  let clock: {now: number};

  beforeEach(() => {
    const timed = makeTimedService();
    service = timed.service;
    clock = timed.clock;
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

  // ── Decay: shape NOT removed immediately on empty frame ────────────────────

  it('should NOT remove shape immediately when absent from frame (decay)', () => {
    service.applyFrame(makeCubeFrame('id1'));
    const removeSpy = vi.spyOn(scene, 'remove');

    // Empty frame — shape should still be tracked (decaying)
    clock.now += 100; // only 100ms later
    service.applyFrame(EMPTY_FRAME);

    expect(removeSpy).not.toHaveBeenCalled();
    expect(service.shapeCount).toBe(1);
  });

  it('should remove shape after SHAPE_DECAY_MS has elapsed', () => {
    service.applyFrame(makeCubeFrame('id1'));
    const removeSpy = vi.spyOn(scene, 'remove');

    // Advance past decay window
    clock.now += SHAPE_DECAY_MS + 1;
    service.applyFrame(EMPTY_FRAME);

    expect(removeSpy).toHaveBeenCalled();
    expect(service.shapeCount).toBe(0);
  });

  it('should refresh lastSeen when shape reappears before decay', () => {
    service.applyFrame(makeCubeFrame('id1'));

    // Shape disappears for 400ms (within decay)
    clock.now += 400;
    service.applyFrame(EMPTY_FRAME);
    expect(service.shapeCount).toBe(1); // still alive

    // Shape comes back — refreshes lastSeen
    clock.now += 50;
    service.applyFrame(makeCubeFrame('id1'));
    expect(service.shapeCount).toBe(1);

    // Another 400ms without — should NOT be removed (lastSeen was refreshed)
    clock.now += 400;
    service.applyFrame(EMPTY_FRAME);
    expect(service.shapeCount).toBe(1);

    // But after full decay from the refreshed time, it should be removed
    clock.now += SHAPE_DECAY_MS;
    service.applyFrame(EMPTY_FRAME);
    expect(service.shapeCount).toBe(0);
  });

  it('should fade opacity during the last SHAPE_FADE_WINDOW_MS of decay', () => {
    service.applyFrame(makeCubeFrame('fade_test', {opacity: 0.8}));

    // Move to start of fade window (SHAPE_DECAY_MS - SHAPE_FADE_WINDOW_MS = 300ms)
    clock.now += SHAPE_DECAY_MS - SHAPE_FADE_WINDOW_MS + 1; // 301ms
    service.applyFrame(EMPTY_FRAME);

    // Shape should still exist but with reduced opacity
    expect(service.shapeCount).toBe(1);

    // Verify opacity was reduced on the object's material
    const group = scene.children.find((c) => c instanceof THREE.Group) as THREE.Group;
    expect(group).toBeTruthy();
    const mesh = group.children.find(
      (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
    ) as THREE.LineSegments;
    if (mesh) {
      const mat = mesh.material as THREE.Material;
      expect(mat.opacity).toBeLessThan(0.8);
      expect(mat.opacity).toBeGreaterThan(0);
    }
  });

  // ── Empty frame with decay ────────────────────────────────────────────────

  it('should clear all shapes only after decay expires on empty frame', () => {
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

    // Empty frame — shapes should persist during decay
    clock.now += 100;
    service.applyFrame(EMPTY_FRAME);
    expect(service.shapeCount).toBe(2);

    // After full decay — shapes removed
    clock.now += SHAPE_DECAY_MS;
    service.applyFrame(EMPTY_FRAME);
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

    service.applyFrame(makeCubeFrame('stable_id'));
    expect(addSpy).toHaveBeenCalledTimes(1);
    addSpy.mockClear();

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

  // ── Anti-flicker: shape survives brief empty frames ────────────────────────

  it('shape survives a brief empty-frame gap and reappears without re-add', () => {
    service.applyFrame(makeCubeFrame('blink'));
    const addSpy = vi.spyOn(scene, 'add');

    // Backend sends empty frame for 1 cycle
    clock.now += 50;
    service.applyFrame(EMPTY_FRAME);
    expect(service.shapeCount).toBe(1); // still alive (decaying)

    // Shape comes back — should NOT re-add
    clock.now += 50;
    service.applyFrame(makeCubeFrame('blink'));
    expect(addSpy).not.toHaveBeenCalled();
    expect(service.shapeCount).toBe(1);
  });
});

// ── Lerp smoothing tests ───────────────────────────────────────────────────────

describe('ShapeLayerService — lerp smoothing', () => {
  let service: ShapeLayerService;
  let scene: THREE.Scene;
  let clock: {now: number};

  beforeEach(() => {
    const timed = makeTimedService();
    service = timed.service;
    clock = timed.clock;
    scene = new THREE.Scene();
    service.init(scene);
  });

  afterEach(() => {
    service.disposeAll();
  });

  // ── New shapes snap to exact position ─────────────────────────────────────

  it('new shapes appear at their exact position (no lerp on first frame)', () => {
    service.applyFrame(makeCubeFrame('snap', {center: [10, 20, 30]}));

    const group = scene.children.find((c) => c instanceof THREE.Group) as THREE.Group;
    const mesh = group?.children.find(
      (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
    ) as THREE.LineSegments | THREE.Mesh | undefined;

    expect(mesh).toBeDefined();
    expect(mesh!.position.x).toBeCloseTo(10);
    expect(mesh!.position.y).toBeCloseTo(20);
    expect(mesh!.position.z).toBeCloseTo(30);
  });

  // ── Cube position lerps toward target ─────────────────────────────────────

  it('cube position lerps toward target over multiple frames (does not snap)', () => {
    // Start at origin
    service.applyFrame(makeCubeFrame('lerp_cube', {center: [0, 0, 0]}));

    // Move target to [10, 0, 0]
    clock.now += 16;
    service.applyFrame(makeCubeFrame('lerp_cube', {center: [10, 0, 0]}));

    const group = scene.children.find((c) => c instanceof THREE.Group) as THREE.Group;
    const mesh = group?.children.find(
      (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
    ) as THREE.LineSegments | THREE.Mesh | undefined;

    expect(mesh).toBeDefined();
    // After one lerp step from 0 → 10: expected = 0 + (10 - 0) * 0.3 = 3
    expect(mesh!.position.x).toBeCloseTo(3, 5);
    // NOT at target (10) — that would be snapping
    expect(mesh!.position.x).toBeLessThan(10);
  });

  it('cube position converges to target within epsilon after enough frames', () => {
    service.applyFrame(makeCubeFrame('converge', {center: [0, 0, 0]}));

    // Drive 50 frames toward [10, 0, 0]
    for (let i = 0; i < 50; i++) {
      clock.now += 16;
      service.applyFrame(makeCubeFrame('converge', {center: [10, 0, 0]}));
    }

    const group = scene.children.find((c) => c instanceof THREE.Group) as THREE.Group;
    const mesh = group?.children.find(
      (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
    ) as THREE.LineSegments | THREE.Mesh | undefined;

    expect(mesh).toBeDefined();
    expect(mesh!.position.x).toBeCloseTo(10, 3);
  });

  it('each lerp step moves position closer to target by the expected alpha factor', () => {
    service.applyFrame(makeCubeFrame('alpha_check', {center: [0, 0, 0]}));

    const getX = (): number => {
      const group = scene.children.find((c) => c instanceof THREE.Group) as THREE.Group;
      const mesh = group?.children.find(
        (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
      ) as THREE.LineSegments | THREE.Mesh;
      return mesh.position.x;
    };

    // Move target to [100, 0, 0] and apply one frame
    clock.now += 16;
    service.applyFrame(makeCubeFrame('alpha_check', {center: [100, 0, 0]}));
    const afterFrame1 = getX();

    // Apply a second frame (target unchanged)
    clock.now += 16;
    service.applyFrame(makeCubeFrame('alpha_check', {center: [100, 0, 0]}));
    const afterFrame2 = getX();

    // Frame 1: 0 + (100 - 0) * ALPHA = 100 * ALPHA
    expect(afterFrame1).toBeCloseTo(100 * SHAPE_LERP_ALPHA, 5);
    // Frame 2: afterFrame1 + (100 - afterFrame1) * ALPHA
    const expectedFrame2 = afterFrame1 + (100 - afterFrame1) * SHAPE_LERP_ALPHA;
    expect(afterFrame2).toBeCloseTo(expectedFrame2, 5);
  });

  // ── Color changes apply immediately ───────────────────────────────────────

  it('color changes apply immediately without lerp', () => {
    service.applyFrame(makeCubeFrame('color_snap', {color: '#ff0000'}));

    clock.now += 16;
    service.applyFrame(makeCubeFrame('color_snap', {color: '#00ff00'}));

    const group = scene.children.find((c) => c instanceof THREE.Group) as THREE.Group;
    const mesh = group?.children.find(
      (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
    ) as THREE.LineSegments | THREE.Mesh | undefined;

    expect(mesh).toBeDefined();
    const mat = mesh!.material as THREE.LineBasicMaterial | THREE.MeshBasicMaterial;
    // Green = 0x00ff00 → r=0, g=1, b=0
    expect((mat as any).color.r).toBeCloseTo(0, 5);
    expect((mat as any).color.g).toBeCloseTo(1, 5);
    expect((mat as any).color.b).toBeCloseTo(0, 5);
  });

  // ── Plane center lerps ─────────────────────────────────────────────────────

  it('plane center lerps toward target', () => {
    service.applyFrame(makePlaneFrame('lerp_plane'));

    clock.now += 16;
    service.applyFrame({
      timestamp: 2.0,
      shapes: [
        {
          id: 'lerp_plane',
          node_name: 'test',
          type: 'plane',
          center: [10, 0, 0],
          normal: [0, 0, 1],
          width: 5,
          height: 5,
          color: '#0000ff',
          opacity: 0.3,
        },
      ],
    });

    const group = scene.children.find((c) => c instanceof THREE.Group) as THREE.Group;
    const mesh = group?.children.find((c) => c instanceof THREE.Mesh) as THREE.Mesh | undefined;

    expect(mesh).toBeDefined();
    // One lerp step: 0 + (10 - 0) * 0.3 = 3
    expect(mesh!.position.x).toBeCloseTo(3, 5);
  });

  // ── Label position lerps, text snaps ──────────────────────────────────────

  it('label position lerps toward target when text is unchanged', () => {
    service.applyFrame(makeLabelFrame('lerp_label'));

    clock.now += 16;
    service.applyFrame({
      timestamp: 2.0,
      shapes: [
        {
          id: 'lerp_label',
          node_name: 'test',
          type: 'label',
          position: [10, 20, 30],
          text: 'Hello',
          font_size: 14,
          color: '#ffffff',
          background_color: '#000000cc',
          scale: 1.0,
        },
      ],
    });

    const sprite = scene.children.find((c) => c instanceof THREE.Sprite) as
      | THREE.Sprite
      | undefined;

    expect(sprite).toBeDefined();
    // Original position was [1, 2, 3]; target is [10, 20, 30]
    // One lerp: 1 + (10 - 1) * 0.3 = 1 + 2.7 = 3.7
    expect(sprite!.position.x).toBeCloseTo(1 + (10 - 1) * SHAPE_LERP_ALPHA, 5);
    expect(sprite!.position.y).toBeCloseTo(2 + (20 - 2) * SHAPE_LERP_ALPHA, 5);
  });

  it('label position snaps immediately when text changes', () => {
    service.applyFrame(makeLabelFrame('text_snap'));

    clock.now += 16;
    service.applyFrame({
      timestamp: 2.0,
      shapes: [
        {
          id: 'text_snap',
          node_name: 'test',
          type: 'label',
          position: [50, 50, 50],
          text: 'Changed!',
          font_size: 14,
          color: '#ffffff',
          background_color: '#000000cc',
          scale: 1.0,
        },
      ],
    });

    const sprite = scene.children.find((c) => c instanceof THREE.Sprite) as
      | THREE.Sprite
      | undefined;

    expect(sprite).toBeDefined();
    // Text changed → position should snap to target
    expect(sprite!.position.x).toBeCloseTo(50, 5);
    expect(sprite!.position.y).toBeCloseTo(50, 5);
    expect(sprite!.position.z).toBeCloseTo(50, 5);
  });

  // ── Lerp continues during decay (shape keeps gliding) ────────────────────

  it('lerp continues across frames where the shape is absent (decaying)', () => {
    service.applyFrame(makeCubeFrame('decay_lerp', {center: [0, 0, 0]}));

    // Move target
    clock.now += 16;
    service.applyFrame(makeCubeFrame('decay_lerp', {center: [100, 0, 0]}));

    const getX = (): number => {
      const group = scene.children.find((c) => c instanceof THREE.Group) as THREE.Group;
      const mesh = group?.children.find(
        (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
      ) as THREE.LineSegments | THREE.Mesh;
      return mesh.position.x;
    };

    const xAfterUpdate = getX();

    // Send empty frame (shape starts decaying) — lerp still runs
    clock.now += 16;
    service.applyFrame(EMPTY_FRAME);
    const xAfterDecayFrame = getX();

    // Shape should have moved further toward 100 even during decay
    expect(xAfterDecayFrame).toBeGreaterThan(xAfterUpdate);
  });
});

// ── Split-view isolation tests ────────────────────────────────────────────────

describe('ShapeLayerService — split-view isolation', () => {
  let serviceA: ShapeLayerService;
  let serviceB: ShapeLayerService;
  let sceneA: THREE.Scene;
  let sceneB: THREE.Scene;
  let clock: {now: number};

  beforeEach(() => {
    clock = {now: 1000};
    serviceA = makeService();
    serviceB = makeService();
    serviceA.now = () => clock.now;
    serviceB.now = () => clock.now;
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
    serviceB.applyFrame(makeCubeFrame('cube1'));

    expect(serviceA.shapeCount).toBe(2);
    expect(serviceB.shapeCount).toBe(1);
  });

  it('both panes receive identical shapes when fed the same frame', () => {
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

    expect(serviceA.shapeCount).toBe(2);
    expect(serviceB.shapeCount).toBe(2);
  });

  it('scene.add is called exactly once per pane per shape id', () => {
    const addSpyA = vi.spyOn(sceneA, 'add');
    const addSpyB = vi.spyOn(sceneB, 'add');
    const frame = makeCubeFrame('dup_test');

    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);
    expect(addSpyA).toHaveBeenCalledTimes(1);
    expect(addSpyB).toHaveBeenCalledTimes(1);
    addSpyA.mockClear();
    addSpyB.mockClear();

    for (let i = 0; i < 5; i++) {
      serviceA.applyFrame(frame);
      serviceB.applyFrame(frame);
    }
    expect(addSpyA).not.toHaveBeenCalled();
    expect(addSpyB).not.toHaveBeenCalled();
  });

  it('objects in sceneA and sceneB are distinct Three.js instances', () => {
    const frame = makeCubeFrame('iso_cube');
    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);

    const objA = sceneA.children.find((c) => c instanceof THREE.Group);
    const objB = sceneB.children.find((c) => c instanceof THREE.Group);

    expect(objA).toBeDefined();
    expect(objB).toBeDefined();
    expect(objA).not.toBe(objB);
  });

  it('disposeAll on pane A does NOT remove objects from pane B', () => {
    const frame = makeCubeFrame('survivor');
    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);

    const removeSpyB = vi.spyOn(sceneB, 'remove');
    serviceA.disposeAll();

    expect(serviceA.shapeCount).toBe(0);
    expect(serviceB.shapeCount).toBe(1);
    expect(removeSpyB).not.toHaveBeenCalled();
  });

  it('stale shape removal in pane A (after decay) does not affect pane B', () => {
    const frame = makeCubeFrame('stale_test');
    serviceA.applyFrame(frame);
    serviceB.applyFrame(frame);

    // Pane A stops receiving shapes, pane B keeps getting them
    clock.now += SHAPE_DECAY_MS + 1;
    serviceA.applyFrame(EMPTY_FRAME);
    serviceB.applyFrame(frame); // pane B still active

    expect(serviceA.shapeCount).toBe(0);
    expect(serviceB.shapeCount).toBe(1);
  });

  it('removing a pane and remounting (scene swap) cleans up the old scene', () => {
    serviceA.applyFrame(makeCubeFrame('remount_cube'));
    expect(sceneA.children.length).toBeGreaterThan(0);

    const sceneANew = new THREE.Scene();
    const removeSpyOld = vi.spyOn(sceneA, 'remove');

    serviceA.init(sceneANew);

    expect(removeSpyOld).toHaveBeenCalled();
    expect(serviceA.shapeCount).toBe(0);
    expect(sceneANew.children.length).toBe(0);

    serviceA.disposeAll();
  });

  it('four-pane scenario: all panes independently track the same shape set', () => {
    const serviceC = makeService();
    const serviceD = makeService();
    serviceC.now = () => clock.now;
    serviceD.now = () => clock.now;
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

    expect(serviceA.shapeCount).toBe(3);
    expect(serviceB.shapeCount).toBe(3);
    expect(serviceC.shapeCount).toBe(3);
    expect(serviceD.shapeCount).toBe(3);

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
