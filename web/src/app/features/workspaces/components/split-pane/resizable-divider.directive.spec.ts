// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component, signal } from '@angular/core';
import { ResizableDividerDirective } from './resizable-divider.directive';
import { SplitLayoutStoreService } from '@core/services/split-layout-store.service';
import { By } from '@angular/platform-browser';

@Component({
  template: `
    <div style="width:1000px; height:100px; display:flex">
      <div appResizableDivider [axis]="axis()" [paneId]="paneId()" style="width:8px; cursor:col-resize"></div>
    </div>
  `,
  imports: [ResizableDividerDirective],
  standalone: true,
})
class TestHostComponent {
  axis = signal<'horizontal' | 'vertical'>('horizontal');
  paneId = signal('pane-1');
}

describe('ResizableDividerDirective', () => {
  let fixture: ComponentFixture<TestHostComponent>;
  let mockLayout: any;

  beforeEach(async () => {
    const panes = signal([
      { id: 'pane-1', orientation: 'perspective', sizeFraction: 0.5 },
      { id: 'pane-2', orientation: 'top', sizeFraction: 0.5 },
    ]);

    mockLayout = {
      allPanes: panes,
      resizePane: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [TestHostComponent],
      providers: [
        { provide: SplitLayoutStoreService, useValue: mockLayout },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(TestHostComponent);
    fixture.detectChanges();
  });

  it('should create an instance', () => {
    const directive = fixture.debugElement.query(By.directive(ResizableDividerDirective));
    expect(directive).toBeTruthy();
  });

  it('should call resizePane when dragging horizontally', () => {
    const divider = fixture.debugElement.query(By.directive(ResizableDividerDirective));
    const el: HTMLElement = divider.nativeElement;

    // Mock setPointerCapture / releasePointerCapture
    el.setPointerCapture = vi.fn();
    el.releasePointerCapture = vi.fn();

    const parent = el.parentElement!;
    Object.defineProperty(parent, 'clientWidth', { value: 1000, configurable: true });
    Object.defineProperty(parent, 'clientHeight', { value: 100, configurable: true });

    // Simulate pointerdown at x=500
    el.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 1, clientX: 500, bubbles: true }));

    // Simulate pointermove to x=600 (100px delta)
    document.dispatchEvent(new PointerEvent('pointermove', { pointerId: 1, clientX: 600, bubbles: true }));

    expect(mockLayout.resizePane).toHaveBeenCalledWith(
      'pane-1',
      expect.any(Number),
      1000,
    );
  });

  it('should stop calling resizePane after pointerup', () => {
    const divider = fixture.debugElement.query(By.directive(ResizableDividerDirective));
    const el: HTMLElement = divider.nativeElement;
    el.setPointerCapture = vi.fn();
    el.releasePointerCapture = vi.fn();

    const parent = el.parentElement!;
    Object.defineProperty(parent, 'clientWidth', { value: 1000, configurable: true });

    el.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 1, clientX: 500, bubbles: true }));
    document.dispatchEvent(new PointerEvent('pointerup', { pointerId: 1, bubbles: true }));

    vi.clearAllMocks();

    // Move after up — should not call
    document.dispatchEvent(new PointerEvent('pointermove', { pointerId: 1, clientX: 700, bubbles: true }));

    expect(mockLayout.resizePane).not.toHaveBeenCalled();
  });
});
