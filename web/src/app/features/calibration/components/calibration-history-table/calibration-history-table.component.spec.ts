import {ComponentFixture, TestBed} from '@angular/core/testing';
import {ComponentRef} from '@angular/core';
import {CalibrationHistoryTableComponent} from './calibration-history-table.component';
import {CalibrationHistoryRecord} from '../../../../core/models/calibration.model';

const BASE_RECORD: CalibrationHistoryRecord = {
  id: 'rec-1',
  sensor_id: 'sensor-1',
  reference_sensor_id: 'ref-1',
  timestamp: '2026-01-01T10:00:00Z',
  fitness: 0.95,
  rmse: 0.01,
  quality: 'excellent',
  stages_used: ['icp'],
  pose_before: {x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0},
  pose_after:  {x: 1, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0},
  transformation_matrix: [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
  accepted: true,
  notes: '',
};

const MOCK_NEW_RECORD: CalibrationHistoryRecord = {
  ...BASE_RECORD,
  id: 'rec-new',
  source_sensor_id: 'lidar-A',
  processing_chain: ['lidar-A', 'crop-1', 'calibration-1'],
  run_id: 'run-abc123',
};

const MOCK_NEW_RECORD_2: CalibrationHistoryRecord = {
  ...BASE_RECORD,
  id: 'rec-new-2',
  sensor_id: 'sensor-2',
  source_sensor_id: 'lidar-B',
  processing_chain: ['lidar-B', 'calibration-1'],
  run_id: 'run-xyz789',
  timestamp: '2026-01-02T10:00:00Z',
};

const MOCK_LEGACY_RECORD: CalibrationHistoryRecord = {
  ...BASE_RECORD,
  id: 'rec-legacy',
  source_sensor_id: undefined,
  processing_chain: undefined,
  run_id: undefined,
};

describe('CalibrationHistoryTableComponent', () => {
  let component: CalibrationHistoryTableComponent;
  let componentRef: ComponentRef<CalibrationHistoryTableComponent>;
  let fixture: ComponentFixture<CalibrationHistoryTableComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CalibrationHistoryTableComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(CalibrationHistoryTableComponent);
    component = fixture.componentInstance;
    componentRef = fixture.componentRef;
    componentRef.setInput('records', []);
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  // --- filteredRecords ---

  it('should return all records when no filter is active', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD, MOCK_NEW_RECORD_2, MOCK_LEGACY_RECORD]);
    fixture.detectChanges();
    expect(component.filteredRecords().length).toBe(3);
  });

  it('should filter by source_sensor_id', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD, MOCK_NEW_RECORD_2, MOCK_LEGACY_RECORD]);
    fixture.detectChanges();
    component.filterSourceSensor.set('lidar-A');
    fixture.detectChanges();
    const results = component.filteredRecords();
    expect(results.length).toBe(1);
    expect(results[0].id).toBe('rec-new');
  });

  it('should filter by run_id', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD, MOCK_NEW_RECORD_2, MOCK_LEGACY_RECORD]);
    fixture.detectChanges();
    component.filterRunId.set('run-xyz789');
    fixture.detectChanges();
    const results = component.filteredRecords();
    expect(results.length).toBe(1);
    expect(results[0].id).toBe('rec-new-2');
  });

  it('should apply both source sensor and run_id filters simultaneously', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD, MOCK_NEW_RECORD_2, MOCK_LEGACY_RECORD]);
    fixture.detectChanges();
    component.filterSourceSensor.set('lidar-A');
    component.filterRunId.set('run-abc123');
    fixture.detectChanges();
    expect(component.filteredRecords().length).toBe(1);
  });

  it('should return empty array when no records match the filter', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD, MOCK_LEGACY_RECORD]);
    fixture.detectChanges();
    component.filterRunId.set('nonexistent-run');
    fixture.detectChanges();
    expect(component.filteredRecords().length).toBe(0);
  });

  it('should sort records newest first', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD, MOCK_NEW_RECORD_2]); // rec-new is Jan 1, rec-new-2 is Jan 2
    fixture.detectChanges();
    const results = component.filteredRecords();
    expect(results[0].id).toBe('rec-new-2'); // Jan 2 first
    expect(results[1].id).toBe('rec-new');
  });

  // --- uniqueSourceSensors ---

  it('should compute unique source sensor IDs excluding nulls', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD, MOCK_NEW_RECORD_2, MOCK_LEGACY_RECORD]);
    fixture.detectChanges();
    const unique = component.uniqueSourceSensors();
    expect(unique).toContain('lidar-A');
    expect(unique).toContain('lidar-B');
    expect(unique.length).toBe(2); // Legacy record excluded
  });

  it('should return empty array when all records are legacy', () => {
    componentRef.setInput('records', [MOCK_LEGACY_RECORD]);
    fixture.detectChanges();
    expect(component.uniqueSourceSensors().length).toBe(0);
  });

  // --- hasActiveFilters ---

  it('should be false when no filters are set', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD]);
    fixture.detectChanges();
    expect(component.hasActiveFilters()).toBe(false);
  });

  it('should be true when source sensor filter is set', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD]);
    fixture.detectChanges();
    component.filterSourceSensor.set('lidar-A');
    expect(component.hasActiveFilters()).toBe(true);
  });

  it('should be true when run_id filter is set', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD]);
    fixture.detectChanges();
    component.filterRunId.set('run-abc123');
    expect(component.hasActiveFilters()).toBe(true);
  });

  // --- clearFilters ---

  it('should clear all filters', () => {
    componentRef.setInput('records', [MOCK_NEW_RECORD]);
    fixture.detectChanges();
    component.filterSourceSensor.set('lidar-A');
    component.filterRunId.set('run-abc123');
    component.clearFilters();
    expect(component.hasActiveFilters()).toBe(false);
    expect(component.filterSourceSensor()).toBe('');
    expect(component.filterRunId()).toBe('');
  });

  // --- isLegacyRecord ---

  it('should identify legacy records (no run_id and no source_sensor_id)', () => {
    expect(component.isLegacyRecord(MOCK_LEGACY_RECORD)).toBe(true);
  });

  it('should not mark records with run_id as legacy', () => {
    expect(component.isLegacyRecord(MOCK_NEW_RECORD)).toBe(false);
  });

  it('should not mark records with only source_sensor_id as legacy', () => {
    const partial = {...MOCK_LEGACY_RECORD, source_sensor_id: 'lidar-A'};
    expect(component.isLegacyRecord(partial)).toBe(false);
  });

  // --- getChainLength ---

  it('should return chain length for new records', () => {
    expect(component.getChainLength(MOCK_NEW_RECORD)).toBe(3);
  });

  it('should return 0 for legacy records with no chain', () => {
    expect(component.getChainLength(MOCK_LEGACY_RECORD)).toBe(0);
  });

  // --- shortId ---

  it('should truncate long IDs', () => {
    const result = component.shortId('very-long-sensor-id-1234567890');
    expect(result.length).toBeLessThan('very-long-sensor-id-1234567890'.length);
    expect(result).toContain('…');
  });

  it('should return em dash for null/undefined IDs', () => {
    expect(component.shortId(null)).toBe('—');
    expect(component.shortId(undefined)).toBe('—');
  });

  it('should return short IDs unchanged', () => {
    expect(component.shortId('short')).toBe('short');
  });

  // --- output emissions ---

  it('should emit filterByRunId when run_id is clicked', () => {
    let emitted: string | undefined;
    component.filterByRunId.subscribe((v) => (emitted = v));
    component.onRunIdClick('run-abc123');
    expect(emitted).toBe('run-abc123');
  });

  it('should also set filterRunId signal when run_id is clicked', () => {
    component.onRunIdClick('run-abc123');
    expect(component.filterRunId()).toBe('run-abc123');
  });

  it('should emit viewDetail when a record row is clicked', () => {
    let emitted: CalibrationHistoryRecord | undefined;
    component.viewDetail.subscribe((v) => (emitted = v));
    component.onViewDetail(MOCK_NEW_RECORD);
    expect(emitted).toEqual(MOCK_NEW_RECORD);
  });

  // --- backward compatibility: legacy records render without errors ---

  it('should render without errors when all records are legacy', () => {
    componentRef.setInput('records', [MOCK_LEGACY_RECORD]);
    expect(() => fixture.detectChanges()).not.toThrow();
  });
});
