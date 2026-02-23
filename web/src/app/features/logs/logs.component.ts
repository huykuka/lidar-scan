import { Component, OnInit, OnDestroy, inject, signal, computed, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LogsStoreService } from '../../core/services/stores/logs-store.service';
import { LogsApiService } from '../../core/services/api/logs-api.service';
import { LogEntry } from '../../core/models/log.model';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

import { NavigationService } from '../../core/services';
import { LogsToolbarComponent } from './components/logs-toolbar.component';
import { LogsTableComponent } from './components/logs-table.component';
import { LogsDetailComponent } from './components/logs-detail.component';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-logs',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    LogsToolbarComponent,
    LogsTableComponent,
    LogsDetailComponent,
    SynergyComponentsModule,
  ],
  templateUrl: './logs.component.html',
})
export class LogsComponent implements OnInit, OnDestroy {
  store = inject(LogsStoreService);
  private api = inject(LogsApiService);
  private destroy$ = new Subject<void>();
  private navService = inject(NavigationService);

  // Signals
  entries = this.store.entries;
  isLoading = this.store.isLoading;
  isStreaming = this.store.isStreaming;
  filters = this.store.filters;
  streamError = this.store.streamError;
  autoScroll = this.store.autoScroll;
  selectedEntry = this.store.selectedEntry;

  // UI state
  selectedLevel = signal<string>('');
  searchText = signal<string>('');
  isLoadingMore = signal<boolean>(false);

  // Computed
  displayEntries = computed(() => {
    let result = this.entries();

    const level = this.selectedLevel();
    if (level) {
      result = result.filter((e) => e.level === level);
    }

    const search = this.searchText();
    if (search) {
      const lowSearch = search.toLowerCase();
      result = result.filter(
        (e) =>
          e.message.toLowerCase().includes(lowSearch) || e.module.toLowerCase().includes(lowSearch),
      );
    }

    return result;
  });

  levelCounts = computed(() => {
    const entries = this.entries();
    const counts: { [key: string]: number } = {};
    entries.forEach((e) => {
      counts[e.level] = (counts[e.level] || 0) + 1;
    });
    return counts;
  });

  ngOnInit() {
    this.navService.setPageConfig({
      title: 'Logs',
      subtitle: 'Monitor and analyze system events and logs',
    });
    this.loadInitialLogs();
    this.setupAutoRefresh();
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private async loadInitialLogs() {
    try {
      this.store.setLoading(true);
      const logs = await this.api.getLogs({ limit: 200 });
      this.store.setEntries(logs);
    } catch (error) {
      this.store.setStreamError('Failed to load logs');
      console.error('Error loading logs:', error);
    } finally {
      this.store.setLoading(false);
    }
  }

  private setupAutoRefresh() {
    // Auto-refresh logs every 5 seconds when not streaming
    const interval = setInterval(async () => {
      if (!this.isStreaming()) {
        try {
          const logs = await this.api.getLogs({ limit: 200 });
          this.store.setEntries(logs);
        } catch (error) {
          console.error('Auto-refresh failed:', error);
        }
      }
    }, 5000);

    this.destroy$.subscribe(() => clearInterval(interval));
  }

  onFilterChange() {
    // Reset offset when filters change
    this.store.setOffset(0);
    this.loadInitialLogs();
  }

  async loadMoreLogs() {
    if (this.isLoadingMore() || this.isLoading()) return;

    try {
      this.isLoadingMore.set(true);
      const currentFilters = this.store.filters();
      const newOffset = (currentFilters.offset || 0) + (currentFilters.limit || 100);

      this.store.setOffset(newOffset);

      const newLogs = await this.api.getLogs({
        ...currentFilters,
        offset: newOffset,
        level: this.selectedLevel() || undefined,
        search: this.searchText() || undefined,
      });

      if (newLogs.length > 0) {
        this.store.appendEntries(newLogs);
      }
    } catch (error) {
      console.error('Error loading more logs:', error);
    } finally {
      this.isLoadingMore.set(false);
    }
  }

  clearFilters() {
    this.selectedLevel.set('');
    this.searchText.set('');
  }

  clearAllLogs() {
    if (confirm('Clear all logs?')) {
      this.store.clearEntries();
    }
  }

  startStreaming() {
    if (this.isStreaming()) return;

    this.store.setStreaming(true);
    this.store.setStreamError(null);

    this.api
      .connectLogsWebSocket(this.selectedLevel() || undefined, this.searchText() || undefined)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (data) => {
          try {
            if (data === '{"type": "connected"}') {
              return; // Skip connection confirmation message
            }
            const entry: LogEntry = JSON.parse(data);
            this.store.addEntry(entry);
          } catch (error) {
            console.error('Failed to parse log entry:', error);
          }
        },
        error: (error) => {
          this.store.setStreamError('WebSocket connection failed');
          this.store.setStreaming(false);
          console.error('WebSocket error:', error);
        },
        complete: () => {
          this.store.setStreaming(false);
        },
      });
  }

  stopStreaming() {
    this.store.setStreaming(false);
  }

  onSelectEntry(entry: LogEntry | null) {
    this.store.selectEntry(entry);
  }

  copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
  }

  downloadLogs() {
    const filters = {
      level: this.selectedLevel() || undefined,
      search: this.searchText() || undefined,
    };

    const downloadUrl = this.api.getLogsDownloadUrl(filters);

    const link = document.createElement('a');
    link.href = downloadUrl;
    // The backend provides the filename in Content-Disposition
    document.body.appendChild(link);
    link.click();

    // Cleanup
    setTimeout(() => {
      document.body.removeChild(link);
    }, 100);
  }
}
