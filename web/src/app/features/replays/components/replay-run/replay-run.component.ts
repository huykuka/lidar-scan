import {ChangeDetectionStrategy, Component, computed, DestroyRef, inject, OnInit, signal} from '@angular/core';
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
import {ReplayOutputs, ReplayRun} from '@core/models';
import {ApplyPreviewComponent} from '../apply-preview/apply-preview.component';
import {ReplayFormComponent} from '../replay-form/replay-form.component';
import {ReplayScoreComponent} from '../replay-score/replay-score.component';
import {RunChartComponent} from '../run-chart/run-chart.component';
import {runToPrefill} from '../../utils/clone-run';
import {formatOverrideValue} from '../../utils/override-values';
import {formatValue, frameRange, frameSnapshot, NodeMetrics, nodeMetrics} from '../../utils/run-metadata';
import {describeError, formatNumber} from '../../utils/score-format';

const POLL_INTERVAL_MS = 1000;

/** Statistics of one replay run: what each node produced, frame by frame. */
@Component({
  selector: 'app-replay-run',
  imports: [SynergyComponentsModule, RouterLink, ReplayScoreComponent, RunChartComponent],
  templateUrl: './replay-run.component.html',
  styleUrl: './replay-run.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReplayRunComponent implements OnInit {
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

  private runId = '';
  protected readonly run = signal<ReplayRun | null>(null);
  protected readonly outputs = signal<ReplayOutputs | null>(null);
  protected readonly isLoading = signal(true);
  protected readonly notFound = signal(false);
  protected readonly outputsFailed = signal(false);
  protected readonly selectedNodeId = signal('');

  protected readonly isActive = computed(() => ['queued', 'running'].includes(this.run()?.status ?? ''));
  protected readonly isCompleted = computed(() => this.run()?.status === 'completed');

  /** Metadata of every node, computed once when the captured frames arrive. */
  private readonly metricsByNode = computed(() => {
    const map = new Map<string, NodeMetrics>();
    for (const id of Object.keys(this.run()?.summary?.nodes ?? {})) map.set(id, nodeMetrics(this.outputs(), id));
    return map;
  });

  /** Pipeline nodes with how many fields each produced. */
  protected readonly nodeList = computed(() =>
    Object.entries(this.run()?.summary?.nodes ?? {}).map(([id, n]) => {
      const m = this.metricsByNode().get(id);
      return {id, name: n.name, type: n.type, emitted: n.emitted, fields: m ? m.numeric.length + m.category.length : null};
    }),
  );

  protected readonly activeNodeId = computed(() => this.selectedNodeId() || this.nodeList()[0]?.id || '');
  protected readonly activeNode = computed(() => this.nodeList().find((n) => n.id === this.activeNodeId()) ?? null);
  protected readonly active = computed(() => this.metricsByNode().get(this.activeNodeId()) ?? {numeric: [], category: []});

  // ── Frame inspector ──
  protected readonly range = computed(() => frameRange(this.outputs()));
  protected readonly inspectFrame = signal<number | null>(null);
  protected readonly inspected = computed(() => {
    const r = this.range();
    const f = this.inspectFrame() ?? r?.min ?? 0;
    return {frame: f, nodes: frameSnapshot(this.outputs(), f)};
  });
  protected readonly savedByNode = computed(() =>
    Object.entries(this.run()?.summary?.saved_results ?? {}).map(([id, count]) => ({
      id,
      name: this.run()?.summary?.nodes?.[id]?.name ?? this.nodeName(id),
      count,
    })),
  );
  protected readonly savedResults = computed(() => this.outputs()?.saved_results ?? []);
  protected readonly errors = computed(() => this.outputs()?.errors ?? []);
  protected readonly overrides = computed(() =>
    Object.entries(this.run()?.overrides ?? {}).flatMap(([nodeId, params]) =>
      Object.entries(params).map(([key, value]) => ({node: this.nodeName(nodeId), key, value: formatOverrideValue(value)})),
    ),
  );
  protected readonly canApply = computed(
    () => this.auth.isAdmin() && this.isCompleted() && this.overrides().length > 0,
  );

  ngOnInit(): void {
    this.runId = this.route.snapshot.paramMap.get('id') ?? '';
    this.nav.setPageConfig({title: 'Replays', subtitle: 'Run statistics'});
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
      .getReplay(this.runId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (run) => {
          const justFinished = run.status === 'completed' && !this.outputs();
          this.run.set(run);
          this.isLoading.set(false);
          if (justFinished) this.loadOutputs();
        },
        error: (err) => {
          this.notFound.set(err?.status === 404);
          this.isLoading.set(false);
        },
      });
  }

  private loadOutputs(): void {
    this.outputsFailed.set(false);
    this.api
      .getOutputs(this.runId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (o) => this.outputs.set(o),
        error: () => this.outputsFailed.set(true),
      });
  }

  // ── Presentation ─────────────────────────────────────────────────────────
  protected nodeName(id: string): string {
    return this.nodeStore.nodes().find((n) => n.id === id)?.name ?? id.slice(0, 8);
  }

  protected recordingName(): string {
    const id = this.run()?.recording_id ?? '';
    return this.recordingStore.recordings().find((r) => r.id === id)?.name ?? id.slice(0, 8);
  }

  protected fmt(value: number | null | undefined): string {
    return formatNumber(value);
  }

  protected errorText(score: Parameters<typeof describeError>[0]): string {
    return describeError(score);
  }

  protected nameOf(nodeId: string): string {
    return this.run()?.summary?.nodes?.[nodeId]?.name ?? this.nodeName(nodeId);
  }

  protected valuesText(values: Record<string, unknown>): string {
    return Object.entries(values)
      .slice(0, 6)
      .map(([k, v]) => `${k}: ${typeof v === 'number' ? formatNumber(v) : String(v)}`)
      .join(' · ');
  }

  protected statusVariant(status: string): 'success' | 'danger' | 'primary' | 'neutral' {
    return status === 'completed' ? 'success' : status === 'failed' ? 'danger' : status === 'running' ? 'primary' : 'neutral';
  }

  protected progressPercent(): number {
    const r = this.run();
    return r && r.frames_total ? Math.round((r.frames_processed / r.frames_total) * 100) : 0;
  }

  protected formatDate(iso: string | null): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
  }

  // ── Interaction ──────────────────────────────────────────────────────────
  protected setFrame(value: string | number): void {
    const r = this.range();
    const n = Math.round(Number(value));
    if (r && Number.isFinite(n)) this.inspectFrame.set(Math.min(r.max, Math.max(r.min, n)));
  }

  protected stepFrame(delta: number): void {
    this.setFrame((this.inspected().frame) + delta);
  }

  protected show(value: unknown): string {
    return formatValue(value);
  }

  protected selectNode(id: string): void {
    this.selectedNodeId.set(id);
  }

  protected rerun(): void {
    const run = this.run();
    if (!run) return;
    this.drawer.open(ReplayFormComponent, {
      title: 'Re-run with changes',
      size: '480px',
      submitLabel: 'Start replay',
      submitIcon: 'play_arrow',
      inputs: {onStarted: () => this.router.navigate(['/replays']), prefill: runToPrefill(run)},
    });
  }

  protected applyToPipeline(): void {
    this.drawer.open(ApplyPreviewComponent, {
      title: 'Apply to pipeline',
      size: '520px',
      showFooter: false,
      inputs: {runId: this.runId, onApplied: () => this.nodeStore.setState({nodes: [], edges: []})},
    });
  }

  protected cancel(): void {
    this.api.cancelReplay(this.runId).subscribe(() => this.load(false));
  }

  protected async remove(): Promise<void> {
    const ok = await this.dialog.confirm({
      title: 'Delete run',
      message: `Delete "${this.run()?.label}"?`,
      confirmLabel: 'Delete',
      confirmIcon: 'delete',
      confirmSeverity: 'danger',
    });
    if (!ok) return;
    this.api.deleteReplay(this.runId).subscribe(() => {
      this.toast.success('Run deleted');
      this.router.navigate(['/replays']);
    });
  }
}
