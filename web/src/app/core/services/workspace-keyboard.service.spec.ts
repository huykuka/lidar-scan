// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { WorkspaceKeyboardService } from './workspace-keyboard.service';
import { SplitLayoutStoreService } from './split-layout-store.service';
import { ToastService } from './toast.service';

function fireKeydown(key: string, ctrlKey = true): void {
  const event = new KeyboardEvent('keydown', { key, ctrlKey, bubbles: true });
  document.dispatchEvent(event);
}

describe('WorkspaceKeyboardService', () => {
  let service: WorkspaceKeyboardService;
  let mockLayout: any;
  let mockToast: any;

  beforeEach(() => {
    const canAdd = signal(true);
    const pCount = signal(1);
    const panes = signal([{ id: 'pane-1', orientation: 'perspective', sizeFraction: 1 }]);
    const focused = signal<string | null>(null);

    mockLayout = {
      canAddPane: canAdd,
      paneCount: pCount,
      allPanes: panes,
      focusedPaneId: focused,
      addPane: vi.fn(),
      removePane: vi.fn(),
      setFocusedPane: vi.fn(),
    };

    mockToast = {
      warning: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        WorkspaceKeyboardService,
        { provide: SplitLayoutStoreService, useValue: mockLayout },
        { provide: ToastService, useValue: mockToast },
      ],
    });

    service = TestBed.inject(WorkspaceKeyboardService);
  });

  afterEach(() => {
    service.ngOnDestroy();
    TestBed.resetTestingModule();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('Ctrl+T', () => {
    it('should call addPane("top") when canAddPane is true', () => {
      mockLayout.canAddPane.set(true);
      fireKeydown('t');
      expect(mockLayout.addPane).toHaveBeenCalledWith('top');
    });

    it('should show warning toast when canAddPane is false', () => {
      mockLayout.canAddPane.set(false);
      fireKeydown('t');
      expect(mockLayout.addPane).not.toHaveBeenCalled();
      expect(mockToast.warning).toHaveBeenCalledWith('Maximum 4 views reached');
    });
  });

  describe('Ctrl+F', () => {
    it('should call addPane("front") when canAddPane is true', () => {
      mockLayout.canAddPane.set(true);
      fireKeydown('f');
      expect(mockLayout.addPane).toHaveBeenCalledWith('front');
    });
  });

  describe('Ctrl+W', () => {
    it('should close focused pane when paneCount > 1', () => {
      mockLayout.paneCount.set(2);
      mockLayout.allPanes.set([
        { id: 'pane-1', orientation: 'perspective', sizeFraction: 0.5 },
        { id: 'pane-2', orientation: 'top', sizeFraction: 0.5 },
      ]);
      mockLayout.focusedPaneId.set('pane-1');
      fireKeydown('w');
      expect(mockLayout.removePane).toHaveBeenCalledWith('pane-1');
    });

    it('should NOT close pane when paneCount === 1', () => {
      mockLayout.paneCount.set(1);
      mockLayout.focusedPaneId.set('pane-1');
      fireKeydown('w');
      expect(mockLayout.removePane).not.toHaveBeenCalled();
    });

    it('should NOT close pane when no pane is focused', () => {
      mockLayout.paneCount.set(2);
      mockLayout.focusedPaneId.set(null);
      fireKeydown('w');
      expect(mockLayout.removePane).not.toHaveBeenCalled();
    });
  });

  describe('Ctrl+1..4 (focus pane by index)', () => {
    beforeEach(() => {
      mockLayout.allPanes.set([
        { id: 'p0', orientation: 'perspective', sizeFraction: 0.5 },
        { id: 'p1', orientation: 'top', sizeFraction: 0.5 },
      ]);
    });

    it('Ctrl+1 should focus pane at index 0', () => {
      fireKeydown('1');
      expect(mockLayout.setFocusedPane).toHaveBeenCalledWith('p0');
    });

    it('Ctrl+2 should focus pane at index 1', () => {
      fireKeydown('2');
      expect(mockLayout.setFocusedPane).toHaveBeenCalledWith('p1');
    });

    it('Ctrl+3 should be no-op when fewer than 3 panes exist', () => {
      fireKeydown('3');
      expect(mockLayout.setFocusedPane).not.toHaveBeenCalled();
    });
  });

  describe('non-Ctrl shortcuts', () => {
    it('should NOT react to "t" without Ctrl', () => {
      const event = new KeyboardEvent('keydown', { key: 't', ctrlKey: false, bubbles: true });
      document.dispatchEvent(event);
      expect(mockLayout.addPane).not.toHaveBeenCalled();
    });
  });

  describe('ngOnDestroy', () => {
    it('should deregister keydown listener on destroy', () => {
      service.ngOnDestroy();
      mockLayout.canAddPane.set(true);
      fireKeydown('t');
      // After destroy, the listener should not fire
      expect(mockLayout.addPane).not.toHaveBeenCalled();
    });
  });
});
