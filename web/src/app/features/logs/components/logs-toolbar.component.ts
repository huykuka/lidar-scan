import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-logs-toolbar',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  template: `
    <div class="bg-white p-3 flex items-center justify-between gap-4 transition-all duration-300">
      <!-- Left: Search & Filter Group -->
      <div class="flex items-center gap-4 flex-1 min-w-0">
        <div class="relative flex-1 max-w-lg group">
          <syn-input
            type="text"
            placeholder="Search logs..."
            [value]="searchText()"
            (syn-input)="onSearchInput($event)"
            clearable
            class="w-full transition-all duration-200 group-hover:shadow-sm"
          >
            <syn-icon slot="prefix" name="search" class="text-syn-color-primary-600"></syn-icon>
          </syn-input>
        </div>

        <div class="flex items-center gap-2">
          <syn-select
            [value]="selectedLevel()"
            (syn-change)="onLevelChange($event)"
            class="w-[140px]"
            placeholder="Filter Level"
          >
            <syn-option value="">All Levels</syn-option>
            <syn-option value="DEBUG">Debug</syn-option>
            <syn-option value="INFO">Info</syn-option>
            <syn-option value="WARNING">Warning</syn-option>
            <syn-option value="ERROR">Error</syn-option>
            <syn-option value="CRITICAL">Critical</syn-option>
          </syn-select>
        </div>

        <div
          class="flex gap-3 items-center border-l border-syn-color-neutral-100 pl-4 hidden xl:flex"
        >
          <syn-badge variant="neutral" size="small" class="opacity-70"
            >{{ totalCount() || 0 }} total</syn-badge
          >
          @if (errorCount() > 0) {
            <syn-badge variant="danger" size="small">{{ errorCount() }} errors</syn-badge>
          }
        </div>
      </div>

      <!-- Right: Actions Group -->
      <div class="flex items-center gap-2">
        <!-- Live Stream Toggle -->
        <syn-button
          [variant]="isStreaming() ? 'filled' : 'outline'"
          (click)="streamingToggled.emit(!isStreaming())"
          class="min-w-[120px]"
        >
          <syn-icon
            slot="prefix"
            [name]="isStreaming() ? 'stop_circle' : 'play_circle'"
            [class.animate-pulse]="isStreaming()"
            [class.text-syn-color-red-500]="isStreaming()"
          >
          </syn-icon>
          {{ isStreaming() ? 'Stop Live' : 'Go Live' }}
        </syn-button>

        <div class="flex items-center gap-2">
          <syn-button
            variant="outline"
            (click)="downloadClicked.emit()"
            class="transition-all hover:bg-syn-color-primary-50"
          >
            <syn-icon slot="prefix" name="file_download"></syn-icon>
            Download Logs
          </syn-button>
        </div>
      </div>
    </div>
  `,
})
export class LogsToolbarComponent {
  searchText = input<string>('');
  selectedLevel = input<string>('');
  isStreaming = input<boolean>(false);
  totalCount = input<number>(0);
  errorCount = input<number>(0);

  searchChanged = output<string>();
  levelChanged = output<string>();
  streamingToggled = output<boolean>();
  downloadClicked = output<void>();
  clearClicked = output<void>();

  onSearchInput(event: any) {
    this.searchChanged.emit(event.target.value);
  }

  onLevelChange(event: any) {
    this.levelChanged.emit(event.target.value);
  }
}
