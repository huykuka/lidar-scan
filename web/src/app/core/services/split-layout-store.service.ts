import { computed, effect, Injectable } from '@angular/core';
import { SignalsSimpleStoreService } from './signals-simple-store.service';

// ── Public Type Exports (API Spec §2.1) ───────────────────────────────────────

export type ViewOrientation = 'perspective' | 'top' | 'front' | 'side';
export type SplitAxis = 'horizontal' | 'vertical';
export type LayoutMode = 'single' | 'h-split' | 'v-split' | '4-grid' | '1+2';

export interface ViewPane {
  /** Stable UUID generated at pane creation time */
  id: string;
  /** Camera/scene orientation for this pane */
  orientation: ViewOrientation;
  /**
   * Fractional size within its split group (0–1).
   * Sum of all pane fractions in a group must equal 1.0.
   */
  sizeFraction: number;
}

export interface SplitGroup {
  /** Direction of the flexbox split */
  axis: SplitAxis;
  /** Ordered array of panes in this group (left→right or top→bottom) */
  panes: ViewPane[];
}

export interface SplitLayoutState {
  /** V1: exactly one group at the top level (no nested splits) */
  groups: SplitGroup[];
  /** ID of the currently keyboard-focused pane, or null */
  focusedPaneId: string | null;
  /** Denormalised count of all active panes (1–4) */
  paneCount: number;
  /** Prevents rapid add/remove operations during transitions */
  isTransitioning: boolean;
  /** Active layout preset — drives rendering strategy in SplitPaneContainerComponent */
  layoutMode: LayoutMode;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const VALID_ORIENTATIONS: ReadonlySet<ViewOrientation> = new Set([
  'perspective', 'top', 'front', 'side',
]);

const STORAGE_KEY = 'lidar_split_layout_v1';

/** Exported for use in tests and mocks */
export const DEFAULT_SPLIT_LAYOUT: SplitLayoutState = {
  groups: [{
    axis: 'horizontal',
    panes: [{ id: 'default-pane', orientation: 'perspective', sizeFraction: 1 }],
  }],
  focusedPaneId: null,
  paneCount: 1,
  isTransitioning: false,
  layoutMode: 'single',
};

// ── Service ───────────────────────────────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class SplitLayoutStoreService extends SignalsSimpleStoreService<SplitLayoutState> {
  readonly MAX_PANES = 4;
  /** Minimum pane dimension in pixels */
  readonly MIN_PX = 200;

  // ── Signal selectors ─────────────────────────────────────────────────────
  groups          = this.select('groups');
  focusedPaneId   = this.select('focusedPaneId');
  paneCount       = this.select('paneCount');
  isTransitioning = this.select('isTransitioning');
  layoutMode      = this.select('layoutMode');

  // ── Computed signals ──────────────────────────────────────────────────────
  allPanes   = computed(() => this.groups().flatMap(g => g.panes));
  canAddPane = computed(() => this.paneCount() < this.MAX_PANES);

  /**
   * In '1+2' mode the outer horizontal split fraction is driven by the single
   * pane in groups[0]. This computed exposes [leftFrac, rightFrac] for the
   * container to apply as flex values on the two column wrappers.
   */
  oneTwoColumnFractions = computed<[number, number]>(() => {
    const gs = this.groups();
    if (this.layoutMode() !== '1+2' || gs.length < 2) return [0.5, 0.5];
    const leftFrac = gs[0].panes[0]?.sizeFraction ?? 0.5;
    return [leftFrac, 1 - leftFrac];
  });

  constructor() {
    super();
    this.loadFromStorage();

    // Persist every state change to localStorage
    effect(() => {
      this.saveToStorage(this.state());
    });
  }

  // ── Public Mutators ───────────────────────────────────────────────────────

  /**
   * Add a new pane by splitting the largest existing pane in half.
   * ADR-1 §3.14
   */
  addPane(orientation: ViewOrientation): void {
    if (this.paneCount() >= this.MAX_PANES) return;
    if (this.isTransitioning()) return;

    const groups = this.groups();
    const group = groups[0]; // V1: single group
    if (!group) return;

    // Find the pane with the largest sizeFraction
    const largestPane = [...group.panes].sort((a, b) => b.sizeFraction - a.sizeFraction)[0];
    const halfFraction = largestPane.sizeFraction / 2;

    const newPane: ViewPane = {
      id: crypto.randomUUID(),
      orientation,
      sizeFraction: halfFraction,
    };

    // Replace largest pane with two halves
    const updatedPanes = group.panes.map(p =>
      p.id === largestPane.id ? { ...p, sizeFraction: halfFraction } : p,
    );

    // Insert new pane after the split pane
    const splitIndex = updatedPanes.findIndex(p => p.id === largestPane.id);
    updatedPanes.splice(splitIndex + 1, 0, newPane);

    const newCount = this.paneCount() + 1;

    this.setState({
      groups: [{ ...group, panes: updatedPanes }],
      paneCount: newCount,
      isTransitioning: true,
    });

    setTimeout(() => this.set('isTransitioning', false), 300);
  }

  /**
   * Remove a pane and redistribute its fraction to remaining panes.
   * ADR-1 §3.15
   */
  removePane(paneId: string): void {
    if (this.paneCount() <= 1) return;

    const groups = this.groups();
    const group = groups[0];
    if (!group) return;

    const paneIndex = group.panes.findIndex(p => p.id === paneId);
    if (paneIndex === -1) return;

    const removedFraction = group.panes[paneIndex].sizeFraction;
    const remaining = group.panes.filter(p => p.id !== paneId);
    const sumRemaining = remaining.reduce((s, p) => s + p.sizeFraction, 0);

    // Proportionally redistribute the removed fraction
    const redistributed = remaining.map(p => ({
      ...p,
      sizeFraction: p.sizeFraction + removedFraction * (p.sizeFraction / sumRemaining),
    }));

    const newCount = this.paneCount() - 1;

    this.setState({
      groups: [{
        ...group,
        panes: redistributed,
        // Reset axis to neutral when only 1 pane remains
        axis: newCount === 1 ? 'horizontal' : group.axis,
      }],
      paneCount: newCount,
      isTransitioning: true,
    });

    setTimeout(() => this.set('isTransitioning', false), 300);
  }

  /** Update the orientation of a single pane. */
  setPaneOrientation(paneId: string, orientation: ViewOrientation): void {
    const groups = this.groups();
    const updatedGroups = groups.map(group => ({
      ...group,
      panes: group.panes.map(p => p.id === paneId ? { ...p, orientation } : p),
    }));
    this.setState({ groups: updatedGroups });
  }

  /**
   * Resize a pane by updating its sizeFraction.
   * The adjacent next-pane absorbs the delta.
   * Enforces MIN_PX on both sides.
   */
  resizePane(paneId: string, newFraction: number, containerPx: number): void {
    const groups = this.groups();

    // Find which group contains this pane
    let targetGroupIdx = groups.findIndex(g => g.panes.some(p => p.id === paneId));

    // In '1+2' mode the outer column divider is keyed to groups[0]'s pane —
    // treat it as a special outer-column resize.
    if (this.layoutMode() === '1+2' && targetGroupIdx === 0) {
      this.resizeOneTwoColumns(newFraction, containerPx);
      return;
    }

    if (targetGroupIdx === -1) targetGroupIdx = 0;
    const group = groups[targetGroupIdx];
    if (!group) return;

    const idx = group.panes.findIndex(p => p.id === paneId);
    if (idx === -1 || idx === group.panes.length - 1) return;

    const minFraction = this.MIN_PX / containerPx;

    // Total size budget for these two panes
    const budget = group.panes[idx].sizeFraction + group.panes[idx + 1].sizeFraction;

    // Clamp target pane: must leave at least minFraction for the adjacent pane
    const maxTarget = budget - minFraction;
    const clamped = Math.max(minFraction, Math.min(maxTarget, newFraction));

    // Round to 10 decimal places to avoid floating-point epsilon drift
    const round10 = (n: number) => Math.round(n * 1e10) / 1e10;
    const finalClamped = round10(clamped);
    const adjacentFraction = round10(budget - finalClamped);

    const updatedPanes = group.panes.map((p, i) => {
      if (i === idx) return { ...p, sizeFraction: finalClamped };
      if (i === idx + 1) return { ...p, sizeFraction: adjacentFraction };
      return p;
    });

    // Preserve all groups — only update the target group
    const updatedGroups = groups.map((g, i) =>
      i === targetGroupIdx ? { ...g, panes: updatedPanes } : g,
    );

    this.setState({ groups: updatedGroups });
  }

  /** Set keyboard-navigation focus to a pane (or clear with null). */
  setFocusedPane(paneId: string | null): void {
    this.set('focusedPaneId', paneId);
  }

  /**
   * In '1+2' mode: resize the outer left/right column split.
   * newLeftFrac is the desired fraction for the left column.
   */
  resizeOneTwoColumns(newLeftFrac: number, containerPx: number): void {
    const groups = this.groups();
    if (this.layoutMode() !== '1+2' || groups.length < 2) return;

    const minFraction = this.MIN_PX / containerPx;
    const clamped = Math.max(minFraction, Math.min(1 - minFraction, newLeftFrac));
    const round10 = (n: number) => Math.round(n * 1e10) / 1e10;

    const updatedGroups = [
      { ...groups[0], panes: [{ ...groups[0].panes[0], sizeFraction: round10(clamped) }] },
      groups[1],
    ];
    this.setState({ groups: updatedGroups });
  }

  /** Restore the default single-perspective-pane layout. */
  resetToDefault(): void {
    this.setState(this.getDefaultState());
  }

  /** Set a horizontal 2-split (top/bottom): top pane perspective, bottom pane top-view. */
  setHorizontalSplit(): void {
    this.setState({
      groups: [{
        axis: 'horizontal',
        panes: [
          { id: crypto.randomUUID(), orientation: 'perspective', sizeFraction: 0.5 },
          { id: crypto.randomUUID(), orientation: 'top',         sizeFraction: 0.5 },
        ],
      }],
      focusedPaneId: null,
      paneCount: 2,
      isTransitioning: false,
      layoutMode: 'h-split',
    });
  }

  /** Set a vertical 2-split (left/right): left pane perspective, right pane front-view. */
  setVerticalSplit(): void {
    this.setState({
      groups: [{
        axis: 'vertical',
        panes: [
          { id: crypto.randomUUID(), orientation: 'perspective', sizeFraction: 0.5 },
          { id: crypto.randomUUID(), orientation: 'front',       sizeFraction: 0.5 },
        ],
      }],
      focusedPaneId: null,
      paneCount: 2,
      isTransitioning: false,
      layoutMode: 'v-split',
    });
  }

  /** Set a 4-pane grid (2×2): perspective (TL), top (TR), front (BL), side (BR). */
  setFourPaneGrid(): void {
    this.setState({
      groups: [{
        axis: 'vertical',
        panes: [
          { id: crypto.randomUUID(), orientation: 'perspective', sizeFraction: 0.25 },
          { id: crypto.randomUUID(), orientation: 'top',         sizeFraction: 0.25 },
          { id: crypto.randomUUID(), orientation: 'front',       sizeFraction: 0.25 },
          { id: crypto.randomUUID(), orientation: 'side',        sizeFraction: 0.25 },
        ],
      }],
      focusedPaneId: null,
      paneCount: 4,
      isTransitioning: false,
      layoutMode: '4-grid',
    });
  }

  /**
   * Set a 1+2 layout: left half = perspective, right half = top (upper) + front (lower).
   * Groups[0] = left pane (horizontal axis, sizeFraction 0.5).
   * Groups[1] = right column with two vertical panes (each 0.5 within that column).
   * The outer container renders groups side-by-side.
   */
  setSplitOneTwo(): void {
    this.setState({
      groups: [
        {
          axis: 'horizontal',
          panes: [{ id: crypto.randomUUID(), orientation: 'perspective', sizeFraction: 0.5 }],
        },
        {
          axis: 'vertical',
          panes: [
            { id: crypto.randomUUID(), orientation: 'top',   sizeFraction: 0.5 },
            { id: crypto.randomUUID(), orientation: 'front', sizeFraction: 0.5 },
          ],
        },
      ],
      focusedPaneId: null,
      paneCount: 3,
      isTransitioning: false,
      layoutMode: '1+2',
    });
  }

  // ── Private Helpers ───────────────────────────────────────────────────────

  private loadFromStorage(): void {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      this.setState(this.getDefaultState());
      return;
    }

    try {
      const parsed: SplitLayoutState = JSON.parse(raw);
      const validated = this.validateAndSanitise(parsed);
      if (!validated) {
        localStorage.removeItem(STORAGE_KEY);
        console.warn('[SplitLayoutStore] Invalid layout data cleared from localStorage.');
        this.setState(this.getDefaultState());
      } else {
        this.setState(validated);
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
      console.warn('[SplitLayoutStore] Corrupt layout data cleared from localStorage.');
      this.setState(this.getDefaultState());
    }
  }

  private saveToStorage(state: SplitLayoutState): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      console.warn('[SplitLayoutStore] Failed to persist layout to localStorage:', e);
    }
  }

  private validateAndSanitise(state: SplitLayoutState): SplitLayoutState | null {
    if (!state || !Array.isArray(state.groups) || state.groups.length === 0) return null;
    if (typeof state.paneCount !== 'number' || state.paneCount < 1 || state.paneCount > 4) return null;

    // Sanitise each group's panes
    const sanitisedGroups = state.groups.map(group => {
      const sanitisedPanes = group.panes.map(pane => ({
        ...pane,
        orientation: VALID_ORIENTATIONS.has(pane.orientation) ? pane.orientation : 'perspective' as ViewOrientation,
      }));

      // Check if any fractions are out of range → normalise to equal distribution
      const hasInvalidFraction = sanitisedPanes.some(
        p => typeof p.sizeFraction !== 'number' || p.sizeFraction < 0 || p.sizeFraction > 1,
      );

      if (hasInvalidFraction) {
        const equalFraction = 1 / sanitisedPanes.length;
        return {
          ...group,
          panes: sanitisedPanes.map(p => ({ ...p, sizeFraction: equalFraction })),
        };
      }

      return { ...group, panes: sanitisedPanes };
    });

    const VALID_MODES: ReadonlySet<string> = new Set(['single', 'h-split', 'v-split', '4-grid', '1+2']);

    return {
      ...state,
      groups: sanitisedGroups,
      isTransitioning: false,
      layoutMode: VALID_MODES.has(state.layoutMode) ? state.layoutMode : 'single',
    };
  }

  private getDefaultState(): SplitLayoutState {
    return {
      groups: [{
        axis: 'horizontal',
        panes: [{ id: crypto.randomUUID(), orientation: 'perspective', sizeFraction: 1 }],
      }],
      focusedPaneId: null,
      paneCount: 1,
      isTransitioning: false,
      layoutMode: 'single',
    };
  }
}
