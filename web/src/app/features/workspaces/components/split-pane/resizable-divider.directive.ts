import {
  Directive,
  ElementRef,
  HostBinding,
  HostListener,
  inject,
  input,
  OnDestroy,
} from '@angular/core';
import { SplitLayoutStoreService, SplitAxis } from '@core/services/split-layout-store.service';

/**
 * Drag-to-resize directive placed on the divider element between two panes.
 * Uses pointer capture for reliable drag across viewport boundaries.
 *
 * During drag: only moves the divider element via CSS transform — no Angular
 * signal writes, no re-renders, no Three.js resize events.
 * On pointerup: commits the final fraction to the store once.
 *
 * Usage:
 *   <div appResizableDivider [axis]="group.axis" [paneId]="pane.id"></div>
 */
@Directive({
  selector: '[appResizableDivider]',
  standalone: true,
})
export class ResizableDividerDirective implements OnDestroy {
  /** Split axis of the parent group — determines which dimension to measure. */
  axis   = input.required<SplitAxis>();
  /** ID of the LEFT / TOP pane (the one being resized). */
  paneId = input.required<string>();

  private layout = inject(SplitLayoutStoreService);
  private el     = inject<ElementRef<HTMLElement>>(ElementRef);

  private isDragging   = false;
  private startPos     = 0;
  private startFrac    = 0;
  private pendingFrac  = 0;
  private containerPx  = 0;

  private readonly moveHandler = (e: PointerEvent) => this.onPointerMove(e);
  private readonly upHandler   = (e: PointerEvent) => this.onPointerUp(e);

  @HostBinding('style.cursor')
  get cursorStyle(): string {
    return this.axis() === 'horizontal' ? 'col-resize' : 'row-resize';
  }

  @HostListener('pointerdown', ['$event'])
  onPointerDown(e: PointerEvent): void {
    e.preventDefault();
    this.isDragging = true;

    // Capture pointer so moves outside the element are still received
    (e.target as HTMLElement).setPointerCapture(e.pointerId);

    this.startPos = this.axis() === 'horizontal' ? e.clientX : e.clientY;

    // Snapshot the container size and current pane fraction at drag start
    const parent = this.el.nativeElement.parentElement;
    this.containerPx = parent
      ? (this.axis() === 'horizontal' ? parent.clientWidth : parent.clientHeight)
      : 0;

    const pane = this.layout.allPanes().find(p => p.id === this.paneId());
    this.startFrac  = pane?.sizeFraction ?? 0.5;
    this.pendingFrac = this.startFrac;

    // Visual feedback: add dragging class so CSS shows the full ghost line
    this.el.nativeElement.classList.add('divider--dragging');

    document.addEventListener('pointermove', this.moveHandler);
    document.addEventListener('pointerup',   this.upHandler);
  }

  private onPointerMove(e: PointerEvent): void {
    if (!this.isDragging || this.containerPx === 0) return;

    const currentPos = this.axis() === 'horizontal' ? e.clientX : e.clientY;
    const deltaPx    = currentPos - this.startPos;

    // Clamp so neither pane goes below MIN_PX
    const minFrac = this.layout.MIN_PX / this.containerPx;
    const raw     = this.startFrac + deltaPx / this.containerPx;
    this.pendingFrac = Math.max(minFrac, Math.min(1 - minFrac, raw));

    // Translate the divider element to show live position — zero Angular writes
    const translatePx = deltaPx;
    this.el.nativeElement.style.transform = this.axis() === 'horizontal'
      ? `translateX(${translatePx}px)`
      : `translateY(${translatePx}px)`;
  }

  private onPointerUp(e: PointerEvent): void {
    if (!this.isDragging) return;
    this.isDragging = false;

    (e.target as HTMLElement)?.releasePointerCapture?.(e.pointerId);
    this.cleanupListeners();

    // Reset the visual translate before the store update reflows the layout
    this.el.nativeElement.style.transform = '';
    this.el.nativeElement.classList.remove('divider--dragging');

    // Single store write → single Angular signal update → single reflow
    if (this.containerPx > 0) {
      this.layout.resizePane(this.paneId(), this.pendingFrac, this.containerPx);
    }
  }

  private cleanupListeners(): void {
    document.removeEventListener('pointermove', this.moveHandler);
    document.removeEventListener('pointerup',   this.upHandler);
  }

  ngOnDestroy(): void {
    this.cleanupListeners();
  }
}
