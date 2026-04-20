import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { PlaybackNodeCardComponent } from './playback-node-card.component';
import { NodeStatusUpdate } from '@core/models/node-status.model';
import { CanvasNode } from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';

const PLAYBACK_NODE: CanvasNode = {
  id: 'node-playback-001',
  type: 'playback',
  data: {
    id: 'node-playback-001',
    name: 'Playback',
    type: 'playback',
    category: 'sensor',
    enabled: true,
    config: {
      recording_id: 'demo0001demo0001demo0001demo0001',
      playback_speed: 1.0,
      loopable: false,
      throttle_ms: 0,
    },
    x: 100,
    y: 100,
  },
  position: { x: 100, y: 100 },
};

function makeStatus(
  operationalState: string,
  appValue: string = '',
  color: string = 'gray',
): NodeStatusUpdate {
  return {
    node_id: 'node-playback-001',
    name: 'Playback',
    type: 'playback',
    enabled: true,
    operational_state: operationalState,
    application_state: { label: 'playback_status', value: appValue, color },
    error_message: undefined,
    timestamp: Date.now(),
  } as NodeStatusUpdate;
}

describe('PlaybackNodeCardComponent', () => {
  let component: PlaybackNodeCardComponent;
  let fixture: ComponentFixture<PlaybackNodeCardComponent>;

  async function createComponent(statusOverride: NodeStatusUpdate | null = null) {
    await TestBed.configureTestingModule({
      imports: [PlaybackNodeCardComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(PlaybackNodeCardComponent);
    component = fixture.componentInstance;

    fixture.componentRef.setInput('node', PLAYBACK_NODE);
    fixture.componentRef.setInput('status', statusOverride);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  describe('creation', () => {
    it('should create', async () => {
      await createComponent();
      expect(component).toBeTruthy();
    });
  });

  describe('playbackBadge() computed', () => {
    it('should return PLAYING badge when RUNNING', async () => {
      await createComponent(makeStatus('RUNNING', 'playing (frame 42/300)', 'green'));
      const badge = component['playbackBadge']();
      expect(badge).not.toBeNull();
      expect(badge!.text).toContain('PLAYING');
      expect(badge!.cssClass).toContain('text-syn-color-success');
    });

    it('should show frame info from application_state.value', async () => {
      await createComponent(makeStatus('RUNNING', 'playing (frame 42/300)', 'green'));
      const badge = component['playbackBadge']();
      expect(badge!.text).toContain('frame 42/300');
    });

    it('should return IDLE badge when STOPPED', async () => {
      await createComponent(makeStatus('STOPPED', 'idle', 'gray'));
      const badge = component['playbackBadge']();
      expect(badge!.text).toContain('IDLE');
      expect(badge!.cssClass).toContain('text-syn-color-neutral');
    });

    it('should return ERROR badge when ERROR', async () => {
      await createComponent({
        ...makeStatus('ERROR', 'file not found', 'red'),
        error_message: 'Recording file not found',
      } as NodeStatusUpdate);
      const badge = component['playbackBadge']();
      expect(badge!.text).toContain('ERROR');
      expect(badge!.cssClass).toContain('text-syn-color-danger');
    });

    it('should return null when status is null', async () => {
      await createComponent(null);
      expect(component['playbackBadge']()).toBeNull();
    });
  });

  describe('config accessors', () => {
    it('should expose recordingId from node config', async () => {
      await createComponent();
      expect(component['recordingId']()).toBe('demo0001demo0001demo0001demo0001');
    });

    it('should expose playbackSpeed from node config', async () => {
      await createComponent();
      expect(component['playbackSpeed']()).toBe(1.0);
    });

    it('should expose loopable from node config', async () => {
      await createComponent();
      expect(component['loopable']()).toBe(false);
    });
  });
});
