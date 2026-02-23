import { Component, OnInit, OnDestroy, inject, signal, computed, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LogsStoreService } from '../../core/services/stores/logs-store.service';
import { LogsApiService } from '../../core/services/api/logs-api.service';
import { LogEntry } from '../../core/models/log.model';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NavigationService } from '../../core/services';

@Component({
  selector: 'app-logs',
  standalone: true,
  imports: [CommonModule, FormsModule, SynergyComponentsModule],
  templateUrl: './logs.component.html',
  styleUrls: ['./logs.component.scss'],
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
  showFilters = signal<boolean>(false);

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
    // Applied in displayEntries computed
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

  toggleFilters() {
    this.showFilters.update((v) => !v);
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

  getLevelColor(level: string): string {
    switch (level) {
      case 'DEBUG':
        return '#808080';
      case 'INFO':
        return '#0066cc';
      case 'WARNING':
        return '#ff9900';
      case 'ERROR':
        return '#cc0000';
      case 'CRITICAL':
        return '#990000';
      default:
        return '#000000';
    }
  }

  getLevelIcon(level: string): string {
    switch (level) {
      case 'DEBUG':
        return 'bug_report';
      case 'INFO':
        return 'info';
      case 'WARNING':
        return 'warning';
      case 'ERROR':
        return 'error';
      case 'CRITICAL':
        return 'report';
      default:
        return 'help_outline';
    }
  }

  copyToClipboard(text: string) {
    navigator.clipboard.writeText(text).then(() => {
      console.log('Copied to clipboard');
    });
  }

  downloadLogs() {
    const content = this.displayEntries()
      .map((e) => `[${e.timestamp}] ${e.level} [${e.module}] ${e.message}`)
      .join('\n');

    const blob = new Blob([content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs-${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    window.URL.revokeObjectURL(url);
  }
}
