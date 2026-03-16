import {ComponentFixture, TestBed} from '@angular/core/testing';
import {ComponentRef} from '@angular/core';
import {CalibrationStatisticsComponent} from './calibration-statistics.component';
import {CalibrationHistoryRecord, CalibrationStatistics} from '../../../../core/models/calibration.model';

const BASE_RECORD: CalibrationHistoryRecord = {
  id: 'r1',
  sensor_id: 'sensor-1',
  reference_sensor_id: 'ref',
  timestamp: '2026-01-01T10:00:00Z',
  fitness: 0.9,
  rmse: 0.02,
  quality: 'good',
  stages_used: [],
  pose_before: {x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0},
  pose_after:  {x: 1, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0},
  transformation_matrix: [],
  accepted: true,
  notes: '',
  source_sensor_id: 'lidar-A',
  processing_chain: ['lidar-A', 'crop-1', 'calib-1'],
  run_id: 'run-001',
};

const MOCK_RECORDS: CalibrationHistoryRecord[] = [
  {...BASE_RECORD, id: 'r1', source_sensor_id: 'lidar-A', accepted: true,  fitness: 0.9,  run_id: 'run-001', processing_chain: ['lidar-A', 'calib-1']},
  {...BASE_RECORD, id: 'r2', source_sensor_id: 'lidar-A', accepted: false, fitness: 0.7,  run_id: 'run-002', processing_chain: ['lidar-A', 'calib-1']},
  {...BASE_RECORD, id: 'r3', source_sensor_id: 'lidar-B', accepted: true,  fitness: 0.85, run_id: 'run-001', processing_chain: ['lidar-B', 'crop-1', 'calib-1']},
  // Legacy record
  {...BASE_RECORD, id: 'r4', source_sensor_id: undefined, accepted: false, fitness: 0.6,  run_id: undefined, processing_chain: undefined},
];

const MOCK_STATS: CalibrationStatistics = {
  sensor_id: 'sensor-1',
  total_attempts: 4,
  accepted_count: 2,
  avg_fitness: 0.8125,
  avg_rmse: 0.02,
  best_fitness: 0.9,
  best_rmse: 0.01,
};

describe('CalibrationStatisticsComponent', () => {
  let component: CalibrationStatisticsComponent;
  let componentRef: ComponentRef<CalibrationStatisticsComponent>;
  let fixture: ComponentFixture<CalibrationStatisticsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CalibrationStatisticsComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(CalibrationStatisticsComponent);
    component = fixture.componentInstance;
    componentRef = fixture.componentRef;
    componentRef.setInput('statistics', null);
    componentRef.setInput('historyRecords', []);
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  // --- bySensor computed ---

  it('should group records by source_sensor_id', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const stats = component.bySensor();
    const lidarA = stats.find((s) => s.sourceSensorId === 'lidar-A');
    const lidarB = stats.find((s) => s.sourceSensorId === 'lidar-B');
    expect(lidarA).not.toBe(undefined);
    expect(lidarB).not.toBe(undefined);
  });

  it('should correctly count attempts per source sensor', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const stats = component.bySensor();
    const lidarA = stats.find((s) => s.sourceSensorId === 'lidar-A')!;
    expect(lidarA.attempts).toBe(2);
    const lidarB = stats.find((s) => s.sourceSensorId === 'lidar-B')!;
    expect(lidarB.attempts).toBe(1);
  });

  it('should correctly count accepted results per source sensor', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const lidarA = component.bySensor().find((s) => s.sourceSensorId === 'lidar-A')!;
    expect(lidarA.acceptedCount).toBe(1); // r1 accepted, r2 rejected
  });

  it('should compute average fitness per source sensor', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const lidarA = component.bySensor().find((s) => s.sourceSensorId === 'lidar-A')!;
    expect(lidarA.avgFitness).toBeCloseTo((0.9 + 0.7) / 2, 5);
  });

  it('should compute average chain length', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const lidarB = component.bySensor().find((s) => s.sourceSensorId === 'lidar-B')!;
    expect(lidarB.avgChainLength).toBe(3); // ['lidar-B', 'crop-1', 'calib-1']
  });

  it('should group legacy records under __legacy__ key', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const legacy = component.bySensor().find((s) => s.sourceSensorId === '__legacy__');
    expect(legacy).not.toBe(undefined);
    expect(legacy!.attempts).toBe(1);
  });

  it('should sort by attempts descending', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const stats = component.bySensor();
    // lidar-A has 2, lidar-B has 1, __legacy__ has 1
    expect(stats[0].sourceSensorId).toBe('lidar-A');
  });

  it('should return empty array when no records', () => {
    componentRef.setInput('historyRecords', []);
    fixture.detectChanges();
    expect(component.bySensor().length).toBe(0);
  });

  // --- recentRuns computed ---

  it('should group records by run_id', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const runs = component.recentRuns();
    const runIds = runs.map((r) => r.runId);
    expect(runIds).toContain('run-001');
    expect(runIds).toContain('run-002');
  });

  it('should exclude records without run_id from recentRuns', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const runs = component.recentRuns();
    // r4 has no run_id
    expect(runs.length).toBe(2);
  });

  it('should count unique sensors per run', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const run001 = component.recentRuns().find((r) => r.runId === 'run-001')!;
    // r1 (sensor-1) and r3 (sensor-1) — same sensor_id
    expect(run001.sensorCount).toBe(1);
  });

  it('should count accepted results per run', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const run001 = component.recentRuns().find((r) => r.runId === 'run-001')!;
    expect(run001.acceptedCount).toBe(2); // r1 and r3 both accepted
  });

  it('should limit recentRuns to 10', () => {
    const manyRecords: CalibrationHistoryRecord[] = Array.from({length: 15}, (_, i) => ({
      ...BASE_RECORD,
      id: `r${i}`,
      run_id: `run-${i.toString().padStart(3, '0')}`,
      sensor_id: `sensor-${i}`,
    }));
    componentRef.setInput('historyRecords', manyRecords);
    fixture.detectChanges();
    expect(component.recentRuns().length).toBeLessThanOrEqual(10);
  });

  // --- avgChainLength ---

  it('should compute average chain length across new-format records', () => {
    // lidar-A records have chain length 2, lidar-B has 3
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    const avg = component.avgChainLength();
    expect(avg).not.toBe(null);
    // 3 records with chains: [2, 2, 3] = avg 7/3 ≈ 2.3
    expect(parseFloat(avg!)).toBeCloseTo(7 / 3, 1);
  });

  it('should return null when no new-format records exist', () => {
    componentRef.setInput('historyRecords', [{
      ...BASE_RECORD,
      processing_chain: undefined,
    }]);
    fixture.detectChanges();
    expect(component.avgChainLength()).toBe(null);
  });

  // --- legacyCount ---

  it('should count legacy records (no run_id and no source_sensor_id)', () => {
    componentRef.setInput('historyRecords', MOCK_RECORDS);
    fixture.detectChanges();
    expect(component.legacyCount()).toBe(1); // only r4
  });

  it('should return 0 when all records are new format', () => {
    componentRef.setInput('historyRecords', [MOCK_RECORDS[0], MOCK_RECORDS[1]]);
    fixture.detectChanges();
    expect(component.legacyCount()).toBe(0);
  });

  // --- filterByRun output ---

  it('should emit filterByRun event with run ID', () => {
    let emitted: string | undefined;
    component.filterByRun.subscribe((v) => (emitted = v));
    component.onFilterByRun('run-001');
    expect(emitted).toBe('run-001');
  });

  // --- getRunStatusVariant ---

  it('should return success when all sensors accepted', () => {
    const run = {runId: 'r', sensorCount: 2, acceptedCount: 2, avgFitness: 0.9};
    expect(component.getRunStatusVariant(run)).toBe('success');
  });

  it('should return warning when some sensors accepted', () => {
    const run = {runId: 'r', sensorCount: 2, acceptedCount: 1, avgFitness: 0.8};
    expect(component.getRunStatusVariant(run)).toBe('warning');
  });

  it('should return neutral when no sensors accepted', () => {
    const run = {runId: 'r', sensorCount: 2, acceptedCount: 0, avgFitness: 0.5};
    expect(component.getRunStatusVariant(run)).toBe('neutral');
  });

  // --- getRunLabel ---

  it('should return "All accepted" when all sensors accepted', () => {
    const run = {runId: 'r', sensorCount: 2, acceptedCount: 2, avgFitness: null};
    expect(component.getRunLabel(run)).toBe('All accepted');
  });

  it('should return partial count when some accepted', () => {
    const run = {runId: 'r', sensorCount: 3, acceptedCount: 1, avgFitness: null};
    expect(component.getRunLabel(run)).toBe('1/3 accepted');
  });

  it('should return "Not accepted" when none accepted', () => {
    const run = {runId: 'r', sensorCount: 2, acceptedCount: 0, avgFitness: null};
    expect(component.getRunLabel(run)).toBe('Not accepted');
  });
});
