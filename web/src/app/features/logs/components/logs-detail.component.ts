import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogEntry } from '../../../core/models/log.model';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-logs-detail',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  template: `
    @if (entry()) {
      <div
        class="h-[300px] border-t border-syn-color-neutral-200 flex flex-col bg-white animate-in slide-in-from-bottom duration-300"
      >
        <div
          class="flex justify-between items-center px-6 py-2 bg-syn-color-neutral-50 border-b border-syn-color-neutral-100"
        >
          <h3 class="text-sm font-bold uppercase tracking-wider text-syn-color-neutral-600">
            Log Details
          </h3>
          <syn-icon-button
            name="close"
            label="Close"
            size="small"
            (click)="close.emit()"
          ></syn-icon-button>
        </div>
        <div class="flex-1 overflow-y-auto p-4 flex gap-6">
          <div class="flex flex-col gap-3 min-w-[200px]">
            <div class="flex flex-col">
              <span class="text-[10px] font-bold text-syn-color-neutral-400 uppercase"
                >Timestamp</span
              >
              <span class="font-mono text-sm font-medium">{{ entry()?.timestamp }}</span>
            </div>
            <div class="flex flex-col">
              <span class="text-[10px] font-bold text-syn-color-neutral-400 uppercase">Level</span>
              <syn-badge
                [variant]="getSynergyBadgeVariant(entry()?.level || '')"
                size="small"
                class="w-min"
              >
                {{ entry()?.level }}
              </syn-badge>
            </div>
            <div class="flex flex-col">
              <span class="text-[10px] font-bold text-syn-color-neutral-400 uppercase">Module</span>
              <span class="font-mono text-sm text-syn-color-blue-700 font-semibold">{{
                entry()?.module
              }}</span>
            </div>
          </div>
          <div class="flex-1 flex flex-col gap-2">
            <div class="flex justify-between items-center">
              <span class="text-[10px] font-bold text-syn-color-neutral-400 uppercase"
                >Message</span
              >
              <syn-button variant="outline" size="small" (click)="onCopy()">
                <syn-icon slot="prefix" name="content_copy"></syn-icon>
                Copy Message
              </syn-button>
            </div>
            <pre
              class="flex-1 bg-syn-color-neutral-950 text-syn-color-neutral-100 p-3 rounded font-mono text-xs whitespace-pre-wrap break-all shadow-inner overflow-auto ring-1 ring-white/10 leading-relaxed"
            >
              {{ entry()?.message }}
            </pre
            >
          </div>
        </div>
      </div>
    }
  `,
})
export class LogsDetailComponent {
  entry = input<LogEntry | null>(null);
  close = output<void>();

  onCopy() {
    if (this.entry()) {
      navigator.clipboard.writeText(this.entry()!.message);
    }
  }

  getSynergyBadgeVariant(level: string): 'neutral' | 'primary' | 'warning' | 'danger' {
    switch (level) {
      case 'DEBUG':
        return 'neutral';
      case 'INFO':
        return 'primary';
      case 'WARNING':
        return 'warning';
      case 'ERROR':
      case 'CRITICAL':
        return 'danger';
      default:
        return 'neutral';
    }
  }
}
