import {ChangeDetectionStrategy, Component, computed, DestroyRef, inject, input, OnInit, signal} from '@angular/core';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {GroundTruthTarget, ReplayRun} from '@core/models';
import {ReplayApiService} from '@core/services/api/replay-api.service';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {RecordingStoreService} from '@core/services/stores/recording-store.service';
import {ToastService} from '@core/services/toast.service';
import {allMetrics, latestMetricStats} from '../../utils/run-metrics';
import {formatNumber} from '../../utils/score-format';

/**
 * Drawer content: the value a metric should have for a recording ("ground truth").
 * Runs of that recording are then scored against it.
 */
@Component({
  selector: 'app-ground-truth',
  imports: [SynergyComponentsModule],
  templateUrl: './ground-truth.component.html',
  styleUrl: './ground-truth.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class GroundTruthComponent implements OnInit {
  /** Recording to start with (e.g. the one of the run being looked at). */
  readonly recordingId = input<string>('');
  /** Called whenever targets were added or removed so the caller can refresh scores. */
  readonly onChanged = input<(() => void) | undefined>(undefined);

  private readonly api = inject(ReplayApiService);
  private readonly toast = inject(ToastService);
  private readonly recordingStore = inject(RecordingStoreService);
  private readonly nodeStore = inject(NodeStoreService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly recordings = computed(() => this.recordingStore.recordings());
  protected readonly selectedRecording = signal('');
  protected readonly targets = signal<GroundTruthTarget[]>([]);
  protected readonly runs = signal<ReplayRun[]>([]);
  protected readonly isLoading = signal(false);
  protected readonly isSaving = signal(false);

  // New-target form
  protected readonly nodeId = signal('');
  protected readonly metricKey = signal('');
  protected readonly expected = signal('');
  protected readonly tolerance = signal('');
  protected readonly label = signal('');

  private readonly metrics = computed(() => allMetrics(this.runs()));
  protected readonly nodeOptions = computed(() => {
    const seen = new Map<string, string>();
    for (const m of this.metrics()) seen.set(m.nodeId, m.nodeName);
    return [...seen].map(([id, name]) => ({id, name}));
  });
  protected readonly keyOptions = computed(() =>
    this.metrics().filter((m) => m.nodeId === this.nodeId()).map((m) => m.key),
  );
  protected readonly observed = computed(() =>
    this.nodeId() && this.metricKey() ? latestMetricStats(this.runs(), this.nodeId(), this.metricKey()) : null,
  );
  protected readonly expectedNumber = computed(() => (this.expected().trim() === '' ? NaN : Number(this.expected())));
  protected readonly toleranceNumber = computed(() => (this.tolerance().trim() === '' ? null : Number(this.tolerance())));
  protected readonly canAdd = computed(
    () =>
      !!this.selectedRecording() &&
      !!this.nodeId() &&
      !!this.metricKey() &&
      Number.isFinite(this.expectedNumber()) &&
      (this.toleranceNumber() === null || (Number.isFinite(this.toleranceNumber()!) && this.toleranceNumber()! >= 0)) &&
      !this.isSaving(),
  );

  ngOnInit(): void {
    const initial = this.recordingId() || this.recordings()[0]?.id || '';
    if (initial) this.selectRecording(initial);
  }

  protected selectRecording(id: string): void {
    this.selectedRecording.set(id);
    this.nodeId.set('');
    this.metricKey.set('');
    this.targets.set([]);
    this.runs.set([]);
    if (!id) return;
    this.isLoading.set(true);
    this.api.listTargets(id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe((r) => this.targets.set(r.targets));
    // Include sweep runs: they hold most of the measured metrics.
    this.api
      .listReplays(id, true)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (r) => {
          this.runs.set(r.runs);
          this.isLoading.set(false);
        },
        error: () => this.isLoading.set(false),
      });
  }

  protected selectNode(id: string): void {
    this.nodeId.set(id);
    this.metricKey.set('');
  }

  protected nodeName(id: string): string {
    return this.nodeStore.nodes().find((n) => n.id === id)?.name ?? id.slice(0, 8);
  }

  protected fmt(value: number | null | undefined): string {
    return formatNumber(value);
  }

  protected add(): void {
    if (!this.canAdd()) return;
    this.isSaving.set(true);
    this.api
      .createTarget({
        recording_id: this.selectedRecording(),
        node_id: this.nodeId(),
        metric_key: this.metricKey(),
        expected: this.expectedNumber(),
        tolerance: this.toleranceNumber(),
        label: this.label().trim(),
      })
      .subscribe({
        next: (target) => {
          this.targets.update((t) => [...t, target]);
          this.isSaving.set(false);
          this.expected.set('');
          this.tolerance.set('');
          this.label.set('');
          this.toast.success('Ground truth saved');
          this.onChanged()?.();
        },
        error: () => this.isSaving.set(false),
      });
  }

  protected remove(target: GroundTruthTarget): void {
    this.api.deleteTarget(target.id).subscribe(() => {
      this.targets.update((t) => t.filter((x) => x.id !== target.id));
      this.onChanged()?.();
    });
  }
}
