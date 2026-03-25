import { inject, Injectable, OnDestroy } from '@angular/core';
import { SplitLayoutStoreService, ViewOrientation } from './split-layout-store.service';
import { ToastService } from './toast.service';

/**
 * Global keyboard shortcut handler for the split-view workspace.
 * Registered as a root-level singleton — inject it in WorkspacesComponent
 * constructor to activate it.
 *
 * Shortcuts (all require Ctrl):
 *   Ctrl+T        → Add Top view
 *   Ctrl+F        → Add Front view
 *   Ctrl+S        → Add Side view (canvas-focused only, avoids browser save)
 *   Ctrl+1–4      → Focus pane by index
 *   Ctrl+W        → Close focused pane (only if paneCount > 1)
 */
@Injectable({ providedIn: 'root' })
export class WorkspaceKeyboardService implements OnDestroy {
  private layout = inject(SplitLayoutStoreService);
  private toast  = inject(ToastService);

  private readonly listener = (e: KeyboardEvent) => this.handleKey(e);

  constructor() {
    document.addEventListener('keydown', this.listener);
  }

  ngOnDestroy(): void {
    document.removeEventListener('keydown', this.listener);
  }

  private handleKey(e: KeyboardEvent): void {
    if (!e.ctrlKey) return;

    switch (e.key) {
      case 't':
      case 'T':
        e.preventDefault();
        this.tryAdd('top');
        break;

      case 'f':
      case 'F':
        e.preventDefault();
        this.tryAdd('front');
        break;

      case 's':
      case 'S':
        // Guard: Ctrl+S is browser save — only intercept when canvas has focus
        if (document.activeElement?.tagName === 'CANVAS') {
          e.preventDefault();
          this.tryAdd('side');
        }
        break;

      case '1':
      case '2':
      case '3':
      case '4':
        e.preventDefault();
        this.focusPane(parseInt(e.key, 10) - 1);
        break;

      case 'w':
      case 'W':
        e.preventDefault();
        this.closeCurrentPane();
        break;
    }
  }

  private tryAdd(orientation: ViewOrientation): void {
    if (!this.layout.canAddPane()) {
      this.toast.warning('Maximum 4 views reached');
      return;
    }
    this.layout.addPane(orientation);
  }

  private focusPane(index: number): void {
    const panes = this.layout.allPanes();
    if (panes[index]) {
      this.layout.setFocusedPane(panes[index].id);
    }
  }

  private closeCurrentPane(): void {
    const id = this.layout.focusedPaneId();
    if (id && this.layout.paneCount() > 1) {
      this.layout.removePane(id);
    }
  }
}
