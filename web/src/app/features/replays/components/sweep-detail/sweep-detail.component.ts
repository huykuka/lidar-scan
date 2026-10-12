import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import {ActivatedRoute, Router, RouterLink} from '@angular/router';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {interval} from 'rxjs';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NavigationService} from '@core/services';
import {AuthService} from '@core/services/auth.service';
import {ReplayApiService} from '@core/services/api/replay-api.service';
import {DialogService} from '@core/services/dialog.service';
import {DrawerService} from '@core/services/drawer.service';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {RecordingStoreService} from '@core/services/stores/recording-store.service';
import {ToastService} from '@core/services/toast.service';
import {ReplayRun, SweepDetail, TargetScore} from '@core/models';
import {ApplyPreviewComponent} from '../apply-preview/apply-preview.component';
import {GroundTruthComponent} from '../ground-truth/ground-truth.component';
import {ReplayFormComponent} from '../replay-form/replay-form.component';
import {ReplayScoreComponent} from '../replay-score/replay-score.component';
import {SweepChartComponent} from '../sweep-chart/sweep-chart.component';
import {runToPrefill} from '../../utils/clone-run';
import {formatOverrideValue} from '../../utils/override-values';
import {commonMetrics, metricStats, MetricOption} from '../../utils/run-metrics';
import {describeError, formatNumber, signed} from '../../utils/score-format';
import {ChartPoint} from '../../utils/sweep-chart-geometry';

const POLL_INTERVAL_MS = 1000;

export interface SweepRow {
  run: ReplayRun;
  x: unknown;
  mean: number | null;
  std: number | null;
  /** Score for the chart's metric when it has a ground-truth target. */
  score: TargetScore | null;
}

@Component({
  selector: 'app-sweep-detail',
  imports: [SynergyComponentsModule, RouterLink, ReplayScoreComponent, SweepChartComponent],
  templateUrl: './sweep-detail.component.html',
  styleUrl: './sweep-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SweepDetailComponent implements OnInit {
  private readonly api = inject(ReplayApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly nav = inject(NavigationService);
  private readonly drawer = inject(DrawerService);
  private readonly dialog = inject(DialogService);
  private readonly toast = inject(ToastService);
  private readonly nodeStore = inject(NodeStoreService);
  private readonly recordingStore = inject(RecordingStoreService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly auth = inject(AuthService);

  private sweepId = '';
  protected readonly detail = signal<SweepDetail | null>(null);
  protected readonly isLoading = signal(true);
  protected readonly notFound = signal(false);
  protected readonly metricId = signal('');
  protected readonly selectedRunId = signal<string | null>(null);
  protected readonly compareIds = signal<string[]>([]);

  protected readonly sweep = computed(() => this.detail()?.sweep ?? null);
  protected readonly isActive = computed(() => (this.sweep()?.progress?.active ?? 0) > 0);
  protected readonly canCompare = computed(() => this.compareIds().length === 2);

  /** Runs ordered by the swept value (numbers ascending; otherwise as created). */
  protected readonly runs = computed<ReplayRun[]>(() => {
    const runs = [...(this.detail()?.runs ?? [])];
    return runs.every((r) => typeof r.x_value === 'number')
      ? runs.sort((a, b) => (a.x_value as number) - (b.x_value as number))
      : runs;
  });

  protected readonly metrics = computed<MetricOption[]>(() => commonMetrics(this.runs()));
  protected readonly metric = computed(() => this.metrics().find((m) => this.idOf(m) === this.metricId()) ?? null);
  /** Ground truth for the metric being plotted, if any. */
  protected readonly target = computed(() => {
    const m = this.metric();
    return m ? (this.detail()?.targets.find((t) => t.node_id === m.nodeId && t.metric_key === m.key) ?? null) : null;
  });

  protected readonly rows = computed<SweepRow[]>(() => {
    const m = this.metric();
    return this.runs().map((run) => {
      const stats = m ? metricStats(run, m.nodeId, m.key) : null;
      const score = this.target() ? (run.scores?.targets.find((t) => t.target_id === this.target()!.id) ?? null) : null;
      return {run, x: run.x_value, mean: stats?.mean ?? null, std: stats?.std ?? null, score};
    });
  });

  protected readonly points = computed<ChartPoint[]>(() =>
    this.rows().map((r) => ({
      runId: r.run.id,
      label: `${this.valueText(r.x)}${r.run.is_baseline ? ' (current)' : ''}`,
      x: typeof r.x === 'number' ? r.x : this.valueText(r.x),
      y: r.mean,
      std: r.std,
      status: r.run.status,
    })),
  );

  protected readonly best = computed(() => {
    const id = this.detail()?.best_run_id;
    return id ? (this.rows().find((r) => r.run.id === id) ?? null) : null;
  });

  constructor() {
    // Pick a sensible metric: the ground-truth one if there is one, else the first available.
    effect(() => {
      const metrics = this.metrics();
      if (metrics.length === 0 || metrics.some((m) => this.idOf(m) === this.metricId())) return;
      const targets = this.detail()?.targets ?? [];
      const preferred = metrics.find((m) => targets.some((t) => t.node_id === m.nodeId && t.metric_key === m.key));
      this.metricId.set(this.idOf(preferred ?? metrics[0]));
    });
  }

  ngOnInit(): void {
    this.sweepId = this.route.snapshot.paramMap.get('id') ?? '';
    this.nav.setPageConfig({title: 'Replays', subtitle: 'Parameter sweep'});
    this.nodeStore.loadNodesIfEmpty();
    this.recordingStore.loadRecordings();
    this.load();

    interval(POLL_INTERVAL_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.isActive()) this.load(false);
      });
  }

  protected load(showSpinner = true): void {
    if (showSpinner) this.isLoading.set(true);
    this.api
      .getSweep(this.sweepId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (d) => {
          this.detail.set(d);
          this.isLoading.set(false);
          const valid = new Set(d.runs.filter((r) => r.status === 'completed').map((r) => r.id));
          this.compareIds.update((ids) => ids.filter((id) => valid.has(id)));
        },
        error: (err) => {
          this.notFound.set(err?.status === 404);
          this.isLoading.set(false);
        },
      });
  }

  // ── Presentation ─────────────────────────────────────────────────────────
  protected idOf(m: MetricOption): string {
    return `${m.nodeId}|${m.key}`;
  }

  protected recordingName(): string {
    const id = this.sweep()?.recording_id ?? '';
    return this.recordingStore.recordings().find((r) => r.id === id)?.name ?? id.slice(0, 8);
  }

  protected nodeName(): string {
    const id = this.sweep()?.node_id ?? '';
    return this.nodeStore.nodes().find((n) => n.id === id)?.name ?? id.slice(0, 8);
  }

  protected valueText(value: unknown): string {
    const text = formatOverrideValue(value);
    return text === '' ? '—' : text;
  }

  protected fmt(value: number | null | undefined): string {
    return formatNumber(value);
  }

  protected errorText(score: TargetScore | null): string {
    return score ? describeError(score) : '—';
  }

  protected signedText(value: number | null | undefined): string {
    return signed(value);
  }

  protected progressPercent(): number {
    const p = this.sweep()?.progress;
    return p && p.total ? Math.round(((p.completed + p.failed) / p.total) * 100) : 0;
  }

  protected statusVariant(status: string): 'success' | 'danger' | 'primary' | 'neutral' {
    return status === 'completed' ? 'success' : status === 'failed' ? 'danger' : status === 'running' ? 'primary' : 'neutral';
  }

  // ── Interaction ──────────────────────────────────────────────────────────
  protected selectMetric(id: string): void {
    this.metricId.set(id);
  }

  protected toggleCompare(run: ReplayRun, checked: boolean): void {
    this.compareIds.update((ids) => {
      const without = ids.filter((id) => id !== run.id);
      return checked ? [...without, run.id].slice(-2) : without;
    });
  }

  protected compare(): void {
    const [a, b] = this.compareIds();
    if (a && b) this.router.navigate(['/replays/compare'], {queryParams: {a, b}});
  }

  protected rerun(run: ReplayRun): void {
    this.drawer.open(ReplayFormComponent, {
      title: 'Re-run with changes',
      size: '480px',
      submitLabel: 'Start replay',
      submitIcon: 'play_arrow',
      inputs: {onStarted: () => this.router.navigate(['/replays']), prefill: runToPrefill(run)},
    });
  }

  protected canApply(run: ReplayRun): boolean {
    return this.auth.isAdmin() && run.status === 'completed' && !run.is_baseline && Object.keys(run.overrides ?? {}).length > 0;
  }

  protected applyToPipeline(run: ReplayRun): void {
    this.drawer.open(ApplyPreviewComponent, {
      title: 'Apply to pipeline',
      size: '520px',
      showFooter: false,
      inputs: {runId: run.id, onApplied: () => this.afterApply()},
    });
  }

  /** The saved pipeline changed: reload it so names and "current" values are up to date. */
  private async afterApply(): Promise<void> {
    this.nodeStore.setState({nodes: [], edges: []});
    await this.nodeStore.loadNodesIfEmpty();
    this.load(false);
  }

  protected openGroundTruth(): void {
    this.drawer.open(GroundTruthComponent, {
      title: 'Ground truth',
      size: '480px',
      showFooter: false,
      inputs: {recordingId: this.sweep()?.recording_id ?? '', onChanged: () => this.load(false)},
    });
  }

  protected cancelSweep(): void {
    this.api.cancelSweep(this.sweepId).subscribe((r) => {
      this.toast.success(`Cancelled ${r.cancelled} run(s)`);
      this.load(false);
    });
  }

  protected async deleteSweep(): Promise<void> {
    const ok = await this.dialog.confirm({
      title: 'Delete sweep',
      message: `Delete "${this.sweep()?.label}" and all of its runs?`,
      confirmLabel: 'Delete',
      confirmIcon: 'delete',
      confirmSeverity: 'danger',
    });
    if (!ok) return;
    this.api.deleteSweep(this.sweepId).subscribe(() => {
      this.toast.success('Sweep deleted');
      this.router.navigate(['/replays'], {queryParams: {tab: 'sweeps'}});
    });
  }
}
