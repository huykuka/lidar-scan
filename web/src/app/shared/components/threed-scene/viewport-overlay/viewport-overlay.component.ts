import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import {DomSanitizer, SafeHtml} from '@angular/platform-browser';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {ViewOrientation} from '@core/services/split-layout-store.service';

export interface OrientationOption {
  value: ViewOrientation;
  label: string;
  svg: SafeHtml;
}

const ORTHO_VIEWS = new Set<ViewOrientation>(['top', 'bottom', 'front', 'end', 'left', 'right']);

/**
 * Two-tone isometric cube SVGs — each highlights the face matching the view direction.
 */
const S = '#888';
const F = '#4a9eff';

const RAW_SVGS: Record<ViewOrientation, string> = {
  perspective: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 28 28" fill="${F}" part="svg"><path d="M12 21.5a9.25 9.25 0 0 1-3.705-.748 9.6 9.6 0 0 1-3.016-2.03 9.6 9.6 0 0 1-2.03-3.017A9.25 9.25 0 0 1 2.5 12H4q0 3 1.952 5.238 1.951 2.24 4.921 2.67L9.366 18.4l1.053-1.054 3.839 3.839a6.4 6.4 0 0 1-1.121.244q-.57.07-1.137.071m.654-6.654V9.154h3l.884.885v3.922l-.884.885zm-5.192 0v-1.192h2.692v-1.212H8.46v-.884h1.693v-1.212H7.462V9.154h3.884v5.692zm6.384-1.192h1.5v-3.308h-1.5zM20 12q0-3-1.952-5.238-1.951-2.24-4.921-2.67L14.634 5.6l-1.053 1.054-3.839-3.838a6.4 6.4 0 0 1 1.121-.245q.57-.07 1.137-.071 1.972 0 3.705.748a9.6 9.6 0 0 1 3.016 2.03 9.6 9.6 0 0 1 2.03 3.017A9.25 9.25 0 0 1 21.5 12z"></path></svg>`,
  top: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round"><path d="M12 3 L21 8 L12 13 L3 8 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/><path d="M3 8 L3 16 L12 21 L21 16 L21 8" fill="none" stroke="${S}"/><path d="M12 13 L12 21" fill="none" stroke="${S}"/></svg>`,
  bottom: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round"><path d="M3 16 L12 21 L21 16 L12 11 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/><path d="M12 3 L21 8 L21 16" fill="none" stroke="${S}"/><path d="M12 3 L3 8 L3 16" fill="none" stroke="${S}"/><path d="M12 3 L12 11" fill="none" stroke="${S}"/><path d="M21 8 L12 11 L3 8" fill="none" stroke="${S}"/></svg>`,
  front: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round"><path d="M3 8 L12 13 L12 21 L3 16 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/><path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/><path d="M21 8 L21 16 L12 21" fill="none" stroke="${S}"/><path d="M12 13 L21 8" fill="none" stroke="${S}"/></svg>`,
  end: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round"><path d="M12 3 L21 8 L21 16 L12 11 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/><path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/><path d="M3 8 L3 16 L12 21" fill="none" stroke="${S}"/><path d="M12 13 L3 8" fill="none" stroke="${S}"/><path d="M12 13 L12 21" fill="none" stroke="${S}"/></svg>`,
  left: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round"><path d="M12 13 L21 8 L21 16 L12 21 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/><path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/><path d="M3 8 L3 16 L12 21" fill="none" stroke="${S}"/><path d="M12 13 L3 8" fill="none" stroke="${S}"/></svg>`,
  right: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round"><path d="M12 3 L3 8 L3 16 L12 11 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/><path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/><path d="M21 8 L21 16 L12 21" fill="none" stroke="${S}"/><path d="M12 13 L3 8" fill="none" stroke="${S}"/><path d="M3 8 L3 16 L12 21" fill="none" stroke="${S}"/></svg>`,
};

/**
 * Shared viewport overlay: orientation picker, grid toggle, scale indicator, empty state.
 * Decoupled from any specific store — communicates via inputs/outputs.
 *
 * Place this absolutely over a <ngt-canvas> container.
 */
@Component({
  selector: 'app-shared-viewport-overlay',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SynergyComponentsModule],
  templateUrl: './viewport-overlay.component.html',
  styleUrl: './viewport-overlay.component.css',
})
export class ViewportOverlayComponent {
  /** Current view orientation */
  readonly orientation = input<ViewOrientation>('perspective');
  /** Whether the grid is shown */
  readonly showGrid = input(true);
  /** Whether any data is being displayed */
  readonly hasData = input(false);
  /** Label for the empty state (e.g. "TOP VIEW") */
  readonly emptyLabel = input<string>('');

  /** Emitted when user selects a new orientation */
  readonly orientationChange = output<ViewOrientation>();
  /** Emitted when user toggles the grid */
  readonly gridToggle = output<boolean>();

  private sanitizer = inject(DomSanitizer);
  protected readonly dropdownOpen = signal(false);

  readonly orientationOptions: OrientationOption[] = (
    [
      ['perspective', '3D'],
      ['top', 'Top'],
      ['bottom', 'Bottom'],
      ['front', 'Front'],
      ['end', 'End'],
      ['left', 'Left'],
      ['right', 'Right'],
    ] as [ViewOrientation, string][]
  ).map(([value, label]) => ({
    value,
    label,
    svg: this.sanitizer.bypassSecurityTrustHtml(RAW_SVGS[value]),
  }));

  protected readonly currentOption = computed(
    () =>
      this.orientationOptions.find((o) => o.value === this.orientation()) ??
      this.orientationOptions[0],
  );

  protected readonly isOrtho = computed(() => ORTHO_VIEWS.has(this.orientation()));

  setOrientation(value: ViewOrientation): void {
    this.orientationChange.emit(value);
    this.dropdownOpen.set(false);
  }

  toggleOrtho(): void {
    const next: ViewOrientation = this.isOrtho() ? 'perspective' : 'top';
    this.orientationChange.emit(next);
  }

  protected toggleGrid(): void {
    this.gridToggle.emit(!this.showGrid());
  }
}
