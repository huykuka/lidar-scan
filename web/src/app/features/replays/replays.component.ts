import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import {ActivatedRoute, Router} from '@angular/router';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {catchError, forkJoin, interval, map, of} from 'rxjs';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NavigationService} from '@core/services';
import {AuthService} from '@core/services/auth.service';
import {ReplayApiService} from '@core/services/api/replay-api.service';
import {DialogService} from '@core/services/dialog.service';
import {DrawerService} from '@core/services/drawer.service';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {RecordingStoreService} from '@core/services/stores/recording-store.service';
import {ToastService} from '@core/services/toast.service';
import {ReplayRun, Sweep} from '@core/models';
import {ApplyPreviewComponent} from './components/apply-preview/apply-preview.component';
import {GroundTruthComponent} from './components/ground-truth/ground-truth.component';
import {ReplayFormComponent} from './components/replay-form/replay-form.component';
import {ReplayScoreComponent} from './components/replay-score/replay-score.component';
import {SweepFormComponent} from './components/sweep-form/sweep-form.component';
import {runToPrefill} from './utils/clone-run';
import {describeValues} from './utils/sweep-values';

const POLL_INTERVAL_MS = 1000;
const COMPARE_COUNT = 2;

export type ReplaysTab = 'runs' | 'sweeps';

@Component({
  selector: 'app-replays',
  imports: [SynergyComponentsModule, ReplayScoreComponent],
  templateUrl: './replays.component.html',
  styleUrl: './replays.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReplaysComponent implements OnInit {
  private readonly api = inject(ReplayApiService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly nav = inject(NavigationService);
  private readonly toast = inject(ToastService);
  private readonly dialog = inject(DialogService);
  private readonly drawer = inject(DrawerService);
  private readonly nodeStore = inject(NodeStoreService);
  private readonly recordingStore = inject(RecordingStoreService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly auth = inject(AuthService);

  protected readonly tab = signal<ReplaysTab>('runs');
  protected readonly runs = signal<ReplayRun[]>([]);
  protected readonly sweeps = signal<Sweep[]>([]);
  protected readonly isLoading = signal(false);
  protected readonly selectedIds = signal<string[]>([]);

  /** Runs that can be selected: anything not queued/running (those must be cancelled first). */
  protected readonly selectableIds = computed(() =>
    this.runs()
      .filter((r) => r.status !== 'queued' && r.status !== 'running')
      .map((r) => r.id),
  );
  protected readonly allSelected = computed(
    () => this.selectableIds().length > 0 && this.selectedIds().length === this.selectableIds().length,
  );
  protected readonly someSelected = computed(() => this.selectedIds().length > 0 && !this.allSelected());
  /** Compare needs exactly two completed runs. */
  protected readonly canCompare = computed(() => {
    const ids = this.selectedIds();
    if (ids.length !== COMPARE_COUNT) return false;
    const byId = new Map(this.runs().map((r) => [r.id, r]));
    return ids.every((id) => byId.get(id)?.status === 'completed');
  });
  protected readonly stats = computed(() => {
    const runs = this.runs();
    const count = (s: string) => runs.filter((r) => r.status === s).length;
    return {
      total: runs.length,
      completed: count('completed'),
      active: count('running') + count('queued'),
      failed: count('failed'),
    };
  });
  protected readonly hasActive = computed(
    () =>
      this.runs().some((r) => r.status === 'queued' || r.status === 'running') ||
      this.sweeps().some((s) => (s.progress?.active ?? 0) > 0),
  );

  async ngOnInit() {
    this.nav.setPageConfig({
      title: 'Replays',
      subtitle: 'Run recordings through the pipeline offline, compare results and tune parameters',
    });
    const requested = this.route.snapshot.queryParamMap.get('tab');
    if (requested === 'sweeps') this.tab.set('sweeps');

    await Promise.all([this.nodeStore.loadNodesIfEmpty(), this.recordingStore.loadRecordings()]);
    this.refresh();

    // Poll only while something is running.
    interval(POLL_INTERVAL_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.hasActive()) this.refresh(false);
      });
  }

  protected refresh(showSpinner = true) {
    if (showSpinner) this.isLoading.set(true);
    this.api
      .listReplays()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.runs.set(res.runs);
          // Drop selections for runs that no longer exist or are now active.
          const valid = new Set(
            res.runs.filter((r) => r.status !== 'queued' && r.status !== 'running').map((r) => r.id),
          );
          this.selectedIds.update((ids) => ids.filter((id) => valid.has(id)));
          this.isLoading.set(false);
        },
        error: () => this.isLoading.set(false),
      });
    this.api
      .listSweeps()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((res) => this.sweeps.set(res.sweeps));
  }

  protected setTab(name: string) {
    if (name !== 'runs' && name !== 'sweeps') return;
    this.tab.set(name);
    this.router.navigate([], {queryParams: {tab: name === 'runs' ? null : name}, queryParamsHandling: 'merge', replaceUrl: true});
  }

  // ── Presentation helpers ─────────────────────────────────────────────────
  protected recordingName(id: string): string {
    return this.recordingStore.recordings().find((r) => r.id === id)?.name ?? id.slice(0, 8);
  }

  protected nodeName(id: string): string {
    return this.nodeStore.nodes().find((n) => n.id === id)?.name ?? id.slice(0, 8);
  }

  protected progress(run: ReplayRun): number {
    if (!run.frames_total) return 0;
    return Math.min(100, Math.round((run.frames_processed / run.frames_total) * 100));
  }

  protected sweepProgress(sweep: Sweep): number {
    const p = sweep.progress;
    return p && p.total ? Math.round(((p.completed + p.failed) / p.total) * 100) : 0;
  }

  protected statusVariant(status: string): 'success' | 'danger' | 'primary' | 'neutral' {
    switch (status) {
      case 'completed':
        return 'success';
      case 'failed':
        return 'danger';
      case 'running':
        return 'primary';
      default:
        return 'neutral';
    }
  }

  /** "Down · every_k_points = 10" style summary of what a run changed. */
  protected overrideSummary(run: ReplayRun): string {
    const parts = Object.entries(run.overrides ?? {}).flatMap(([nodeId, params]) =>
      Object.entries(params).map(([key, value]) => `${this.nodeName(nodeId)} · ${key} = ${typeof value === 'string' ? value : JSON.stringify(value)}`),
    );
    return parts.length ? parts.join('; ') : 'pipeline as saved';
  }

  protected describeValues(values: unknown[]): string {
    return describeValues(values);
  }

  protected openRun(run: ReplayRun): void {
    this.router.navigate(['/replays', run.id]);
  }

  protected formatDate(iso: string): string {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
  }

  protected isSelected(id: string): boolean {
    return this.selectedIds().includes(id);
  }

  // ── Selection / navigation ───────────────────────────────────────────────
  protected toggleSelect(run: ReplayRun, checked: boolean) {
    this.selectedIds.update((ids) => {
      const without = ids.filter((id) => id !== run.id);
      if (!checked) return without;
      return [...without, run.id];
    });
  }

  protected toggleSelectAll(checked: boolean) {
    this.selectedIds.set(checked ? [...this.selectableIds()] : []);
  }

  protected async removeSelected() {
    const ids = this.selectedIds();
    if (ids.length === 0) return;
    const ok = await this.dialog.confirm({
      title: 'Delete replay runs',
      message: `Delete ${ids.length} selected run${ids.length === 1 ? '' : 's'}? Their captured outputs will be removed.`,
      confirmLabel: `Delete ${ids.length}`,
      confirmIcon: 'delete',
      confirmSeverity: 'danger',
    });
    if (!ok) return;
    forkJoin(
      ids.map((id) =>
        this.api.deleteReplay(id).pipe(
          map(() => true),
          catchError(() => of(false)),
        ),
      ),
    ).subscribe((results) => {
      const deleted = results.filter(Boolean).length;
      const failed = results.length - deleted;
      if (deleted) this.toast.success(`Deleted ${deleted} replay run${deleted === 1 ? '' : 's'}`);
      if (failed) this.toast.danger(`${failed} run${failed === 1 ? '' : 's'} could not be deleted`);
      this.selectedIds.set([]);
      this.refresh(false);
    });
  }

  protected compareSelected() {
    const [a, b] = this.selectedIds();
    if (a && b) this.router.navigate(['/replays/compare'], {queryParams: {a, b}});
  }

  protected openSweep(sweep: Sweep) {
    this.router.navigate(['/replays/sweeps', sweep.id]);
  }

  // ── Run actions ──────────────────────────────────────────────────────────
  protected cancel(run: ReplayRun) {
    this.api.cancelReplay(run.id).subscribe(() => this.refresh(false));
  }

  protected async remove(run: ReplayRun) {
    const ok = await this.dialog.confirm({
      title: 'Delete replay run',
      message: `Delete "${run.label}"? Its captured outputs will be removed.`,
      confirmLabel: 'Delete',
      confirmIcon: 'delete',
      confirmSeverity: 'danger',
    });
    if (!ok) return;
    this.api.deleteReplay(run.id).subscribe(() => {
      this.toast.success('Replay run deleted');
      this.refresh(false);
    });
  }

  protected async removeSweep(sweep: Sweep) {
    const ok = await this.dialog.confirm({
      title: 'Delete sweep',
      message: `Delete "${sweep.label}" and all of its runs?`,
      confirmLabel: 'Delete',
      confirmIcon: 'delete',
      confirmSeverity: 'danger',
    });
    if (!ok) return;
    this.api.deleteSweep(sweep.id).subscribe(() => {
      this.toast.success('Sweep deleted');
      this.refresh(false);
    });
  }

  protected canApply(run: ReplayRun): boolean {
    return this.auth.isAdmin() && run.status === 'completed' && Object.keys(run.overrides ?? {}).length > 0;
  }

  protected applyToPipeline(run: ReplayRun) {
    this.drawer.open(ApplyPreviewComponent, {
      title: 'Apply to pipeline',
      size: '520px',
      showFooter: false,
      inputs: {runId: run.id, onApplied: () => this.afterApply()},
    });
  }

  /** The saved pipeline changed: reload it so forms show the new "current" values. */
  private async afterApply() {
    this.nodeStore.setState({nodes: [], edges: []});
    await this.nodeStore.loadNodesIfEmpty();
    this.refresh(false);
  }

  // ── Drawers ──────────────────────────────────────────────────────────────
  protected openNewReplay() {
    this.drawer.open(ReplayFormComponent, {
      title: 'New replay',
      size: '480px',
      submitLabel: 'Start replay',
      submitIcon: 'play_arrow',
      inputs: {onStarted: () => this.refresh(false)},
    });
  }

  /** Open the new-replay form pre-filled from an earlier run. */
  protected rerun(run: ReplayRun) {
    this.drawer.open(ReplayFormComponent, {
      title: 'Re-run with changes',
      size: '480px',
      submitLabel: 'Start replay',
      submitIcon: 'play_arrow',
      inputs: {onStarted: () => this.refresh(false), prefill: runToPrefill(run)},
    });
  }

  protected openSweepForm() {
    this.drawer.open(SweepFormComponent, {
      title: 'Parameter sweep',
      size: '520px',
      submitLabel: 'Start sweep',
      submitIcon: 'tune',
      inputs: {
        onStarted: (sweep: Sweep) => {
          this.refresh(false);
          this.router.navigate(['/replays/sweeps', sweep.id]);
        },
      },
    });
  }

  protected openGroundTruth() {
    const firstRun = this.selectedIds()[0] ? this.runs().find((r) => r.id === this.selectedIds()[0]) : this.runs()[0];
    this.drawer.open(GroundTruthComponent, {
      title: 'Ground truth',
      size: '480px',
      showFooter: false,
      inputs: {recordingId: firstRun?.recording_id ?? '', onChanged: () => this.refresh(false)},
    });
  }
}
