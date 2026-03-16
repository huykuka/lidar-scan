import {ComponentFixture, TestBed} from '@angular/core/testing';
import {ComponentRef} from '@angular/core';
import {CalibrationAcceptDialogComponent} from './calibration-accept-dialog.component';
import {CalibrationNodeStatus} from '../../../../core/models/calibration.model';

const MOCK_NODE_STATUS: CalibrationNodeStatus = {
  id: 'calib-1',
  name: 'Calibration Node',
  type: 'calibration',
  enabled: true,
  reference_sensor: 'ref-sensor',
  source_sensors: ['lidar-A', 'lidar-B'],
  buffered_frames: {'lidar-A': 10, 'lidar-B': 8},
  last_calibration_time: null,
  has_pending: true,
  pending_results: {
    'sensor-A': {
      fitness: 0.95,
      rmse: 0.01,
      quality: 'excellent',
      source_sensor_id: 'lidar-A',
      processing_chain: ['lidar-A', 'crop-1', 'calib-1'],
    },
    'sensor-B': {
      fitness: 0.82,
      rmse: 0.03,
      quality: 'good',
      source_sensor_id: 'lidar-B',
      processing_chain: ['lidar-B', 'calib-1'],
    },
  },
};

const MOCK_LEGACY_NODE: CalibrationNodeStatus = {
  ...MOCK_NODE_STATUS,
  pending_results: {
    'sensor-A': {
      fitness: 0.9,
      rmse: 0.02,
      quality: 'good',
      // No source_sensor_id or processing_chain
    },
  },
};

describe('CalibrationAcceptDialogComponent', () => {
  let component: CalibrationAcceptDialogComponent;
  let componentRef: ComponentRef<CalibrationAcceptDialogComponent>;
  let fixture: ComponentFixture<CalibrationAcceptDialogComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CalibrationAcceptDialogComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(CalibrationAcceptDialogComponent);
    component = fixture.componentInstance;
    componentRef = fixture.componentRef;
    componentRef.setInput('open', false);
    componentRef.setInput('nodeStatus', null);
    componentRef.setInput('runId', null);
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  // --- pendingResultsList ---

  it('should compute pending results list from node status', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();
    const list = component.pendingResultsList();
    expect(list.length).toBe(2);
    const sensorIds = list.map((r) => r.sensorId);
    expect(sensorIds).toContain('sensor-A');
    expect(sensorIds).toContain('sensor-B');
  });

  it('should return empty list when nodeStatus is null', () => {
    componentRef.setInput('nodeStatus', null);
    fixture.detectChanges();
    expect(component.pendingResultsList().length).toBe(0);
  });

  it('should include provenance fields in result entries', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();
    const sensorA = component.pendingResultsList().find((r) => r.sensorId === 'sensor-A');
    expect(sensorA?.source_sensor_id).toBe('lidar-A');
    expect(sensorA?.processing_chain).toEqual(['lidar-A', 'crop-1', 'calib-1']);
  });

  it('should handle legacy pending results without provenance fields', () => {
    componentRef.setInput('nodeStatus', MOCK_LEGACY_NODE);
    fixture.detectChanges();
    const list = component.pendingResultsList();
    expect(list.length).toBe(1);
    expect(list[0].source_sensor_id).toBe(undefined);
    expect(list[0].processing_chain).toBe(undefined);
  });

  // --- sensor selection logic ---

  it('should handle sensor toggle correctly', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();

    // Manually seed selected sensors (as constructor setTimeout may not have fired)
    component.selectedSensors.set(new Set(['sensor-A', 'sensor-B']));

    component.toggleSensor('sensor-A');
    expect(component.selectedSensors().has('sensor-A')).toBe(false);
    expect(component.selectedSensors().has('sensor-B')).toBe(true);
  });

  it('should re-add sensor on second toggle', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();
    component.selectedSensors.set(new Set(['sensor-B']));
    component.toggleSensor('sensor-B');
    expect(component.selectedSensors().has('sensor-B')).toBe(false);
    component.toggleSensor('sensor-B');
    expect(component.selectedSensors().has('sensor-B')).toBe(true);
  });

  it('should select all sensors via toggleAll when none are selected', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();
    component.selectedSensors.set(new Set());
    component.toggleAll();
    expect(component.selectedSensors().has('sensor-A')).toBe(true);
    expect(component.selectedSensors().has('sensor-B')).toBe(true);
  });

  it('should deselect all sensors via toggleAll when all are selected', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();
    component.selectedSensors.set(new Set(['sensor-A', 'sensor-B']));
    component.toggleAll();
    expect(component.selectedSensors().size).toBe(0);
  });

  it('isSensorSelected should return correct boolean', () => {
    component.selectedSensors.set(new Set(['sensor-A']));
    expect(component.isSensorSelected('sensor-A')).toBe(true);
    expect(component.isSensorSelected('sensor-B')).toBe(false);
  });

  // --- onAccept output ---

  it('should emit null when all sensors are selected (accept all)', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();
    component.selectedSensors.set(new Set(['sensor-A', 'sensor-B']));

    let emitted: string[] | null | undefined;
    component.accepted.subscribe((v) => (emitted = v));
    component.onAccept();
    expect(emitted).toBe(null);
  });

  it('should emit selected sensor IDs when subset is chosen', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();
    component.selectedSensors.set(new Set(['sensor-A']));

    let emitted: string[] | null | undefined;
    component.accepted.subscribe((v) => (emitted = v));
    component.onAccept();
    expect(emitted).toEqual(['sensor-A']);
  });

  // --- onReject output ---

  it('should emit rejected event when onReject is called', () => {
    let emitted = false;
    component.rejected.subscribe(() => (emitted = true));
    component.onReject();
    expect(emitted).toBe(true);
  });

  // --- onClose output ---

  it('should emit closed event when onClose is called', () => {
    let emitted = false;
    component.closed.subscribe(() => (emitted = true));
    component.onClose();
    expect(emitted).toBe(true);
  });

  // --- helper methods ---

  it('getQualityVariant should return correct variant for each quality level', () => {
    expect(component.getQualityVariant('excellent')).toBe('success');
    expect(component.getQualityVariant('good')).toBe('warning');
    expect(component.getQualityVariant('poor')).toBe('danger');
    expect(component.getQualityVariant(null)).toBe('neutral');
    expect(component.getQualityVariant(undefined)).toBe('neutral');
    expect(component.getQualityVariant('unknown')).toBe('neutral');
  });

  it('shortRunId should truncate long run IDs', () => {
    const result = component.shortRunId('a3f2b1c4-dead-beef-1234-567890abcdef');
    expect(result.length).toBeLessThan(40);
    expect(result).toContain('…');
  });

  it('shortRunId should return em dash for null run ID', () => {
    expect(component.shortRunId(null)).toBe('—');
    expect(component.shortRunId(undefined)).toBe('—');
  });

  it('shortId should truncate long sensor IDs', () => {
    const longId = 'very-long-lidar-sensor-id-12345678';
    const result = component.shortId(longId);
    expect(result.length).toBeLessThan(longId.length);
    expect(result).toContain('…');
  });

  it('shortId should return em dash for null/undefined', () => {
    expect(component.shortId(null)).toBe('—');
    expect(component.shortId(undefined)).toBe('—');
  });

  // --- allSelected computed ---

  it('allSelected should be true when all pending sensors are selected', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();
    component.selectedSensors.set(new Set(['sensor-A', 'sensor-B']));
    expect(component.allSelected()).toBe(true);
  });

  it('allSelected should be false when subset is selected', () => {
    componentRef.setInput('nodeStatus', MOCK_NODE_STATUS);
    fixture.detectChanges();
    component.selectedSensors.set(new Set(['sensor-A']));
    expect(component.allSelected()).toBe(false);
  });

  it('allSelected should be false when no results', () => {
    componentRef.setInput('nodeStatus', null);
    fixture.detectChanges();
    expect(component.allSelected()).toBe(false);
  });
});
