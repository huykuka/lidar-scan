import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {Observable} from 'rxjs';
import {environment} from '@env/environment';
import {
  ApplyPreview,
  ApplyResult,
  CreateReplayRequest,
  CreateSweepRequest,
  CreateTargetRequest,
  GroundTruthTarget,
  ListReplayRunsResponse,
  ListSweepsResponse,
  ReplayComparison,
  ReplayOutputs,
  ReplayRun,
  Sweep,
  SweepDetail,
} from '../../models/replay.model';

@Injectable({providedIn: 'root'})
export class ReplayApiService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/replays`;

  startReplay(request: CreateReplayRequest): Observable<ReplayRun> {
    return this.http.post<ReplayRun>(this.baseUrl, request);
  }

  /** Stand-alone runs by default; sweep runs are listed under their sweep. */
  listReplays(recordingId?: string, includeSweepRuns = false): Observable<ListReplayRunsResponse> {
    const params: Record<string, string> = {};
    if (recordingId) params['recording_id'] = recordingId;
    if (includeSweepRuns) params['include_sweep_runs'] = 'true';
    return this.http.get<ListReplayRunsResponse>(this.baseUrl, {params});
  }

  getReplay(runId: string): Observable<ReplayRun> {
    return this.http.get<ReplayRun>(`${this.baseUrl}/${encodeURIComponent(runId)}`);
  }

  /** Per-node, per-frame captured outputs of a completed run. */
  getOutputs(runId: string): Observable<ReplayOutputs> {
    return this.http.get<ReplayOutputs>(`${this.baseUrl}/${encodeURIComponent(runId)}/outputs`);
  }

  cancelReplay(runId: string): Observable<ReplayRun> {
    return this.http.post<ReplayRun>(`${this.baseUrl}/${encodeURIComponent(runId)}/cancel`, {});
  }

  deleteReplay(runId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/${encodeURIComponent(runId)}`);
  }

  /** Binary visual-diff payload for one node/frame; decode with `parseCloudDiff`. */
  getCloudDiff(
    a: string,
    b: string,
    nodeId: string,
    frame: number,
    tol: number,
  ): Observable<ArrayBuffer> {
    return this.http.get(`${this.baseUrl}/compare/cloud`, {
      params: {a, b, node_id: nodeId, frame: String(frame), tol: String(tol)},
      responseType: 'arraybuffer',
    });
  }

  // ── Parameter sweeps ──────────────────────────────────────────────────────
  startSweep(request: CreateSweepRequest): Observable<Sweep> {
    return this.http.post<Sweep>(`${this.baseUrl}/sweeps`, request);
  }

  listSweeps(): Observable<ListSweepsResponse> {
    return this.http.get<ListSweepsResponse>(`${this.baseUrl}/sweeps`);
  }

  getSweep(sweepId: string): Observable<SweepDetail> {
    return this.http.get<SweepDetail>(`${this.baseUrl}/sweeps/${encodeURIComponent(sweepId)}`);
  }

  cancelSweep(sweepId: string): Observable<{cancelled: number}> {
    return this.http.post<{cancelled: number}>(`${this.baseUrl}/sweeps/${encodeURIComponent(sweepId)}/cancel`, {});
  }

  deleteSweep(sweepId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/sweeps/${encodeURIComponent(sweepId)}`);
  }

  // ── Ground truth ──────────────────────────────────────────────────────────
  listTargets(recordingId?: string): Observable<{targets: GroundTruthTarget[]}> {
    const params = recordingId ? {recording_id: recordingId} : undefined;
    return this.http.get<{targets: GroundTruthTarget[]}>(`${this.baseUrl}/targets`, {params});
  }

  createTarget(request: CreateTargetRequest): Observable<GroundTruthTarget> {
    return this.http.post<GroundTruthTarget>(`${this.baseUrl}/targets`, request);
  }

  deleteTarget(targetId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/targets/${encodeURIComponent(targetId)}`);
  }

  // ── Apply to the live pipeline ────────────────────────────────────────────
  previewApply(runId: string): Observable<ApplyPreview> {
    return this.http.get<ApplyPreview>(`${this.baseUrl}/${encodeURIComponent(runId)}/apply-preview`);
  }

  /** Writes the run's parameters into the saved pipeline (admin only). */
  applyToPipeline(runId: string): Observable<ApplyResult> {
    return this.http.post<ApplyResult>(`${this.baseUrl}/${encodeURIComponent(runId)}/apply`, {});
  }

  compare(a: string, b: string): Observable<ReplayComparison> {
    return this.http.get<ReplayComparison>(`${this.baseUrl}/compare`, {params: {a, b}});
  }
}
