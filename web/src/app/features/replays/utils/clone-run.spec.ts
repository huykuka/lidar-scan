import {ReplayRun} from '@core/models';
import {runToPrefill} from './clone-run';

const run = (extra: Partial<ReplayRun>): ReplayRun =>
  ({
    id: 'r1', label: 'baseline', recording_id: 'rec', playback_node_id: 'pb',
    overrides: {}, capture_nodes: null, ...extra,
  }) as ReplayRun;

describe('runToPrefill', () => {
  it('carries over recording, playback node and a re-run label', () => {
    const p = runToPrefill(run({}));
    expect(p).toEqual({
      label: 'baseline (re-run)', recordingId: 'rec', playbackNodeId: 'pb', overrides: [], captureNodes: null,
    });
  });

  it('flattens overrides into rows with the text a user would type', () => {
    const p = runToPrefill(run({overrides: {n1: {radius: 1.5, enabled: true}, n2: {bounds: [1, 2]}}}));
    expect(p.overrides).toEqual([
      {nodeId: 'n1', key: 'radius', value: '1.5'},
      {nodeId: 'n1', key: 'enabled', value: 'true'},
      {nodeId: 'n2', key: 'bounds', value: '[1,2]'},
    ]);
  });

  it('keeps the exact set of captured nodes, including none', () => {
    expect(runToPrefill(run({capture_nodes: ['a', 'b']})).captureNodes).toEqual(['a', 'b']);
    expect(runToPrefill(run({capture_nodes: []})).captureNodes).toEqual([]);
  });

  it('does not invent a label for an unnamed run', () => {
    expect(runToPrefill(run({label: ''})).label).toBe('');
  });
});
