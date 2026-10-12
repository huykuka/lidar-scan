import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  ElementRef,
  inject,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import {ActivatedRoute, Router, RouterLink} from '@angular/router';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {buildPath, CHART_H, CHART_W, frameAtFraction} from '../../utils/chart-geometry';
import {ApplyPreviewComponent} from '../apply-preview/apply-preview.component';
import {ReplayCloudDiffComponent} from '../replay-cloud-diff/replay-cloud-diff.component';
import {ReplayScoreComponent} from '../replay-score/replay-score.component';
import {NavigationService} from '@core/services';
import {AuthService} from '@core/services/auth.service';
import {DrawerService} from '@core/services/drawer.service';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {ReplayApiService} from '@core/services/api/replay-api.service';
import {
  ComparisonSeries,
  FieldDiff,
  NodeComparison,
  ReplayComparison,
  SavedResultsComparison,
  ValueComparison,
} from '@core/models';

export interface ChartModel {
  series: ComparisonSeries;
  pathA: string;
  pathB: string;
  min: number;
  max: number;
  firstFrame: number;
  lastFrame: number;
}

export type CompareTab = 'overview' | 'visual' | 'results' | 'nodes';

export interface NodeRow {
  id: string;
  node: NodeComparison;
  values: {key: string; stats: ValueComparison}[];
}

export interface SavedRow {
  nodeId: string;
  nodeName: string;
  data: SavedResultsComparison;
}

@Component({
  selector: 'app-replay-compare',
  imports: [SynergyComponentsModule, RouterLink, ReplayCloudDiffComponent, ReplayScoreComponent],
  templateUrl: './replay-compare.component.html',
  styleUrl: './replay-compare.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReplayCompareComponent implements OnInit {
  private readonly api = inject(ReplayApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly nav = inject(NavigationService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly drawer = inject(DrawerService);
  private readonly nodeStore = inject(NodeStoreService);
  protected readonly auth = inject(AuthService);
  private readonly tabGroup = viewChild('tabs', {read: ElementRef});

  protected readonly chartW = CHART_W;
  protected readonly chartH = CHART_H;

  protected readonly comparison = signal<ReplayComparison | null>(null);
  protected readonly isLoading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly onlyDifferences = signal(true);
  protected readonly tab = signal<CompareTab>('overview');
  /** Frame requested by clicking a chart; handed to the visual diff. */
  protected readonly focusFrame = signal<number | null>(null);

  protected readonly nodeRows = computed<NodeRow[]>(() => {
    const cmp = this.comparison();
    if (!cmp) return [];
    const onlyDiff = this.onlyDifferences();
    return Object.entries(cmp.nodes).map(([id, node]) => ({
      id,
      node,
      values: Object.entries(node.values)
        .filter(([, s]) => !onlyDiff || s.differing > 0 || s.only_a > 0 || s.only_b > 0)
        .map(([key, stats]) => ({key, stats})),
    }));
  });

  protected readonly savedRows = computed<SavedRow[]>(() => {
    const cmp = this.comparison();
    if (!cmp) return [];
    return Object.entries(cmp.saved_results).map(([nodeId, data]) => ({
      nodeId,
      nodeName: cmp.nodes[nodeId]?.name ?? nodeId.slice(0, 8),
      data: {
        ...data,
        pairs: this.onlyDifferences() ? data.pairs.filter((p) => Object.keys(p.fields).length) : data.pairs,
      },
    }));
  });

  protected readonly charts = computed<ChartModel[]>(() =>
    (this.comparison()?.series ?? []).map((series) => {
      const all = series.points.flatMap((p) => [p.a, p.b]);
      const min = Math.min(...all);
      const max = Math.max(...all);
      const first = series.points[0]?.frame ?? 0;
      const last = series.points[series.points.length - 1]?.frame ?? 1;
      return {
        series,
        min,
        max,
        firstFrame: first,
        lastFrame: last,
        pathA: buildPath(series.points.map((p) => ({frame: p.frame, v: p.a})), first, last, min, max),
        pathB: buildPath(series.points.map((p) => ({frame: p.frame, v: p.b})), first, last, min, max),
      };
    }),
  );

  ngOnInit() {
    this.nav.setPageConfig({title: 'Replays', subtitle: 'Compare two runs: baseline (A) against candidate (B)'});
    this.nodeStore.loadNodesIfEmpty();
    const params = this.route.snapshot.queryParamMap;
    const a = params.get('a');
    const b = params.get('b');
    if (!a || !b) {
      this.error.set('Select two runs on the Replays page to compare them.');
      this.isLoading.set(false);
      return;
    }
    this.api
      .compare(a, b)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (cmp) => {
          this.comparison.set(cmp);
          this.isLoading.set(false);
        },
        error: (err) => {
          this.error.set(err?.error?.detail ?? 'Could not compare these runs.');
          this.isLoading.set(false);
        },
      });
  }

  /** Clicking a chart jumps the visual diff to that frame. */
  protected onChartClick(event: MouseEvent, chart: ChartModel): void {
    const rect = (event.currentTarget as SVGElement).getBoundingClientRect();
    if (rect.width === 0) return;
    this.focusFrame.set(
      frameAtFraction((event.clientX - rect.left) / rect.width, chart.firstFrame, chart.lastFrame),
    );
    this.showTab('visual');
  }

  protected setTab(name: string): void {
    if (name === 'overview' || name === 'visual' || name === 'results' || name === 'nodes') this.tab.set(name);
  }

  /** Switch tab from code (the tab group only reacts to its own clicks otherwise). */
  private showTab(name: CompareTab): void {
    this.tab.set(name);
    (this.tabGroup()?.nativeElement as {show?: (panel: string) => void} | undefined)?.show?.(name);
  }

  /** Overrides of run B, if it differs from the saved pipeline and the user may apply them. */
  protected readonly canApplyB = computed(() => {
    const info = this.comparison()?.run_b_info;
    return this.auth.isAdmin() && !!info && Object.keys(info.overrides ?? {}).length > 0;
  });

  protected applyB(): void {
    const info = this.comparison()?.run_b_info;
    if (!info) return;
    this.drawer.open(ApplyPreviewComponent, {
      title: 'Apply to pipeline',
      size: '520px',
      showFooter: false,
      inputs: {runId: info.id, onApplied: () => this.nodeStore.setState({nodes: [], edges: []})},
    });
  }

  /** "Down · radius = 1.5" style summary of what a run changed. */
  protected overrideList(overrides: Record<string, Record<string, unknown>> | undefined): string[] {
    return Object.entries(overrides ?? {}).flatMap(([nodeId, params]) =>
      Object.entries(params).map(([key, value]) => {
        const name = this.nodeStore.nodes().find((n) => n.id === nodeId)?.name ?? nodeId.slice(0, 8);
        return `${name} · ${key} = ${typeof value === 'string' ? value : JSON.stringify(value)}`;
      }),
    );
  }

  protected goBack() {
    this.router.navigate(['/replays']);
  }

  // ── Formatting ───────────────────────────────────────────────────────────
  protected num(value: number | null | undefined, digits = 4): string {
    if (value === null || value === undefined) return '—';
    if (Number.isInteger(value)) return String(value);
    return Math.abs(value) >= 1000 ? value.toFixed(1) : value.toPrecision(digits);
  }

  protected delta(value: number | null | undefined): string {
    if (value === null || value === undefined) return '—';
    const s = this.num(value);
    return value > 0 ? `+${s}` : s;
  }

  protected pct(value: number | null | undefined): string {
    if (value === null || value === undefined) return '—';
    return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
  }

  /** Colour class for a delta: any change is highlighted, direction-neutral. */
  protected changed(value: number | null | undefined): boolean {
    return value !== null && value !== undefined && value !== 0;
  }

  protected fieldList(fields: Record<string, FieldDiff>): {key: string; diff: FieldDiff}[] {
    return Object.entries(fields).map(([key, diff]) => ({key, diff}));
  }

  protected show(value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'number') return this.num(value);
    return String(value);
  }
}
