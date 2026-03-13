import {Component, input, output} from '@angular/core';

import {LogEntry} from '@core/models';
import {SynergyComponentsModule} from '@synergy-design-system/angular';

@Component({
  selector: 'app-logs-table',
  standalone: true,
  imports: [SynergyComponentsModule],
  template: `
    <div class="flex-1 relative">
      @if (isLoading() && entries().length === 0) {
        <div
          class="flex flex-col items-center justify-center h-full text-syn-color-neutral-400 gap-4"
        >
          <syn-spinner size="large" />
          <p class="text-sm font-medium animate-pulse">Initializing log viewer...</p>
        </div>
      } @else if (!isLoading() && entries().length === 0) {
        <div
          class="flex flex-col items-center justify-center h-full text-syn-color-neutral-400 py-12"
        >
          <syn-icon name="description" class="text-5xl opacity-20 mb-4" />
          <p class="text-lg">No log entries found</p>
        </div>
      } @else {
        @if (isLoading()) {
          <div
            class="absolute inset-0 flex items-center justify-center bg-white/40 z-30 backdrop-blur-[1px]"
          >
            <syn-spinner size="large" />
          </div>
        }

        <table class="syn-table--default w-full">
          <thead>
            <tr>
              <th
                class="sticky top-0 z-20 px-4 py-3 bg-white text-left text-[10px] font-bold text-syn-color-neutral-600 uppercase tracking-widest w-45 border-b border-syn-color-neutral-200"
              >
                Timestamp
              </th>
              <th
                class="sticky top-0 z-20 px-4 py-3 bg-white text-left text-[10px] font-bold text-syn-color-neutral-600 uppercase tracking-widest w-27.5 border-b border-syn-color-neutral-200"
              >
                Level
              </th>
              <th
                class="sticky top-0 z-20 px-4 py-3 bg-white text-left text-[10px] font-bold text-syn-color-neutral-600 uppercase tracking-widest w-50 border-b border-syn-color-neutral-200"
              >
                Module
              </th>
              <th
                class="sticky top-0 z-20 px-4 py-3 bg-white text-left text-[10px] font-bold text-syn-color-neutral-600 uppercase tracking-widest border-b border-syn-color-neutral-200"
              >
                Message
              </th>
            </tr>
          </thead>
          <tbody>
            @for (entry of entries(); track entry.timestamp + $index) {
              <tr
                (click)="entrySelected.emit(entry)"
                class="cursor-pointer transition-colors group"
                [class.bg-syn-color-blue-50]="entry === selectedEntry()"
                [class.hover:bg-syn-color-neutral-50]="entry !== selectedEntry()"
              >
                <td
                  class="px-4 py-3 font-mono text-[11px] text-syn-color-neutral-500 whitespace-nowrap align-top border-b border-syn-color-neutral-100"
                >
                  {{ entry.timestamp }}
                </td>
                <td class="px-4 py-3 align-top border-b border-syn-color-neutral-100">
                  <syn-badge [variant]="getSynergyBadgeVariant(entry.level)" size="small">
                    {{ entry.level }}
                  </syn-badge>
                </td>
                <td
                  class="px-4 py-3 font-mono text-[11px] text-syn-color-blue-700 break-all align-top border-b border-syn-color-neutral-100"
                >
                  {{ entry.module }}
                </td>
                <td
                  class="px-4 py-3 font-mono text-xs text-syn-color-neutral-900 break-all opacity-90 group-hover:opacity-100 align-top border-b border-syn-color-neutral-100"
                >
                  {{ entry.message }}
                </td>
              </tr>
            }
          </tbody>
        </table>

        <!-- Load More Section -->
        @if (entries().length > 0) {
          <div class="p-4 flex justify-center bg-syn-color-neutral-50/50">
            <syn-button
              variant="outline"
              size="small"
              [loading]="isLoadingMore()"
              (click)="loadMoreClicked.emit()"
            >
              <syn-icon slot="prefix" name="expand_more" />
              Load More
            </syn-button>
          </div>
        }
      }
    </div>
  `,
})
export class LogsTableComponent {
  entries = input<LogEntry[]>([]);
  selectedEntry = input<LogEntry | null>(null);
  isLoading = input<boolean>(false);
  isLoadingMore = input<boolean>(false);

  entrySelected = output<LogEntry | null>();
  loadMoreClicked = output<void>();

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
