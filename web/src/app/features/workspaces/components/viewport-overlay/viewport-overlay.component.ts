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

/**
 * Two-tone isometric cube SVGs.
 * Stroke: #888 (neutral, visible on both light and dark)
 * Highlighted face: #4a9eff (blue — unmistakably distinct)
 * Other faces: transparent / very light fill
 */
const S = '#888'; // stroke color
const F = '#4a9eff'; // active face fill

const RAW_SVGS: Record<string, string> = {
  // Perspective — wireframe only, no face highlighted
  perspective: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M12 3 L21 8 L21 16 L12 21 L3 16 L3 8 Z"/>
    <path d="M12 3 L12 12"/>
    <path d="M12 12 L21 8"/>
    <path d="M12 12 L3 8"/>
    <path d="M12 12 L12 21"/>
  </svg>`,

  // Top — top face highlighted
  top: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M12 3 L21 8 L12 13 L3 8 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/>
    <path d="M3 8 L3 16 L12 21 L21 16 L21 8" fill="none" stroke="${S}"/>
    <path d="M12 13 L12 21" fill="none" stroke="${S}"/>
  </svg>`,

  // Front — front-left face highlighted
  front: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M3 8 L12 13 L12 21 L3 16 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/>
    <path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/>
    <path d="M21 8 L21 16 L12 21" fill="none" stroke="${S}"/>
    <path d="M12 13 L21 8" fill="none" stroke="${S}"/>
  </svg>`,

  // Side — front-right face highlighted
  side: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="${S}" stroke-width="1.4" stroke-linejoin="round">
    <path d="M21 8 L12 13 L12 21 L21 16 Z" fill="${F}" stroke="${F}" stroke-width="0.5"/>
    <path d="M12 3 L21 8 L12 13 L3 8 Z" fill="none" stroke="${S}"/>
    <path d="M3 8 L3 16 L12 21" fill="none" stroke="${S}"/>
    <path d="M12 13 L3 8" fill="none" stroke="${S}"/>
  </svg>`,
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

  readonly orientationOptions: OrientationOption[] = [
    {
      value: 'perspective',
      label: '3D',
      svg: this.sanitizer.bypassSecurityTrustHtml(RAW_SVGS['perspective']),
    },
    { value: 'top', label: 'Top', svg: this.sanitizer.bypassSecurityTrustHtml(RAW_SVGS['top']) },
    {
      value: 'front',
      label: 'Front',
      svg: this.sanitizer.bypassSecurityTrustHtml(RAW_SVGS['front']),
    },
    { value: 'side', label: 'Side', svg: this.sanitizer.bypassSecurityTrustHtml(RAW_SVGS['side']) },
  ];

  protected readonly currentOption = computed(
    () =>
      this.orientationOptions.find((o) => o.value === this.pane().orientation) ??
      this.orientationOptions[0],
  );

  setOrientation(value: ViewOrientation): void {
    this.layout.setPaneOrientation(this.pane().id, value);
    this.dropdownOpen.set(false);
  }
}
