import { Component, computed, input } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { CanvasNode } from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import { NodeStatusUpdate } from '@core/models/node-status.model';
import { NodeCardComponent } from '@core/models/node-plugin.model';

interface PlaybackBadge {
  text: string;
  cssClass: string;
}

@Component({
  selector: 'app-playback-node-card',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './playback-node-card.component.html',
  styleUrl: './playback-node-card.component.css',
})
export class PlaybackNodeCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);

  // ── Config accessors ────────────────────────────────────────────────────────
  protected recordingId = computed(() => this.node().data.config?.['recording_id'] as string ?? '');
  protected playbackSpeed = computed(() => this.node().data.config?.['playback_speed'] as number ?? 1.0);
  protected loopable = computed(() => this.node().data.config?.['loopable'] as boolean ?? false);

  /**
   * Playback-specific status badge.
   * Maps operational_state → icon text + CSS class per technical.md §7.3
   *  ▶ PLAYING (frame N/M) — green  — RUNNING
   *  ■ IDLE                — grey   — STOPPED
   *  ✕ ERROR               — red    — ERROR
   */
  protected playbackBadge = computed<PlaybackBadge | null>(() => {
    const s = this.status();
    if (!s) return null;

    const appValue = s.application_state?.value ?? '';

    switch (s.operational_state) {
      case 'RUNNING': {
        // Extract frame info from application_state.value e.g. "playing (frame 42/300)"
        const frameMatch = String(appValue).match(/frame\s+(\d+\/\d+)/i);
        const frameInfo = frameMatch ? ` (${frameMatch[0]})` : '';
        return {
          text: `▶ PLAYING${frameInfo}`,
          cssClass: 'text-syn-color-success-600',
        };
      }
      case 'STOPPED':
        return {
          text: '■ IDLE',
          cssClass: 'text-syn-color-neutral-400',
        };
      case 'ERROR':
        return {
          text: '✕ ERROR',
          cssClass: 'text-syn-color-danger-600',
        };
      default:
        return null;
    }
  });
}
