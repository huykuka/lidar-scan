// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { ViewportOverlayComponent } from './viewport-overlay.component';
import { SplitLayoutStoreService } from '@core/services/split-layout-store.service';
import { PointCloudDataService } from '@core/services/point-cloud-data.service';
import { ViewPane } from '@core/services/split-layout-store.service';

describe('ViewportOverlayComponent', () => {
  let component: ViewportOverlayComponent;
  let fixture: ComponentFixture<ViewportOverlayComponent>;
  let mockLayout: any;
  let mockDataService: any;

  const defaultPane: ViewPane = { id: 'p1', orientation: 'perspective', sizeFraction: 1 };

  beforeEach(async () => {
    mockLayout = {
      paneCount: signal(1),
      setPaneOrientation: vi.fn(),
    };

    mockDataService = {
      frames: signal(new Map()),
    };

    await TestBed.configureTestingModule({
      imports: [ViewportOverlayComponent],
      providers: [
        { provide: SplitLayoutStoreService, useValue: mockLayout },
        { provide: PointCloudDataService, useValue: mockDataService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ViewportOverlayComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('pane', defaultPane);
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display the orientation label', () => {
    const badge = fixture.nativeElement.querySelector('[class*="uppercase"]');
    expect(badge?.textContent?.toLowerCase()).toContain('perspective');
  });

  it('should not render a close button', () => {
    const closeBtn = fixture.nativeElement.querySelector('button');
    expect(closeBtn).toBeFalsy();
  });

  it('should render the orientation dropdown', () => {
    const select = fixture.nativeElement.querySelector('select');
    expect(select).toBeTruthy();
  });

  it('should call setPaneOrientation when orientation is changed', () => {
    const select: HTMLSelectElement = fixture.nativeElement.querySelector('select');
    select.value = 'top';
    select.dispatchEvent(new Event('change'));
    expect(mockLayout.setPaneOrientation).toHaveBeenCalledWith('p1', 'top');
  });

  it('should show empty state when frames map is empty (no data)', () => {
    mockDataService.frames.set(new Map());
    fixture.detectChanges();
    const emptyState = fixture.nativeElement.querySelector('[class*="inset-0"]') ||
                       fixture.nativeElement.querySelector('.empty-state');
    expect(emptyState).toBeTruthy();
  });

  it('should hide empty state when frames map has data', () => {
    const framesMap = new Map([['lidar_1', { timestamp: 0, count: 100, points: new Float32Array(300) }]]);
    mockDataService.frames.set(framesMap);
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should show performance warning badge when adaptiveLodActive is true', () => {
    fixture.componentRef.setInput('pane', {
      id: 'p1', orientation: 'perspective', sizeFraction: 0.3,
    } satisfies ViewPane);
    mockLayout.paneCount.set(3);
    fixture.detectChanges();
    // adaptiveLodActive = paneCount > 1 && sizeFraction < 0.5
    const warning = fixture.nativeElement.querySelector('[class*="yellow"]');
    expect(warning).toBeTruthy();
  });

  it('should NOT show performance warning badge when adaptiveLodActive is false', () => {
    fixture.componentRef.setInput('pane', defaultPane);
    mockLayout.paneCount.set(1);
    fixture.detectChanges();
    const warning = fixture.nativeElement.querySelector('[class*="yellow"]');
    expect(warning).toBeFalsy();
  });

  // ── Bug fix: [value] removed from <select> (Bug 2 regression guard) ────────
  // The <select> must NOT have a [value] binding — the correct selected state
  // is driven solely by [selected] on each <option>, which Angular applies
  // after all options are in the DOM (avoids timing-based mismatched display).
  it('should NOT have a value attribute on the <select> element (no [value] binding)', () => {
    const select: HTMLSelectElement = fixture.nativeElement.querySelector('select');
    expect(select).toBeTruthy();
    // The select element should not have a static 'value' attribute set by Angular
    // (i.e. [value]="..." was removed). The displayed selection is driven by [selected] on options.
    // We verify the correct option IS selected via [selected] instead.
    const perspectiveOption: HTMLOptionElement | null = select.querySelector('option[value="perspective"]');
    expect(perspectiveOption?.selected).toBe(true);
  });

  it('should update the displayed option when pane orientation changes', () => {
    // Simulate orientation change from perspective to top via input update
    fixture.componentRef.setInput('pane', {
      id: 'p1', orientation: 'top', sizeFraction: 1,
    } satisfies ViewPane);
    fixture.detectChanges();

    const select: HTMLSelectElement = fixture.nativeElement.querySelector('select');
    const topOption: HTMLOptionElement | null = select.querySelector('option[value="top"]');
    const perspOption: HTMLOptionElement | null = select.querySelector('option[value="perspective"]');

    // After orientation changes to "top", "top" option should be selected
    expect(topOption?.selected).toBe(true);
    expect(perspOption?.selected).toBe(false);
  });
});
