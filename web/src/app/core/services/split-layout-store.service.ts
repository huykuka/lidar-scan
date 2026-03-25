import { computed, effect, Injectable } from '@angular/core';
import { SignalsSimpleStoreService } from './signals-simple-store.service';

// ── Public Type Exports (API Spec §2.1) ───────────────────────────────────────

export type ViewOrientation = 'perspective' | 'top' | 'front' | 'side';
export type SplitAxis = 'horizontal' | 'vertical';

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

  // ── Computed signals ──────────────────────────────────────────────────────
  allPanes   = computed(() => this.groups().flatMap(g => g.panes));
  canAddPane = computed(() => this.paneCount() < this.MAX_PANES);

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
    const group = groups[0];
    if (!group) return;

    const paneIndex = group.panes.findIndex(p => p.id === paneId);
    if (paneIndex === -1) return;

    const updatedPanes = group.panes.map(p =>
      p.id === paneId ? { ...p, orientation } : p,
    );

    this.setState({ groups: [{ ...group, panes: updatedPanes }] });
  }

  /**
   * Resize a pane by updating its sizeFraction.
   * The adjacent next-pane absorbs the delta.
   * Enforces MIN_PX on both sides.
   */
  resizePane(paneId: string, newFraction: number, containerPx: number): void {
    const groups = this.groups();
    const group = groups[0];
    if (!group) return;

    const idx = group.panes.findIndex(p => p.id === paneId);
    if (idx === -1 || idx === group.panes.length - 1) return;

    const minFraction = this.MIN_PX / containerPx;
    const maxFraction = 1 - minFraction;

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

    this.setState({ groups: [{ ...group, panes: updatedPanes }] });
  }

  /** Set keyboard-navigation focus to a pane (or clear with null). */
  setFocusedPane(paneId: string | null): void {
    this.set('focusedPaneId', paneId);
  }

  /** Restore the default single-perspective-pane layout. */
  resetToDefault(): void {
    this.setState(this.getDefaultState());
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

    return {
      ...state,
      groups: sanitisedGroups,
      isTransitioning: false,
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
    };
  }
}
