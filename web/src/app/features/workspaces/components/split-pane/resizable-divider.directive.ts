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

  private isDragging = false;
  private startPos   = 0;
  private startFrac  = 0;

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

    // Record the current fraction of the pane being dragged
    const pane = this.layout.allPanes().find(p => p.id === this.paneId());
    this.startFrac = pane?.sizeFraction ?? 0.5;

    document.addEventListener('pointermove', this.moveHandler);
    document.addEventListener('pointerup', this.upHandler);
  }

  private onPointerMove(e: PointerEvent): void {
    if (!this.isDragging) return;

    const parent = this.el.nativeElement.parentElement;
    if (!parent) return;

    const containerPx = this.axis() === 'horizontal'
      ? parent.clientWidth
      : parent.clientHeight;

    if (containerPx === 0) return;

    const currentPos = this.axis() === 'horizontal' ? e.clientX : e.clientY;
    const deltaPx    = currentPos - this.startPos;
    const newFrac    = this.startFrac + deltaPx / containerPx;

    this.layout.resizePane(this.paneId(), newFrac, containerPx);
  }

  private onPointerUp(e: PointerEvent): void {
    this.isDragging = false;
    (e.target as HTMLElement)?.releasePointerCapture?.(e.pointerId);
    this.cleanupListeners();
  }

  private cleanupListeners(): void {
    document.removeEventListener('pointermove', this.moveHandler);
    document.removeEventListener('pointerup', this.upHandler);
  }

  ngOnDestroy(): void {
    this.cleanupListeners();
  }
}
