import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component, ElementRef, signal, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { LogsTableComponent } from './logs-table.component';
import { LogEntry } from '@core/models';

// Mock LogEntry for testing (without 'id' field as it doesn't exist in the model)
const createMockLogEntry = (overrides: Partial<LogEntry> = {}): LogEntry => ({
  timestamp: '2026-03-12T10:30:00.000Z',
  level: 'INFO',
  module: 'test-module',
  message: 'Test message',
  ...overrides,
});

// Test wrapper component to simulate the parent container
@Component({
  template: `
    <div class="h-screen flex flex-col">
      <div class="flex-1 min-h-0 overflow-hidden flex flex-col">
        <app-logs-table
          [entries]="entries()"
          [selectedEntry]="selectedEntry()"
          [isLoading]="isLoading()"
          [isLoadingMore]="isLoadingMore()"
          [autoScroll]="autoScroll()"
          [isStreaming]="isStreaming()"
          (entrySelected)="onEntrySelected($event)"
          (loadMoreClicked)="onLoadMoreClicked()"
        />
      </div>
    </div>
  `,
})
class TestWrapperComponent {
  entries = signal<LogEntry[]>([]);
  selectedEntry = signal<LogEntry | null>(null);
  isLoading = signal<boolean>(false);
  isLoadingMore = signal<boolean>(false);
  autoScroll = signal<boolean>(true);
  isStreaming = signal<boolean>(false);

  onEntrySelected = jest.fn();
  onLoadMoreClicked = jest.fn();
}

describe('LogsTableComponent - Scroll Enhancement Tests', () => {
  let component: LogsTableComponent;
  let fixture: ComponentFixture<TestWrapperComponent>;
  let wrapperComponent: TestWrapperComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LogsTableComponent],
      declarations: [TestWrapperComponent],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(TestWrapperComponent);
    wrapperComponent = fixture.componentInstance;
    
    const logsTableElement = fixture.debugElement.query(
      debugEl => debugEl.componentInstance instanceof LogsTableComponent
    );
    component = logsTableElement.componentInstance;
    
    fixture.detectChanges();
  });

  describe('Phase 1: Host Element CSS Classes', () => {
    it('should apply correct host CSS classes for flex participation', () => {
      const hostElement = fixture.debugElement.query(
        debugEl => debugEl.componentInstance instanceof LogsTableComponent
      ).nativeElement;

      // Verify host element has the required classes
      expect(hostElement.classList.contains('flex')).toBe(true);
      expect(hostElement.classList.contains('flex-col')).toBe(true);
      expect(hostElement.classList.contains('flex-1')).toBe(true);
      expect(hostElement.classList.contains('min-h-0')).toBe(true);
      expect(hostElement.classList.contains('overflow-hidden')).toBe(true);
    });

    it('should participate in flex height chain correctly', () => {
      const hostElement = fixture.debugElement.query(
        debugEl => debugEl.componentInstance instanceof LogsTableComponent
      ).nativeElement;

      const computedStyle = getComputedStyle(hostElement);
      expect(computedStyle.display).toBe('flex');
      expect(computedStyle.flexDirection).toBe('column');
      expect(computedStyle.flexGrow).toBe('1');
      expect(computedStyle.minHeight).toBe('0px');
      expect(computedStyle.overflow).toBe('hidden');
    });
  });

  describe('Phase 2: Scroll Container', () => {
    it('should have scroll container with correct CSS classes', () => {
      const scrollContainer = fixture.debugElement.nativeElement.querySelector('[data-testid="scroll-container"]') ||
                            fixture.debugElement.nativeElement.querySelector('#scrollContainer') ||
                            fixture.debugElement.nativeElement.querySelector('div[role="region"]');

      expect(scrollContainer).toBeTruthy();
      expect(scrollContainer.classList.contains('flex-1')).toBe(true);
      expect(scrollContainer.classList.contains('min-h-0')).toBe(true);
      expect(scrollContainer.classList.contains('overflow-y-auto')).toBe(true);
      expect(scrollContainer.classList.contains('overflow-x-hidden')).toBe(true);
      expect(scrollContainer.classList.contains('relative')).toBe(true);
      expect(scrollContainer.classList.contains('syn-scrollbar')).toBe(true);
    });

    it('should have correct accessibility attributes', () => {
      const scrollContainer = fixture.debugElement.nativeElement.querySelector('div[role="region"]');

      expect(scrollContainer).toBeTruthy();
      expect(scrollContainer.getAttribute('role')).toBe('region');
      expect(scrollContainer.getAttribute('aria-label')).toBe('Log entries');
      expect(scrollContainer.getAttribute('tabindex')).toBe('0');
    });

    it('should have focus styling classes', () => {
      const scrollContainer = fixture.debugElement.nativeElement.querySelector('div[role="region"]');

      expect(scrollContainer.classList.contains('focus:outline-none')).toBe(true);
      expect(scrollContainer.classList.contains('focus-visible:ring-2')).toBe(true);
      expect(scrollContainer.classList.contains('focus-visible:ring-syn-color-primary-300')).toBe(true);
    });

    it('should be keyboard focusable', () => {
      const scrollContainer = fixture.debugElement.nativeElement.querySelector('div[role="region"]');
      
      scrollContainer.focus();
      expect(document.activeElement).toBe(scrollContainer);
    });
  });

  describe('Phase 3: Auto-Scroll Signal Inputs', () => {
    it('should accept autoScroll input signal', () => {
      expect(component.autoScroll).toBeDefined();
      expect(component.autoScroll()).toBe(true); // Default value from wrapper
    });

    it('should accept isStreaming input signal', () => {
      expect(component.isStreaming).toBeDefined();
      expect(component.isStreaming()).toBe(false); // Default value from wrapper
    });

    it('should have scrollContainer viewChild reference', () => {
      expect(component.scrollContainer).toBeDefined();
      
      const scrollContainerRef = component.scrollContainer();
      expect(scrollContainerRef).toBeInstanceOf(ElementRef);
      expect(scrollContainerRef?.nativeElement.tagName).toBe('DIV');
    });
  });

  describe('Phase 4: Auto-Scroll Functionality', () => {
    beforeEach(() => {
      // Set up test data with multiple entries
      const mockEntries = Array.from({ length: 10 }, (_, i) => 
        createMockLogEntry({
          timestamp: `2026-03-12T10:${30 + i}:00.000Z`,
          message: `Test message ${i}`,
        })
      );
      wrapperComponent.entries.set(mockEntries);
      fixture.detectChanges();
    });

    it('should scroll to top when new entries are added during streaming with autoScroll enabled', async () => {
      // Enable streaming and auto-scroll
      wrapperComponent.isStreaming.set(true);
      wrapperComponent.autoScroll.set(true);
      fixture.detectChanges();

      const scrollContainer = component.scrollContainer()?.nativeElement;
      expect(scrollContainer).toBeTruthy();

      // Manually scroll down to simulate user scrolling
      scrollContainer!.scrollTop = 200;
      expect(scrollContainer!.scrollTop).toBe(200);

      // Add new entries (simulating live streaming)
      const newEntries = [
        createMockLogEntry({ message: 'New entry 1' }),
        ...wrapperComponent.entries(),
      ];
      wrapperComponent.entries.set(newEntries);
      fixture.detectChanges();

      // Wait for effect to run
      await fixture.whenStable();

      // Should auto-scroll to top
      expect(scrollContainer!.scrollTop).toBe(0);
    });

    it('should NOT auto-scroll when streaming is disabled', async () => {
      wrapperComponent.isStreaming.set(false);
      wrapperComponent.autoScroll.set(true);
      fixture.detectChanges();

      const scrollContainer = component.scrollContainer()?.nativeElement;
      scrollContainer!.scrollTop = 200;

      const newEntries = [
        createMockLogEntry({ message: 'New entry 1' }),
        ...wrapperComponent.entries(),
      ];
      wrapperComponent.entries.set(newEntries);
      fixture.detectChanges();

      await fixture.whenStable();

      // Should preserve scroll position
      expect(scrollContainer!.scrollTop).toBe(200);
    });

    it('should NOT auto-scroll when autoScroll is disabled', async () => {
      wrapperComponent.isStreaming.set(true);
      wrapperComponent.autoScroll.set(false);
      fixture.detectChanges();

      const scrollContainer = component.scrollContainer()?.nativeElement;
      scrollContainer!.scrollTop = 200;

      const newEntries = [
        createMockLogEntry({ message: 'New entry 1' }),
        ...wrapperComponent.entries(),
      ];
      wrapperComponent.entries.set(newEntries);
      fixture.detectChanges();

      await fixture.whenStable();

      // Should preserve scroll position
      expect(scrollContainer!.scrollTop).toBe(200);
    });
  });

  describe('Phase 5: Sticky Headers', () => {
    beforeEach(() => {
      // Add enough entries to cause scrolling
      const mockEntries = Array.from({ length: 100 }, (_, i) => 
        createMockLogEntry({
          message: `Long test message ${i} that might cause the table to scroll`,
        })
      );
      wrapperComponent.entries.set(mockEntries);
      fixture.detectChanges();
    });

    it('should have sticky header cells with correct positioning', () => {
      const headerCells = fixture.debugElement.nativeElement.querySelectorAll('th');
      
      headerCells.forEach((th: HTMLElement) => {
        expect(th.classList.contains('sticky')).toBe(true);
        expect(th.classList.contains('top-0')).toBe(true);
        expect(th.classList.contains('z-20')).toBe(true);
        
        const computedStyle = getComputedStyle(th);
        expect(computedStyle.position).toBe('sticky');
        expect(computedStyle.top).toBe('0px');
      });
    });

    it('should not have border-collapse on table element', () => {
      const tableElement = fixture.debugElement.nativeElement.querySelector('table');
      
      const computedStyle = getComputedStyle(tableElement);
      expect(computedStyle.borderCollapse).toBe('separate');
    });
  });

  describe('Phase 6: Table Content and Load More', () => {
    it('should render table rows correctly', () => {
      const mockEntries = [
        createMockLogEntry({ level: 'INFO', message: 'Test info message' }),
        createMockLogEntry({ level: 'ERROR', message: 'Test error message' }),
      ];
      wrapperComponent.entries.set(mockEntries);
      fixture.detectChanges();

      const tableRows = fixture.debugElement.nativeElement.querySelectorAll('tbody tr');
      expect(tableRows.length).toBe(2);
    });

    it('should show Load More button when entries exist', () => {
      const mockEntries = [createMockLogEntry()];
      wrapperComponent.entries.set(mockEntries);
      fixture.detectChanges();

      const loadMoreButton = fixture.debugElement.nativeElement.querySelector('syn-button');
      expect(loadMoreButton).toBeTruthy();
    });

    it('should emit loadMoreClicked when Load More button is clicked', () => {
      const mockEntries = [createMockLogEntry()];
      wrapperComponent.entries.set(mockEntries);
      fixture.detectChanges();

      const loadMoreButton = fixture.debugElement.nativeElement.querySelector('syn-button');
      loadMoreButton.click();

      expect(wrapperComponent.onLoadMoreClicked).toHaveBeenCalled();
    });
  });

  describe('Phase 7: Error States and Loading', () => {
    it('should show loading spinner when isLoading is true and no entries', () => {
      wrapperComponent.isLoading.set(true);
      wrapperComponent.entries.set([]);
      fixture.detectChanges();

      const spinner = fixture.debugElement.nativeElement.querySelector('syn-spinner[size="large"]');
      expect(spinner).toBeTruthy();
    });

    it('should show empty state when not loading and no entries', () => {
      wrapperComponent.isLoading.set(false);
      wrapperComponent.entries.set([]);
      fixture.detectChanges();

      const emptyMessage = fixture.debugElement.nativeElement.textContent;
      expect(emptyMessage).toContain('No log entries found');
    });

    it('should show loading overlay when isLoading is true with entries', () => {
      const mockEntries = [createMockLogEntry()];
      wrapperComponent.entries.set(mockEntries);
      wrapperComponent.isLoading.set(true);
      fixture.detectChanges();

      const loadingOverlay = fixture.debugElement.nativeElement.querySelector('.absolute.inset-0');
      expect(loadingOverlay).toBeTruthy();
    });
  });

  describe('Phase 8: Integration with Parent Component', () => {
    it('should emit entrySelected when row is clicked', () => {
      const mockEntry = createMockLogEntry({ message: 'Clickable entry' });
      wrapperComponent.entries.set([mockEntry]);
      fixture.detectChanges();

      const tableRow = fixture.debugElement.nativeElement.querySelector('tbody tr');
      tableRow.click();

      expect(wrapperComponent.onEntrySelected).toHaveBeenCalledWith(mockEntry);
    });

    it('should highlight selected entry', () => {
      const mockEntry = createMockLogEntry({ message: 'Selected entry' });
      wrapperComponent.entries.set([mockEntry]);
      wrapperComponent.selectedEntry.set(mockEntry);
      fixture.detectChanges();

      const tableRow = fixture.debugElement.nativeElement.querySelector('tbody tr');
      expect(tableRow.classList.contains('bg-syn-color-blue-50')).toBe(true);
    });
  });
});