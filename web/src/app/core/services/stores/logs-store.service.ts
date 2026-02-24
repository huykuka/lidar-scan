import { Injectable } from '@angular/core';
import { SignalsSimpleStoreService } from '../signals-simple-store.service';
import { LogEntry, LogFilterOptions } from '../../models/log.model';

export interface LogsState {
  entries: LogEntry[];
  filteredEntries: LogEntry[];
  isLoading: boolean;
  isStreaming: boolean;
  filters: LogFilterOptions;
  selectedEntry: LogEntry | null;
  streamError: string | null;
  autoScroll: boolean;
}

const initialState: LogsState = {
  entries: [],
  filteredEntries: [],
  isLoading: false,
  isStreaming: false,
  filters: {
    level: undefined,
    search: undefined,
    offset: 0,
    limit: 100,
  },
  selectedEntry: null,
  streamError: null,
  autoScroll: true,
};

@Injectable({
  providedIn: 'root',
})
export class LogsStoreService extends SignalsSimpleStoreService<LogsState> {
  constructor() {
    super();
    this.setState(initialState);
  }

  // Selectors
  entries = this.select('entries');
  filteredEntries = this.select('filteredEntries');
  isLoading = this.select('isLoading');
  isStreaming = this.select('isStreaming');
  filters = this.select('filters');
  selectedEntry = this.select('selectedEntry');
  streamError = this.select('streamError');
  autoScroll = this.select('autoScroll');

  // Mutations
  addEntry(entry: LogEntry) {
    this.state.update((current) => ({
      ...current,
      entries: [entry, ...current.entries],
      filteredEntries: [entry, ...current.filteredEntries],
    }));
  }

  setEntries(entries: LogEntry[]) {
    this.setState({ entries, filteredEntries: entries });
  }

  appendEntries(entries: LogEntry[]) {
    this.state.update((current) => ({
      ...current,
      entries: [...current.entries, ...entries],
      filteredEntries: [...current.filteredEntries, ...entries],
    }));
  }

  setFilters(filters: Partial<LogFilterOptions>) {
    this.state.update((current) => ({
      ...current,
      filters: { ...current.filters, ...filters },
    }));
  }

  setOffset(offset: number) {
    this.setFilters({ offset });
  }

  clearEntries() {
    this.setState({ entries: [], filteredEntries: [] });
  }

  selectEntry(entry: LogEntry | null) {
    this.setState({ selectedEntry: entry });
  }

  setStreaming(streaming: boolean) {
    this.setState({ isStreaming: streaming });
  }

  setStreamError(error: string | null) {
    this.setState({ streamError: error });
  }

  setAutoScroll(autoScroll: boolean) {
    this.setState({ autoScroll });
  }

  setLoading(loading: boolean) {
    this.setState({ isLoading: loading });
  }
}
