import {computed, inject, Injectable, OnDestroy} from '@angular/core';
import {SignalsSimpleStoreService} from '../signals-simple-store.service';
import {CalibrationApiService} from '../api/calibration-api.service';
import {
  CalibrationAcceptRequest,
  CalibrationHistoryRecord,
  CalibrationNodeStatusResponse,
  CalibrationTriggerRequest,
} from '../../models/calibration.model';

export interface CalibrationState {
  nodeStatuses: Record<string, CalibrationNodeStatusResponse>;
  pollingNodeId: string | null;
  historyByNode: Record<string, CalibrationHistoryRecord[]>;
  isLoadingStatus: boolean;
  isLoadingHistory: boolean;
  isTriggering: boolean;
  isAccepting: boolean;
  isRejecting: boolean;
  isRollingBack: boolean;
  error: string | null;
}

const INITIAL_STATE: CalibrationState = {
  nodeStatuses: {},
  pollingNodeId: null,
  historyByNode: {},
  isLoadingStatus: false,
  isLoadingHistory: false,
  isTriggering: false,
  isAccepting: false,
  isRejecting: false,
  isRollingBack: false,
  error: null,
};

@Injectable({
  providedIn: 'root',
})
export class CalibrationStoreService
  extends SignalsSimpleStoreService<CalibrationState>
  implements OnDestroy
{
  // ── Selectors ────────────────────────────────────────────────────────────────
  readonly nodeStatuses = this.select('nodeStatuses');
  readonly pollingNodeId = this.select('pollingNodeId');
  readonly historyByNode = this.select('historyByNode');
  readonly isLoadingStatus = this.select('isLoadingStatus');
  readonly isLoadingHistory = this.select('isLoadingHistory');
  readonly isTriggering = this.select('isTriggering');
  readonly isAccepting = this.select('isAccepting');
  readonly isRejecting = this.select('isRejecting');
  readonly isRollingBack = this.select('isRollingBack');
  readonly error = this.select('error');

  /** Returns a function: (nodeId) => CalibrationNodeStatusResponse | null */
  readonly getNodeStatus = computed(() => {
    const statuses = this.nodeStatuses();
    return (nodeId: string): CalibrationNodeStatusResponse | null =>
      statuses[nodeId] ?? null;
  });

  /** Returns a function: (nodeId) => CalibrationHistoryRecord[] */
  readonly getHistoryForNode = computed(() => {
    const map = this.historyByNode();
    return (nodeId: string): CalibrationHistoryRecord[] => map[nodeId] ?? [];
  });

  // ── Dependencies ─────────────────────────────────────────────────────────────
  private readonly calibrationApi = inject(CalibrationApiService);

  // ── Poll timer ───────────────────────────────────────────────────────────────
  private _pollTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    super();
    this.setState(INITIAL_STATE);
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  // ── Polling ──────────────────────────────────────────────────────────────────

  /**
   * Start polling calibration status for the given node every 2 seconds.
   * Stops any existing poll first.
   */
  startPolling(nodeId: string): void {
    this.stopPolling();
    this.setState({pollingNodeId: nodeId});
    void this._fetchStatus(nodeId); // immediate first fetch
    this._pollTimer = setInterval(() => void this._fetchStatus(nodeId), 2000);
  }

  /** Stop the active polling timer. */
  stopPolling(): void {
    if (this._pollTimer !== null) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    this.setState({pollingNodeId: null});
  }

  private async _fetchStatus(nodeId: string): Promise<void> {
    try {
      const status = await this.calibrationApi.getNodeStatus(nodeId);
      const current = this.nodeStatuses();
      this.setState({nodeStatuses: {...current, [nodeId]: status}});
    } catch {
      // Silently ignore poll failures — stale data is better than an error loop
    }
  }

  // ── Actions ──────────────────────────────────────────────────────────────────

  async triggerCalibration(
    nodeId: string,
    request: CalibrationTriggerRequest = {},
  ): Promise<void> {
    this.setState({isTriggering: true, error: null});
    try {
      await this.calibrationApi.triggerCalibration(nodeId, request);
      await this._fetchStatus(nodeId); // refresh status immediately after trigger
    } catch (err) {
      this.setState({error: this._extractError(err)});
    } finally {
      this.setState({isTriggering: false});
    }
  }

  async acceptCalibration(
    nodeId: string,
    request: CalibrationAcceptRequest = {},
  ): Promise<void> {
    this.setState({isAccepting: true, error: null});
    try {
      await this.calibrationApi.acceptCalibration(nodeId, request);
      void this._fetchStatus(nodeId); // refresh status immediately
    } catch (err) {
      this.setState({error: this._extractError(err)});
    } finally {
      this.setState({isAccepting: false});
    }
  }

  async rejectCalibration(nodeId: string): Promise<void> {
    this.setState({isRejecting: true, error: null});
    try {
      await this.calibrationApi.rejectCalibration(nodeId);
      void this._fetchStatus(nodeId); // refresh status immediately
    } catch (err) {
      this.setState({error: this._extractError(err)});
    } finally {
      this.setState({isRejecting: false});
    }
  }

  async rollbackHistory(sensorId: string, recordId: string): Promise<void> {
    this.setState({isRollingBack: true, error: null});
    try {
      await this.calibrationApi.rollback(sensorId, {record_id: recordId});
    } catch (err) {
      this.setState({error: this._extractError(err)});
    } finally {
      this.setState({isRollingBack: false});
    }
  }

  /**
   * Load history for a single sensor ID.
   * Stores results under the sensorId key in historyByNode.
   */
  async loadHistory(
    sensorId: string,
    limit = 50,
    runId?: string,
  ): Promise<void> {
    this.setState({isLoadingHistory: true, error: null});
    try {
      const response = await this.calibrationApi.getHistory(
        sensorId,
        limit,
        undefined,
        runId,
      );
      const current = this.historyByNode();
      this.setState({
        historyByNode: {...current, [sensorId]: response.history},
      });
    } catch (err) {
      this.setState({error: this._extractError(err)});
    } finally {
      this.setState({isLoadingHistory: false});
    }
  }

  /**
   * Load history for all source sensors of a calibration node.
   * Fetches history per source_sensor_id and merges all records under nodeId,
   * sorted descending by timestamp. Capped at MAX_HISTORY_RECORDS total.
   */
  static readonly MAX_HISTORY_RECORDS = 4;

  async loadHistoryForNode(nodeId: string, limit = CalibrationStoreService.MAX_HISTORY_RECORDS): Promise<void> {
    const node = this.nodeStatuses()[nodeId];
    if (!node || node.source_sensor_ids.length === 0) return;

    this.setState({isLoadingHistory: true, error: null});
    try {
      const results = await Promise.all(
        node.source_sensor_ids.map(sensorId =>
          this.calibrationApi.getHistory(sensorId, limit).then(r => r.history),
        ),
      );
      const merged = results
        .flat()
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        .slice(0, CalibrationStoreService.MAX_HISTORY_RECORDS);
      const current = this.historyByNode();
      this.setState({historyByNode: {...current, [nodeId]: merged}});
    } catch (err) {
      this.setState({error: this._extractError(err)});
    } finally {
      this.setState({isLoadingHistory: false});
    }
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  private _extractError(err: unknown): string {
    if (err instanceof Error) return err.message;
    if (
      typeof err === 'object' &&
      err !== null &&
      'error' in err
    ) {
      return String((err as {error: unknown}).error);
    }
    return 'An unexpected error occurred';
  }
}
