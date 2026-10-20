import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import {SynButtonComponent, SynDialogComponent, SynIconComponent} from '@synergy-design-system/angular';
import {OnboardingService} from '@core/services/onboarding.service';

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const PAD = 6;
const CARD_W = 340;

/**
 * Welcome dialog (first run) followed by a spotlight tour of the main areas.
 * Place once in app.html.
 */
@Component({
  selector: 'app-onboarding',
  imports: [SynDialogComponent, SynButtonComponent, SynIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <syn-dialog
      label="Welcome to LiDAR Studio"
      [open]="svc.showWelcome()"
      (syn-request-close)="$event.preventDefault()"
    >
      <div class="flex flex-col gap-3">
        <p class="m-0">
          Connect LiDAR sensors, build a processing pipeline and explore your point clouds in 3D.
        </p>
        <ul class="m-0 pl-5 text-sm" style="color: var(--syn-color-neutral-700)">
          <li><strong>Workspaces</strong> – live 3D view of your sensors</li>
          <li><strong>Settings</strong> – build the processing pipeline</li>
          <li><strong>Recordings &amp; Replays</strong> – record and play back data</li>
        </ul>
        <p class="m-0 text-sm" style="color: var(--syn-color-neutral-600)">
          Take a short tour to see where everything is.
        </p>
      </div>
      <div slot="footer" class="flex justify-end gap-2">
        <syn-button variant="outline" (click)="svc.finish()">Skip</syn-button>
        <syn-button variant="filled" (click)="svc.startTour()">
          <syn-icon slot="prefix" name="play_arrow" aria-hidden="true" />
          Start tour
        </syn-button>
      </div>
    </syn-dialog>

    @if (step(); as s) {
      <div class="tour-blocker" (click)="$event.stopPropagation()"></div>
      @if (rect(); as r) {
        <div
          class="tour-spot"
          [style.top.px]="r.top - pad"
          [style.left.px]="r.left - pad"
          [style.width.px]="r.width + pad * 2"
          [style.height.px]="r.height + pad * 2"
        ></div>
      } @else {
        <div class="tour-dim"></div>
      }
      <div class="tour-card" role="dialog" [style.top.px]="cardPos().top" [style.left.px]="cardPos().left">
        <div class="text-xs" style="color: var(--syn-color-neutral-600)">
          Step {{ svc.tourStep()! + 1 }} of {{ svc.steps.length }}
        </div>
        <h3 class="m-0 mt-1 mb-2 text-lg">{{ s.title }}</h3>
        <p class="m-0 text-sm">{{ s.body }}</p>
        <div class="flex items-center justify-between mt-4">
          <syn-button size="small" variant="text" (click)="svc.finish()">Skip</syn-button>
          <div class="flex gap-2">
            @if (svc.tourStep()! > 0) {
              <syn-button size="small" variant="outline" (click)="svc.back()">Back</syn-button>
            }
            <syn-button size="small" variant="filled" (click)="svc.next()">
              {{ isLast() ? 'Finish' : 'Next' }}
            </syn-button>
          </div>
        </div>
      </div>
    }
  `,
  styles: `
    .tour-blocker {
      position: fixed;
      inset: 0;
      z-index: 2000;
    }
    .tour-dim {
      position: fixed;
      inset: 0;
      z-index: 2001;
      background: rgba(0, 0, 0, 0.55);
      pointer-events: none;
    }
    .tour-spot {
      position: fixed;
      z-index: 2001;
      border-radius: 6px;
      box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55);
      outline: 2px solid var(--syn-color-primary-500);
      pointer-events: none;
      transition: all 0.2s ease;
    }
    .tour-card {
      position: fixed;
      z-index: 2002;
      width: min(340px, calc(100vw - 24px));
      box-sizing: border-box;
      padding: 16px;
      border-radius: 8px;
      background: var(--syn-panel-background-color, #fff);
      color: var(--syn-color-neutral-900);
      border: 1px solid var(--syn-panel-border-color);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    }
  `,
})
export class OnboardingComponent {
  protected readonly svc = inject(OnboardingService);
  protected readonly pad = PAD;


  protected readonly step = computed(() => {
    const i = this.svc.tourStep();
    return i === null ? null : this.svc.steps[i];
  });
  protected readonly isLast = computed(() => this.svc.tourStep() === this.svc.steps.length - 1);

  protected readonly rect = signal<Rect | null>(null);
  private readonly viewport = signal({w: window.innerWidth, h: window.innerHeight});

  protected readonly cardPos = computed(() => {
    const {w, h} = this.viewport();
    const cardW = Math.min(CARD_W, w - 24);
    const r = this.rect();
    if (!r) return {top: Math.max(12, h / 2 - 90), left: Math.max(12, (w - cardW) / 2)};
    // Prefer to the right of the target, else below, clamped to the viewport.
    let left = r.left + r.width + PAD + 14;
    let top = r.top;
    if (left + cardW > w - 12) {
      left = r.left;
      top = r.top + r.height + PAD + 14;
    }
    return {
      left: Math.min(Math.max(12, left), w - cardW - 12),
      top: Math.min(Math.max(12, top), h - 220),
    };
  });

  constructor() {
    effect(() => {
      const s = this.step();
      this.svc.tourStep();
      this.measure(s?.target);
    });
  }

  @HostListener('window:resize')
  protected onResize(): void {
    this.viewport.set({w: window.innerWidth, h: window.innerHeight});
    this.measure(this.step()?.target);
  }

  @HostListener('window:keydown.escape')
  protected onEscape(): void {
    if (this.svc.isTouring()) this.svc.finish();
  }

  private measure(selector?: string): void {
    if (!selector) {
      this.rect.set(null);
      return;
    }
    // Let layout settle (side-nav may still be animating) before measuring.
    setTimeout(() => {
      const el = document.querySelector(selector);
      const b = el?.getBoundingClientRect();
      this.rect.set(b && b.width > 0 ? {top: b.top, left: b.left, width: b.width, height: b.height} : null);
    }, 50);
  }
}
