// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import {
  SplitLayoutStoreService,
  DEFAULT_SPLIT_LAYOUT,
  SplitLayoutState,
  ViewOrientation,
} from './split-layout-store.service';

describe('SplitLayoutStoreService', () => {
  let service: SplitLayoutStoreService;

  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    TestBed.configureTestingModule({});
    service = TestBed.inject(SplitLayoutStoreService);
  });

  afterEach(() => {
    vi.useRealTimers();
    localStorage.clear();
    TestBed.resetTestingModule();
  });

  // ── Initial State ──────────────────────────────────────────────────────────

  describe('initial state', () => {
    it('should be created', () => {
      expect(service).toBeTruthy();
    });

    it('should start with a single perspective pane (default state)', () => {
      expect(service.paneCount()).toBe(1);
      expect(service.allPanes().length).toBe(1);
      expect(service.allPanes()[0].orientation).toBe('perspective');
    });

    it('should expose canAddPane = true initially', () => {
      expect(service.canAddPane()).toBe(true);
    });

    it('should have focusedPaneId = null initially', () => {
      expect(service.focusedPaneId()).toBeNull();
    });

    it('DEFAULT_SPLIT_LAYOUT should have 1 pane with perspective orientation', () => {
      expect(DEFAULT_SPLIT_LAYOUT.paneCount).toBe(1);
      expect(DEFAULT_SPLIT_LAYOUT.groups[0].panes[0].orientation).toBe('perspective');
    });
  });

  // ── addPane ────────────────────────────────────────────────────────────────

  describe('addPane()', () => {
    it('should increase paneCount by 1', () => {
      service.addPane('top');
      expect(service.paneCount()).toBe(2);
    });

    it('should add the pane with the specified orientation', () => {
      service.addPane('front');
      const newPane = service.allPanes().find(p => p.orientation === 'front');
      expect(newPane).toBeDefined();
    });

    it('should keep fractions summing to 1.0 after adding a pane', () => {
      service.addPane('top');
      const fractions = service.groups()[0].panes.reduce((sum, p) => sum + p.sizeFraction, 0);
      expect(fractions).toBeCloseTo(1.0, 5);
    });

    it('should keep fractions summing to 1.0 after adding 3 panes', () => {
      service.addPane('top');
      vi.runAllTimers(); // clear isTransitioning debounce
      service.addPane('front');
      vi.runAllTimers();
      service.addPane('side');
      const fractions = service.groups()[0].panes.reduce((sum, p) => sum + p.sizeFraction, 0);
      expect(fractions).toBeCloseTo(1.0, 5);
    });

    it('should set canAddPane to false when 4 panes exist', () => {
      service.addPane('top');
      vi.runAllTimers();
      service.addPane('front');
      vi.runAllTimers();
      service.addPane('side');
      expect(service.canAddPane()).toBe(false);
    });

    it('should NOT add a 5th pane when MAX_PANES is reached', () => {
      service.addPane('top');
      vi.runAllTimers();
      service.addPane('front');
      vi.runAllTimers();
      service.addPane('side');
      vi.runAllTimers();
      service.addPane('perspective'); // 5th attempt
      expect(service.paneCount()).toBe(4);
    });

    it('should assign a unique id to each pane', () => {
      service.addPane('top');
      vi.runAllTimers();
      service.addPane('front');
      const ids = service.allPanes().map(p => p.id);
      const uniqueIds = new Set(ids);
      expect(uniqueIds.size).toBe(ids.length);
    });
  });

  // ── removePane ────────────────────────────────────────────────────────────

  describe('removePane()', () => {
    it('should decrease paneCount by 1', () => {
      service.addPane('top');
      const panes = service.allPanes();
      service.removePane(panes[1].id);
      expect(service.paneCount()).toBe(1);
    });

    it('should NOT remove the last pane', () => {
      const paneId = service.allPanes()[0].id;
      service.removePane(paneId);
      expect(service.paneCount()).toBe(1);
    });

    it('should redistribute fractions to sum to 1.0 after removal', () => {
      service.addPane('top');
      service.addPane('front');
      const paneToRemove = service.allPanes()[1].id;
      service.removePane(paneToRemove);
      const fractions = service.groups()[0].panes.reduce((sum, p) => sum + p.sizeFraction, 0);
      expect(fractions).toBeCloseTo(1.0, 5);
    });

    it('should be a no-op for a non-existent pane id', () => {
      service.removePane('nonexistent-id');
      expect(service.paneCount()).toBe(1);
    });

    it('should restore canAddPane after removing from 4 panes', () => {
      service.addPane('top');
      vi.runAllTimers();
      service.addPane('front');
      vi.runAllTimers();
      service.addPane('side');
      vi.runAllTimers();
      const idToRemove = service.allPanes()[3].id;
      service.removePane(idToRemove);
      expect(service.canAddPane()).toBe(true);
    });
  });

  // ── setPaneOrientation ────────────────────────────────────────────────────

  describe('setPaneOrientation()', () => {
    it('should update the orientation of a pane', () => {
      const paneId = service.allPanes()[0].id;
      service.setPaneOrientation(paneId, 'top');
      expect(service.allPanes()[0].orientation).toBe('top');
    });

    it('should not affect other panes', () => {
      service.addPane('front');
      const [p0, p1] = service.allPanes();
      service.setPaneOrientation(p0.id, 'side');
      expect(service.allPanes().find(p => p.id === p1.id)!.orientation).toBe('front');
    });

    it('should be a no-op for a non-existent pane id', () => {
      service.setPaneOrientation('bogus', 'top');
      expect(service.allPanes()[0].orientation).toBe('perspective');
    });
  });

  // ── resizePane ────────────────────────────────────────────────────────────

  describe('resizePane()', () => {
    beforeEach(() => {
      service.addPane('top'); // now 2 panes, each 0.5
    });

    it('should update the sizeFraction of the target pane', () => {
      const paneId = service.allPanes()[0].id;
      service.resizePane(paneId, 0.7, 1000);
      expect(service.allPanes()[0].sizeFraction).toBeCloseTo(0.7, 5);
    });

    it('should adjust adjacent pane so fractions still sum to 1.0', () => {
      const paneId = service.allPanes()[0].id;
      service.resizePane(paneId, 0.65, 1000);
      const fractions = service.groups()[0].panes.reduce((sum, p) => sum + p.sizeFraction, 0);
      expect(fractions).toBeCloseTo(1.0, 5);
    });

    it('should clamp fraction to enforce MIN_PX constraint on target pane', () => {
      // containerPx = 1000, MIN_PX = 200 → min fraction = 0.2
      const paneId = service.allPanes()[0].id;
      service.resizePane(paneId, 0.05, 1000); // tries to go below min
      expect(service.allPanes()[0].sizeFraction).toBeGreaterThanOrEqual(0.2);
    });

    it('should clamp fraction to enforce MIN_PX constraint on adjacent pane', () => {
      const paneId = service.allPanes()[0].id;
      service.resizePane(paneId, 0.95, 1000); // pane[1] would be 0.05 = 50px
      expect(service.allPanes()[1].sizeFraction).toBeGreaterThanOrEqual(0.2);
    });
  });

  // ── setFocusedPane ────────────────────────────────────────────────────────

  describe('setFocusedPane()', () => {
    it('should set the focused pane id', () => {
      const paneId = service.allPanes()[0].id;
      service.setFocusedPane(paneId);
      expect(service.focusedPaneId()).toBe(paneId);
    });

    it('should accept null to clear focus', () => {
      const paneId = service.allPanes()[0].id;
      service.setFocusedPane(paneId);
      service.setFocusedPane(null);
      expect(service.focusedPaneId()).toBeNull();
    });
  });

  // ── resetToDefault ────────────────────────────────────────────────────────

  describe('resetToDefault()', () => {
    it('should restore to a single perspective pane', () => {
      service.addPane('top');
      service.addPane('front');
      service.resetToDefault();
      expect(service.paneCount()).toBe(1);
      expect(service.allPanes()[0].orientation).toBe('perspective');
    });

    it('should clear focusedPaneId on reset', () => {
      const paneId = service.allPanes()[0].id;
      service.setFocusedPane(paneId);
      service.resetToDefault();
      expect(service.focusedPaneId()).toBeNull();
    });
  });

  // ── localStorage persistence ──────────────────────────────────────────────

  describe('localStorage persistence', () => {
    it('should save state to localStorage on change', () => {
      service.addPane('top');
      TestBed.flushEffects();
      const raw = localStorage.getItem('lidar_split_layout_v1');
      expect(raw).not.toBeNull();
      const saved: SplitLayoutState = JSON.parse(raw!);
      expect(saved.paneCount).toBe(2);
    });

    it('should restore state from localStorage on service init', () => {
      const state: SplitLayoutState = {
        groups: [{
          axis: 'horizontal',
          panes: [
            { id: 'a1', orientation: 'top', sizeFraction: 0.5 },
            { id: 'a2', orientation: 'front', sizeFraction: 0.5 },
          ]
        }],
        focusedPaneId: null,
        paneCount: 2,
        isTransitioning: false,
        layoutMode: 'h-split',
      };
      localStorage.setItem('lidar_split_layout_v1', JSON.stringify(state));

      TestBed.resetTestingModule();
      TestBed.configureTestingModule({});
      const fresh = TestBed.inject(SplitLayoutStoreService);

      expect(fresh.paneCount()).toBe(2);
      expect(fresh.allPanes()[0].orientation).toBe('top');
    });

    it('should fall back to default state if localStorage data is corrupt', () => {
      localStorage.setItem('lidar_split_layout_v1', 'NOT_JSON!@#');
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({});
      const fresh = TestBed.inject(SplitLayoutStoreService);

      expect(fresh.paneCount()).toBe(1);
      expect(fresh.allPanes()[0].orientation).toBe('perspective');
      expect(localStorage.getItem('lidar_split_layout_v1')).toBeNull();
    });

    it('should fall back to default state if paneCount > 4', () => {
      const invalid: SplitLayoutState = {
        groups: [{ axis: 'horizontal', panes: [] }],
        focusedPaneId: null,
        paneCount: 5,
        isTransitioning: false,
        layoutMode: 'single',
      };
      localStorage.setItem('lidar_split_layout_v1', JSON.stringify(invalid));
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({});
      const fresh = TestBed.inject(SplitLayoutStoreService);

      expect(fresh.paneCount()).toBe(1);
    });

    it('should normalize sizeFractions if any is out of range', () => {
      const badFraction: SplitLayoutState = {
        groups: [{
          axis: 'horizontal',
          panes: [
            { id: 'b1', orientation: 'perspective', sizeFraction: -0.5 },
            { id: 'b2', orientation: 'top', sizeFraction: 1.5 },
          ]
        }],
        focusedPaneId: null,
        paneCount: 2,
        isTransitioning: false,
        layoutMode: 'h-split',
      };
      localStorage.setItem('lidar_split_layout_v1', JSON.stringify(badFraction));
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({});
      const fresh = TestBed.inject(SplitLayoutStoreService);

      const panes = fresh.allPanes();
      panes.forEach(p => {
        expect(p.sizeFraction).toBeGreaterThan(0);
        expect(p.sizeFraction).toBeLessThanOrEqual(1);
      });
    });

    it('should reset invalid orientation to perspective', () => {
      const badOrientation: SplitLayoutState = {
        groups: [{
          axis: 'horizontal',
          panes: [{ id: 'c1', orientation: 'diagonal' as ViewOrientation, sizeFraction: 1 }]
        }],
        focusedPaneId: null,
        paneCount: 1,
        isTransitioning: false,
        layoutMode: 'single',
      };
      localStorage.setItem('lidar_split_layout_v1', JSON.stringify(badOrientation));
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({});
      const fresh = TestBed.inject(SplitLayoutStoreService);
      expect(fresh.allPanes()[0].orientation).toBe('perspective');
    });
  });

  // ── allPanes computed ─────────────────────────────────────────────────────

  describe('allPanes computed signal', () => {
    it('should be a flat array of panes across all groups', () => {
      service.addPane('top');
      expect(service.allPanes().length).toBe(service.paneCount());
    });
  });
});
