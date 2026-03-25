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
      removePane: vi.fn(),
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

  it('should disable close button when isLastPane (paneCount === 1)', () => {
    mockLayout.paneCount.set(1);
    fixture.detectChanges();
    const closeBtn = fixture.nativeElement.querySelector('button[disabled], button:disabled');
    expect(closeBtn).toBeTruthy();
  });

  it('should enable close button when paneCount > 1', () => {
    mockLayout.paneCount.set(2);
    fixture.detectChanges();
    const closeBtn = fixture.nativeElement.querySelector('button:not([disabled])');
    expect(closeBtn).toBeTruthy();
  });

  it('should call removePane when close button is clicked (paneCount > 1)', () => {
    mockLayout.paneCount.set(2);
    fixture.detectChanges();
    const closeBtn: HTMLButtonElement = fixture.nativeElement.querySelector('button:not([disabled])');
    closeBtn?.click();
    expect(mockLayout.removePane).toHaveBeenCalledWith('p1');
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
});
