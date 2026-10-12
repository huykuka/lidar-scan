import {ReplayRun} from '@core/models';
import {formatOverrideValue} from './override-values';

/** Everything the new-replay form needs to start from an earlier run. */
export interface ReplayPrefill {
  label: string;
  recordingId: string;
  playbackNodeId: string;
  overrides: {nodeId: string; key: string; value: string}[];
  /** null = the run predates capture tracking; keep the form default. */
  captureNodes: string[] | null;
}

/** Turn a finished run into form values so the engineer can tweak and re-run it. */
export function runToPrefill(run: ReplayRun): ReplayPrefill {
  const overrides = Object.entries(run.overrides ?? {}).flatMap(([nodeId, params]) =>
    Object.entries(params).map(([key, value]) => ({nodeId, key, value: formatOverrideValue(value)})),
  );
  return {
    label: run.label ? `${run.label} (re-run)` : '',
    recordingId: run.recording_id,
    playbackNodeId: run.playback_node_id,
    overrides,
    captureNodes: run.capture_nodes ?? null,
  };
}
