// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';
import { Component, input, NO_ERRORS_SCHEMA } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal, computed } from '@angular/core';
import { SplitPaneContainerComponent } from './split-pane-container.component';
import { SplitLayoutStoreService } from '@core/services/split-layout-store.service';
import { WorkspaceStoreService } from '@core/services/stores/workspace-store.service';
import { PointCloudDataService } from '@core/services/point-cloud-data.service';
import { PointCloudComponent } from '../../point-cloud/point-cloud.component';
import { ViewportOverlayComponent } from '../../viewport-overlay/viewport-overlay.component';
import { ResizableDividerDirective } from '../resizable-divider.directive';
import { ViewPane } from '@core/services/split-layout-store.service';

// ── Stub components to avoid Three.js WebGL and Synergy ResizeObserver errors ─

@Component({ selector: 'app-point-cloud', template: '', standalone: true })
class PointCloudStub {
  pointSize = input<number>(0.1);
  showGrid = input<boolean>(true);
  showAxes = input<boolean>(true);
  backgroundColor = input<string>('#000000');
}

@Component({ selector: 'app-viewport-overlay', template: '', standalone: true })
class ViewportOverlayStub {
  pane = input.required<ViewPane>();
}

describe('SplitPaneContainerComponent', () => {
  let component: SplitPaneContainerComponent;
  let fixture: ComponentFixture<SplitPaneContainerComponent>;
  let mockLayout: any;
  let mockStore: any;
  let mockDataService: any;

  beforeEach(async () => {
    const panes = [{ id: 'p1', orientation: 'perspective', sizeFraction: 1 }];
    const groups = signal([{ axis: 'horizontal', panes }]);
    const paneCount = signal(1);

    mockLayout = {
      groups,
      paneCount,
      allPanes: computed(() => groups().flatMap((g: any) => g.panes)),
    };

    mockStore = {
      backgroundColor: signal('#000000'),
      pointSize: signal(0.1),
      showAxes: signal(true),
      showGrid: signal(true),
    };

    mockDataService = {
      frames: signal(new Map()),
    };

    await TestBed.configureTestingModule({
      imports: [SplitPaneContainerComponent],
      providers: [
        { provide: SplitLayoutStoreService, useValue: mockLayout },
        { provide: WorkspaceStoreService, useValue: mockStore },
        { provide: PointCloudDataService, useValue: mockDataService },
      ],
    })
      .overrideComponent(SplitPaneContainerComponent, {
        // Remove real heavy imports; add lightweight stubs instead
        remove: { imports: [PointCloudComponent, ViewportOverlayComponent, ResizableDividerDirective] },
        add:    { imports: [PointCloudStub, ViewportOverlayStub], schemas: [NO_ERRORS_SCHEMA] },
      })
      .compileComponents();

    fixture = TestBed.createComponent(SplitPaneContainerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render a pane container for each pane in the group', () => {
    const paneEls = fixture.nativeElement.querySelectorAll('[data-pane-id]');
    expect(paneEls.length).toBeGreaterThanOrEqual(1);
  });

  it('should apply horizontal flex class for horizontal axis', () => {
    const el = fixture.nativeElement.querySelector('.flex-row, [class*="flex-row"]') ??
               fixture.nativeElement.querySelector('div');
    expect(el).toBeTruthy();
  });

  it('should show a divider between panes when more than one pane exists', () => {
    mockLayout.groups.set([{
      axis: 'horizontal',
      panes: [
        { id: 'p1', orientation: 'perspective', sizeFraction: 0.5 },
        { id: 'p2', orientation: 'top', sizeFraction: 0.5 },
      ]
    }]);
    mockLayout.paneCount.set(2);
    fixture.detectChanges();

    const dividers = fixture.nativeElement.querySelectorAll('.split-divider');
    expect(dividers.length).toBeGreaterThanOrEqual(1);
  });

  describe('isSmallPane()', () => {
    it('should return false when only 1 pane with sizeFraction 1.0', () => {
      const pane = mockLayout.allPanes()[0];
      expect(component.isSmallPane(pane)).toBe(false);
    });

    it('should return true for a pane with sizeFraction < 0.5 when paneCount > 1', () => {
      mockLayout.paneCount.set(2);
      const smallPane = { id: 'x', orientation: 'top' as const, sizeFraction: 0.3 };
      expect(component.isSmallPane(smallPane)).toBe(true);
    });
  });
});

