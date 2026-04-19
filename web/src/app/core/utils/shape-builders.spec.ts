import * as THREE from 'three';
import {vi, describe, it, expect} from 'vitest';
import {ShapeBuilders} from './shape-builders';
import {CubeDescriptor, LabelDescriptor, PlaneDescriptor} from '@core/models/shapes.model';

const BASE = {id: 'test', node_name: 'n'};

const CUBE: CubeDescriptor = {
  ...BASE,
  type: 'cube',
  center: [1, 2, 3],
  size: [0.8, 0.6, 1.2],
  rotation: [0, 0, 0],
  color: '#00ff00',
  opacity: 0.4,
  wireframe: true,
  label: null,
};

const CUBE_SOLID: CubeDescriptor = {...CUBE, wireframe: false, label: 'Thing'};

const PLANE: PlaneDescriptor = {
  ...BASE,
  type: 'plane',
  center: [0, 0, 0],
  normal: [0, 0, 1],
  width: 10,
  height: 5,
  color: '#4488ff',
  opacity: 0.25,
};

const LABEL: LabelDescriptor = {
  ...BASE,
  type: 'label',
  position: [1, 2, 3],
  text: 'Test Label',
  font_size: 14,
  color: '#ffffff',
  background_color: '#000000cc',
  scale: 1.0,
};

describe('ShapeBuilders', () => {
  describe('buildCube', () => {
    it('should return a THREE.Group', () => {
      const g = ShapeBuilders.buildCube(CUBE);
      expect(g).toBeInstanceOf(THREE.Group);
    });

    it('should set the INNER MESH position to cube center (not the group)', () => {
      const g = ShapeBuilders.buildCube(CUBE);
      // outerGroup is a pure rotation pivot — position stays at origin
      expect(g.position.x).toBeCloseTo(0);
      expect(g.position.y).toBeCloseTo(0);
      expect(g.position.z).toBeCloseTo(0);
      // The inner mesh carries the LiDAR-space position
      const mesh = g.children.find(
        (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
      )!;
      expect(mesh.position.x).toBeCloseTo(1);
      expect(mesh.position.y).toBeCloseTo(2);
      expect(mesh.position.z).toBeCloseTo(3);
    });

    it('wireframe=true should add a LineSegments child', () => {
      const g = ShapeBuilders.buildCube(CUBE);
      const lines = g.children.find((c) => c instanceof THREE.LineSegments);
      expect(lines).toBeTruthy();
    });

    it('wireframe=false should add a Mesh child', () => {
      const g = ShapeBuilders.buildCube(CUBE_SOLID);
      const mesh = g.children.find((c) => c instanceof THREE.Mesh);
      expect(mesh).toBeTruthy();
    });

    it('should add a label sprite when label is set', () => {
      const g = ShapeBuilders.buildCube(CUBE_SOLID);
      const sprite = g.children.find((c) => c instanceof THREE.Sprite);
      expect(sprite).toBeTruthy();
    });

    it('should apply LiDAR coordinate rotation', () => {
      const g = ShapeBuilders.buildCube(CUBE);
      expect(g.rotation.x).toBeCloseTo(-Math.PI / 2);
      expect(g.rotation.z).toBeCloseTo(-Math.PI / 2);
    });
  });

  describe('buildPlane', () => {
    it('should return a THREE.Group', () => {
      const g = ShapeBuilders.buildPlane(PLANE);
      expect(g).toBeInstanceOf(THREE.Group);
    });

    it('should contain a Mesh child', () => {
      const g = ShapeBuilders.buildPlane(PLANE);
      const mesh = g.children.find((c) => c instanceof THREE.Mesh);
      expect(mesh).toBeTruthy();
    });

    it('should set the INNER MESH position to plane center (outerGroup stays at origin)', () => {
      const g = ShapeBuilders.buildPlane(PLANE);
      // outerGroup is a pure rotation pivot
      expect(g.position.x).toBeCloseTo(0);
      expect(g.position.y).toBeCloseTo(0);
      expect(g.position.z).toBeCloseTo(0);
      // Inner mesh carries the LiDAR-space position
      const mesh = g.children.find((c) => c instanceof THREE.Mesh) as THREE.Mesh;
      expect(mesh.position.x).toBeCloseTo(0);
      expect(mesh.position.y).toBeCloseTo(0);
      expect(mesh.position.z).toBeCloseTo(0);
    });

    it('should apply LiDAR coordinate rotation', () => {
      const g = ShapeBuilders.buildPlane(PLANE);
      expect(g.rotation.x).toBeCloseTo(-Math.PI / 2);
      expect(g.rotation.z).toBeCloseTo(-Math.PI / 2);
    });

    it('should orient mesh for non-default normal', () => {
      const tilted = {...PLANE, normal: [0, 1, 0] as [number, number, number]};
      const g = ShapeBuilders.buildPlane(tilted);
      const mesh = g.children.find((c) => c instanceof THREE.Mesh) as THREE.Mesh;
      // Quaternion should not be identity
      const q = mesh.quaternion;
      const isIdentity = q.x === 0 && q.y === 0 && q.z === 0 && q.w === 1;
      expect(isIdentity).toBe(false);
    });
  });

  describe('buildLabel', () => {
    it('should return a THREE.Sprite', () => {
      const s = ShapeBuilders.buildLabel(LABEL);
      expect(s).toBeInstanceOf(THREE.Sprite);
    });

    it('should set the sprite position', () => {
      const s = ShapeBuilders.buildLabel(LABEL);
      expect(s.position.x).toBeCloseTo(1);
      expect(s.position.y).toBeCloseTo(2);
      expect(s.position.z).toBeCloseTo(3);
    });

    it('should create a SpriteMaterial with a CanvasTexture', () => {
      const s = ShapeBuilders.buildLabel(LABEL);
      expect((s.material as THREE.SpriteMaterial).map).toBeInstanceOf(THREE.CanvasTexture);
    });
  });

  describe('parseCssColorWithAlpha', () => {
    it('converts 8-digit hex to rgba()', () => {
      const result = ShapeBuilders.parseCssColorWithAlpha('#000000cc');
      expect(result).toContain('rgba(');
      expect(result).toContain('0.800'); // 0xCC / 255 ≈ 0.800
    });

    it('returns 6-digit hex unchanged', () => {
      expect(ShapeBuilders.parseCssColorWithAlpha('#ff0000')).toBe('#ff0000');
    });
  });

  describe('updateCube', () => {
    it('should mutate the INNER MESH position in-place (outerGroup stays at origin)', () => {
      const g = ShapeBuilders.buildCube(CUBE);
      const updated: CubeDescriptor = {...CUBE, center: [9, 8, 7]};
      ShapeBuilders.updateCube(g, updated);
      // outerGroup remains at world origin
      expect(g.position.x).toBeCloseTo(0);
      expect(g.position.y).toBeCloseTo(0);
      expect(g.position.z).toBeCloseTo(0);
      // Inner mesh should have the new center
      const mesh = g.children.find(
        (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
      )!;
      expect(mesh.position.x).toBeCloseTo(9);
      expect(mesh.position.y).toBeCloseTo(8);
      expect(mesh.position.z).toBeCloseTo(7);
    });
  });

  describe('updatePlane', () => {
    it('should mutate the INNER MESH position in-place (outerGroup stays at origin)', () => {
      const g = ShapeBuilders.buildPlane(PLANE);
      const updated: PlaneDescriptor = {...PLANE, center: [5, 5, 5]};
      ShapeBuilders.updatePlane(g, updated);
      // outerGroup remains at world origin
      expect(g.position.x).toBeCloseTo(0);
      // Inner mesh should have the new center
      const mesh = g.children.find((c) => c instanceof THREE.Mesh) as THREE.Mesh;
      expect(mesh.position.x).toBeCloseTo(5);
      expect(mesh.position.y).toBeCloseTo(5);
      expect(mesh.position.z).toBeCloseTo(5);
    });
  });

  describe('updateLabel', () => {
    it('should mutate the sprite position in-place', () => {
      const s = ShapeBuilders.buildLabel(LABEL);
      const updated: LabelDescriptor = {...LABEL, position: [9, 9, 9]};
      ShapeBuilders.updateLabel(s, updated);
      expect(s.position.x).toBeCloseTo(9);
    });

    it('should NOT replace the texture when label content is unchanged (no-flicker)', () => {
      const s = ShapeBuilders.buildLabel(LABEL);
      const originalTexture = (s.material as THREE.SpriteMaterial).map;

      // Calling updateLabel with identical content must not create a new texture.
      ShapeBuilders.updateLabel(s, {...LABEL});
      const textureAfter = (s.material as THREE.SpriteMaterial).map;

      expect(textureAfter).toBe(originalTexture);
    });

    it('should replace the texture only when label text changes', () => {
      const s = ShapeBuilders.buildLabel(LABEL);
      const originalTexture = (s.material as THREE.SpriteMaterial).map;

      ShapeBuilders.updateLabel(s, {...LABEL, text: 'Different text'});
      const textureAfter = (s.material as THREE.SpriteMaterial).map;

      expect(textureAfter).not.toBe(originalTexture);
    });

    it('should replace the texture when font_size changes', () => {
      const s = ShapeBuilders.buildLabel(LABEL);
      const originalTexture = (s.material as THREE.SpriteMaterial).map;

      ShapeBuilders.updateLabel(s, {...LABEL, font_size: 24});
      // font_size is part of the fingerprint → new texture expected
      expect((s.material as THREE.SpriteMaterial).map).not.toBe(originalTexture);
    });

    it('should NOT replace the texture when only position changes', () => {
      const s = ShapeBuilders.buildLabel(LABEL);
      const originalTexture = (s.material as THREE.SpriteMaterial).map;

      // position change must update sprite.position but NOT re-bake canvas
      ShapeBuilders.updateLabel(s, {...LABEL, position: [5, 5, 5]});
      expect((s.material as THREE.SpriteMaterial).map).toBe(originalTexture);
      expect(s.position.x).toBeCloseTo(5);
    });
  });

  describe('buildCube — embedded label deduplication', () => {
    it('should embed exactly ONE sprite child when label is provided', () => {
      const cubeWithLabel: CubeDescriptor = {...CUBE, wireframe: false, label: 'Box A'};
      const g = ShapeBuilders.buildCube(cubeWithLabel);
      const sprites = g.children.filter((c) => c instanceof THREE.Sprite);
      expect(sprites).toHaveLength(1);
    });

    it('should embed ZERO sprite children when label is null', () => {
      const g = ShapeBuilders.buildCube(CUBE); // CUBE has label: null
      const sprites = g.children.filter((c) => c instanceof THREE.Sprite);
      expect(sprites).toHaveLength(0);
    });

    it('embedded sprite should have non-zero scale', () => {
      const cubeWithLabel: CubeDescriptor = {...CUBE, wireframe: false, label: 'Box B'};
      const g = ShapeBuilders.buildCube(cubeWithLabel);
      const sprite = g.children.find((c) => c instanceof THREE.Sprite) as THREE.Sprite;
      expect(sprite.scale.x).toBeGreaterThan(0);
      expect(sprite.scale.y).toBeGreaterThan(0);
    });

    it('embedded sprite Z offset should be above box top face (center.z + size.z/2)', () => {
      const cubeWithLabel: CubeDescriptor = {
        ...CUBE,
        wireframe: false,
        label: 'Test',
        center: [0, 0, 2],
        size: [1, 1, 2],
      };
      const g = ShapeBuilders.buildCube(cubeWithLabel);
      const sprite = g.children.find((c) => c instanceof THREE.Sprite) as THREE.Sprite;
      // Expected Z = center[2] + size[2]/2 + 0.5 = 2 + 1 + 0.5 = 3.5
      expect(sprite.position.z).toBeGreaterThan(2 + 1); // above box top
    });
  });
});

