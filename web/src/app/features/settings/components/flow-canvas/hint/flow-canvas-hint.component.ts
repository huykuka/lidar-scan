import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

interface Hint {
  icon: string;
  key: string;
  desc: string;
}

const HINTS: Hint[] = [
  { icon: 'mouse',           key: 'Left Click',                desc: 'Select node' },
  { icon: 'open_with',       key: 'Left Click Hold',          desc: 'Pan view' },
  { icon: 'select_all',      key: 'Shift + Left Click Hold',         desc: 'Area select' },
  { icon: 'zoom_in',         key: 'Scroll wheel',         desc: 'Zoom' },
  { icon: 'edit',            key: 'Double-click',         desc: 'Edit node' },
  { icon: 'content_copy',    key: 'Ctrl + C / V',         desc: 'Copy / Paste' },
];

@Component({
  selector: 'app-flow-canvas-hint',
  imports: [SynergyComponentsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="hint-host">
      <!-- Trigger button -->
      <button
        (click)="open.set(!open())"
        [class.active]="open()"
        class="hint-trigger"
        aria-label="Canvas shortcuts"
      >
        <syn-icon name="keyboard" style="font-size: 14px" />
      </button>

      <!-- Popover -->
      @if (open()) {
        <div class="hint-backdrop" (click)="open.set(false)"></div>

        <div class="hint-panel" role="tooltip" aria-live="polite">
          <div class="hint-header">
            <span class="hint-title">Shortcuts</span>
            <button class="hint-close" (click)="open.set(false)" aria-label="Close">
              <syn-icon name="close" style="font-size: 12px" />
            </button>
          </div>
          <ul class="hint-list">
            @for (h of hints; track h.key) {
              <li class="hint-row">
                <syn-icon [name]="h.icon" class="hint-icon" />
                <kbd class="hint-key">{{ h.key }}</kbd>
                <span class="hint-desc">{{ h.desc }}</span>
              </li>
            }
          </ul>
        </div>
      }
    </div>
  `,
  styles: [`
    .hint-host { position: relative; }

    /* ── Trigger ── */
    .hint-trigger {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 1.75rem;
      height: 1.75rem;
      border-radius: 6px;
      border: 1px solid var(--syn-color-neutral-300);
      background: var(--syn-page-background-color);
      color: var(--syn-color-neutral-500);
      box-shadow: 0 1px 2px rgba(0,0,0,.06);
      cursor: pointer;
      transition: all 120ms ease;
    }

    .hint-trigger:hover,
    .hint-trigger.active {
      background: var(--syn-color-primary-50);
      border-color: var(--syn-color-primary-400);
      color: var(--syn-color-primary-600);
      box-shadow: 0 2px 6px rgba(0,0,0,.08);
    }

    /* ── Backdrop ── */
    .hint-backdrop {
      position: fixed;
      inset: 0;
      z-index: 39;
    }

    /* ── Panel ── */
    .hint-panel {
      position: absolute;
      bottom: calc(100% + 8px);
      right: 0;
      z-index: 40;
      width: 16rem;
      background: var(--syn-page-background-color);
      border: 1px solid var(--syn-color-neutral-300);
      border-radius: 10px;
      box-shadow: 0 8px 24px rgba(0,0,0,.12), 0 2px 6px rgba(0,0,0,.06);
      padding: 0.5rem 0.625rem;
      animation: hint-in 120ms cubic-bezier(.2,.8,.4,1) both;
    }

    @keyframes hint-in {
      from { opacity: 0; transform: translateY(4px) scale(.98); }
      to   { opacity: 1; transform: translateY(0)   scale(1);   }
    }

    .hint-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.375rem;
      padding-bottom: 0.25rem;
      border-bottom: 1px solid var(--syn-color-neutral-200);
    }

    .hint-title {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: var(--syn-color-neutral-500);
      margin: 0;
    }

    .hint-close {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 1.25rem;
      height: 1.25rem;
      border: none;
      background: transparent;
      border-radius: 4px;
      color: var(--syn-color-neutral-400);
      cursor: pointer;
    }

    .hint-close:hover {
      background: var(--syn-color-neutral-100);
      color: var(--syn-color-neutral-700);
    }

    /* ── Rows ── */
    .hint-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
    }

    .hint-row {
      display: grid;
      grid-template-columns: 14px 1fr auto;
      align-items: center;
      gap: 0.4rem;
      padding: 2px 0;
    }

    .hint-icon {
      color: var(--syn-color-neutral-400);
      font-size: 12px;
      justify-self: center;
    }

    .hint-key {
      font-size: 10px;
      font-weight: 600;
      font-family: var(--syn-font-mono, ui-monospace, monospace);
      color: var(--syn-color-neutral-700);
      background: var(--syn-color-neutral-100);
      border: 1px solid var(--syn-color-neutral-200);
      border-bottom-width: 2px;
      border-radius: 3px;
      padding: 1px 5px;
      white-space: nowrap;
      line-height: 1.4;
    }

    .hint-desc {
      font-size: 10px;
      color: var(--syn-color-neutral-500);
      text-align: right;
    }
  `],
})
export class FlowCanvasHintComponent {
  readonly hints = HINTS;
  open = signal(false);
}
