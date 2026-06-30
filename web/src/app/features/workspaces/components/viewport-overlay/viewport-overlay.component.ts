import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import {
  SplitLayoutStoreService,
  ViewPane,
  ViewOrientation,
} from '@core/services/split-layout-store.service';
import { PointCloudDataService } from '@core/services/point-cloud-data.service';

export interface OrientationOption {
  value: ViewOrientation;
  label: string;
  svg: SafeHtml;
}

const ORTHO_VIEWS = new Set<ViewOrientation>(['top', 'bottom', 'front', 'end', 'left', 'right']);

/**
 * Two-tone isometric cube SVGs — each highlights the face matching the view direction.
 * Stroke: #888  |  Active face fill: #4a9eff
 */
const S = '#888';
const F = '#4a9eff';

const RAW_SVGS: Record<ViewOrientation, string> = {
  // Perspective — full wireframe, no face highlighted
  perspective: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M12 3 L21 8 L21 16 L12 21 L3 16 L3 8 Z"/>
    <path d="M12 3 L12 12"/>
    <path d="M12 12 L21 8"/>
    <path d="M12 12 L3 8"/>
    <path d="M12 12 L12 21"/>
  </svg>`,

  // Top — top face highlighted (+Y)
  top: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M12 3 L21 8 L12 13 L3 8 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/>
    <path d="M3 8 L3 16 L12 21 L21 16 L21 8" fill="none" stroke="${S}"/>
    <path d="M12 13 L12 21" fill="none" stroke="${S}"/>
  </svg>`,

  // Bottom — bottom face highlighted (-Y)
  bottom: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M3 16 L12 21 L21 16 L12 11 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/>
    <path d="M12 3 L21 8 L21 16" fill="none" stroke="${S}"/>
    <path d="M12 3 L3 8 L3 16" fill="none" stroke="${S}"/>
    <path d="M12 3 L12 11" fill="none" stroke="${S}"/>
    <path d="M21 8 L12 11 L3 8" fill="none" stroke="${S}"/>
  </svg>`,

  // Front — front-left face highlighted (+Z)
  front: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M3 8 L12 13 L12 21 L3 16 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/>
    <path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/>
    <path d="M21 8 L21 16 L12 21" fill="none" stroke="${S}"/>
    <path d="M12 13 L21 8" fill="none" stroke="${S}"/>
  </svg>`,

  // End — back-right face highlighted (-Z)
  end: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M12 3 L21 8 L21 16 L12 11 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/>
    <path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/>
    <path d="M3 8 L3 16 L12 21" fill="none" stroke="${S}"/>
    <path d="M12 13 L3 8" fill="none" stroke="${S}"/>
    <path d="M12 13 L12 21" fill="none" stroke="${S}"/>
  </svg>`,

  // Left → now labeled "Front": highlight the front face (left-facing panel in iso view)
  left: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M12 13 L21 8 L21 16 L12 21 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/>
    <path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/>
    <path d="M3 8 L3 16 L12 21" fill="none" stroke="${S}"/>
    <path d="M12 13 L3 8" fill="none" stroke="${S}"/>
  </svg>
`,

  // Right → now labeled "Rear": highlight the rear face (right-facing panel in iso view)
  right: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M12 3 L3 8 L3 16 L12 11 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/>
    <path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/>
    <path d="M21 8 L21 16 L12 21" fill="none" stroke="${S}"/>
    <path d="M12 13 L3 8" fill="none" stroke="${S}"/>
    <path d="M3 8 L3 16 L12 21" fill="none" stroke="${S}"/>
</svg>
`,
};

@Component({
  selector: 'app-viewport-overlay',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SynergyComponentsModule],
  templateUrl: './viewport-overlay.component.html',
  styleUrl: './viewport-overlay.component.css',
})
export class ViewportOverlayComponent {
  pane = input.required<ViewPane>();

  protected layout = inject(SplitLayoutStoreService);
  protected dataService = inject(PointCloudDataService);
  private sanitizer = inject(DomSanitizer);

  protected readonly dropdownOpen = signal(false);

  protected hasData = computed(() => this.dataService.frames().size > 0);

  protected adaptiveLodActive = computed(
    () => this.layout.paneCount() > 1 && this.pane().sizeFraction < 0.5,
  );

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
      this.orientationOptions.find((o) => o.value === this.pane().orientation) ??
      this.orientationOptions[0],
  );

  protected readonly isOrtho = computed(() => ORTHO_VIEWS.has(this.pane().orientation));

  setOrientation(value: ViewOrientation): void {
    this.layout.setPaneOrientation(this.pane().id, value);
    this.dropdownOpen.set(false);
  }

  toggleOrtho(): void {
    const next: ViewOrientation = this.isOrtho() ? 'perspective' : 'top';
    this.layout.setPaneOrientation(this.pane().id, next);
  }

  resetCamera(): void {
    console.log(`ViewportOverlayComponent: resetCamera() for pane ${this.pane().id}`);
    this.layout.requestCameraReset(this.pane().id);
  }
}
