import {ChangeDetectionStrategy, Component, computed, DestroyRef, inject, input, OnInit, signal} from '@angular/core';
import {takeUntilDestroyed, toSignal} from '@angular/core/rxjs-interop';
import {catchError, forkJoin, map, of} from 'rxjs';
import {FormArray, FormControl, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {NodesApiService} from '@core/services/api/nodes-api.service';
import {ReplayApiService} from '@core/services/api/replay-api.service';
import {NodeConfig, NodeDefinition, PropertySchema} from '@core/models/node.model';
import {ReplayPrefill} from '../../utils/clone-run';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {RecordingStoreService} from '@core/services/stores/recording-store.service';
import {DrawerService} from '@core/services/drawer.service';
import {ToastService} from '@core/services/toast.service';
import {defaultCaptureIds, downstreamNodes} from '../../utils/replay-graph';
import {
  formatOverrideValue,
  overridableProperties,
  overrideRowValidator,
  parseOverrideValue,
  resolveOverrideValue,
} from '../../utils/override-values';

export {formatOverrideValue, overridableProperties, overrideRowValidator, parseOverrideValue, resolveOverrideValue};

/**
 * Drawer content for starting a replay run.
 * The drawer host's "Save" button submits this component's <form>.
 */
@Component({
  selector: 'app-replay-form',
  imports: [ReactiveFormsModule, SynergyComponentsModule, SynergyFormsModule],
  templateUrl: './replay-form.component.html',
  styleUrl: './replay-form.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReplayFormComponent implements OnInit {
  /** Called after the run has been accepted by the backend. */
  readonly onStarted = input<(() => void) | undefined>(undefined);
  /** Values to start from (used to re-run an earlier run with changes). */
  readonly prefill = input<ReplayPrefill | null>(null);

  private readonly api = inject(ReplayApiService);
  private readonly nodesApi = inject(NodesApiService);
  private readonly drawer = inject(DrawerService);
  private readonly toast = inject(ToastService);
  private readonly nodeStore = inject(NodeStoreService);
  private readonly recordingStore = inject(RecordingStoreService);

  protected readonly isSubmitting = signal(false);
  private readonly fetchedDefinitions = signal<NodeDefinition[]>([]);
  private readonly definitions = computed(() => {
    const stored = this.nodeStore.nodeDefinitions();
    return stored.length > 0 ? stored : this.fetchedDefinitions();
  });

  protected readonly recordings = computed(() =>
    this.recordingStore.recordings().filter((r) => (r.status ?? 'ready') === 'ready'),
  );
  protected readonly playbackNodes = computed(() =>
    this.nodeStore.nodes().filter((n) => n.type === 'playback' && n.enabled),
  );
  protected readonly overrideTargets = computed(() =>
    this.nodeStore.nodes().filter((n) => n.type !== 'playback' && n.enabled),
  );

  // NOTE: DrawerHost looks for the first AbstractControl property to drive its Save button.
  readonly form = new FormGroup({
    label: new FormControl('', {nonNullable: true, validators: [Validators.maxLength(80)]}),
    playbackNodeId: new FormControl('', {nonNullable: true, validators: [Validators.required]}),
    /** One or more recordings; a separate run is started for each. */
    recordingIds: new FormControl<string[]>([], {nonNullable: true, validators: [Validators.required]}),
    overrides: new FormArray<FormGroup>([]),
  });

  // ── Point clouds to capture for visual diff ──────────────────────────────
  private readonly selectedPlaybackId = toSignal(this.form.controls.playbackNodeId.valueChanges, {
    initialValue: '',
  });
  /** Nodes that will run in the replay (everything downstream of the playback node). */
  protected readonly capturableNodes = computed(() =>
    downstreamNodes(this.selectedPlaybackId(), this.nodeStore.nodes(), this.nodeStore.edges()),
  );
  private readonly defaultCapture = computed(() =>
    defaultCaptureIds(this.capturableNodes(), this.nodeStore.edges()),
  );
  /** User's explicit choice; ``null`` means "use the default for the chosen playback node". */
  private readonly captureOverride = signal<string[] | null>(null);
  protected readonly captureIds = computed(() => this.captureOverride() ?? this.defaultCapture());

  constructor() {
    this.form.controls.playbackNodeId.valueChanges
      .pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(() => this.captureOverride.set(null));

    // The store only has definitions once the Settings page was visited; fetch them otherwise.
    if (this.nodeStore.nodeDefinitions().length === 0) {
      this.nodesApi
        .getNodeDefinitions()
        .then((defs) => this.fetchedDefinitions.set(defs))
        .catch(() => undefined);
    }

    // Pre-select when there is only one playback node (and its current recording, if known).
    const nodes = this.playbackNodes();
    if (nodes.length === 1) {
      this.form.controls.playbackNodeId.setValue(nodes[0].id);
      const current = nodes[0].config?.['recording_id'];
      if (current && this.recordings().some((r) => r.id === current)) {
        this.form.controls.recordingIds.setValue([current]);
      }
    }
  }

  protected isCaptured(nodeId: string): boolean {
    return this.captureIds().includes(nodeId);
  }

  protected toggleCapture(nodeId: string, checked: boolean): void {
    const current = this.captureIds().filter((id) => id !== nodeId);
    this.captureOverride.set(checked ? [...current, nodeId] : current);
  }

  private recordingName(id: string): string {
    return this.recordings().find((r) => r.id === id)?.name ?? id.slice(0, 8);
  }

  protected get overrideRows(): FormGroup[] {
    return this.form.controls.overrides.controls;
  }

  protected addOverride(initial?: {nodeId: string; key: string; value: string}): void {
    const row = (
      new FormGroup(
        {
          nodeId: new FormControl(initial?.nodeId ?? '', {nonNullable: true}),
          key: new FormControl(initial?.key ?? '', {nonNullable: true}),
          value: new FormControl(initial?.value ?? '', {nonNullable: true}),
        },
        {validators: overrideRowValidator},
      )
    );
    // Changing the node invalidates the parameter; changing the parameter prefills its saved value.
    row.controls['nodeId'].valueChanges.subscribe(() => {
      row.patchValue({key: '', value: ''}, {emitEvent: false});
    });
    row.controls['key'].valueChanges.subscribe((key: string) => {
      const {nodeId} = row.getRawValue();
      row.patchValue({value: this.currentValueText(nodeId, key)}, {emitEvent: false});
    });
    this.form.controls.overrides.push(row);
  }

  ngOnInit(): void {
    const prefill = this.prefill();
    if (!prefill) return;
    const f = this.form.controls;
    // Setting the playback node resets the capture choice, so apply the choice afterwards.
    f.playbackNodeId.setValue(prefill.playbackNodeId);
    f.recordingIds.setValue([prefill.recordingId]);
    f.label.setValue(prefill.label);
    if (prefill.captureNodes !== null) this.captureOverride.set(prefill.captureNodes);
    for (const row of prefill.overrides) this.addOverride(row);
  }

  private nodeById(nodeId: string): NodeConfig | undefined {
    return this.nodeStore.nodes().find((n) => n.id === nodeId);
  }

  /** Parameters offered for the node picked in an override row. */
  protected propertiesFor(nodeId: string): PropertySchema[] {
    const node = this.nodeById(nodeId);
    return overridableProperties(this.definitions().find((d) => d.type === node?.type));
  }

  protected propertyFor(nodeId: string, key: string): PropertySchema | undefined {
    return this.propertiesFor(nodeId).find((p) => p.name === key);
  }

  /** The value currently saved in the pipeline (falls back to the schema default). */
  protected currentValueText(nodeId: string, key: string): string {
    const node = this.nodeById(nodeId);
    const prop = this.propertyFor(nodeId, key);
    const saved = node?.config?.[key];
    return formatOverrideValue(saved !== undefined && saved !== null && saved !== '' ? saved : prop?.default);
  }

  protected removeOverride(index: number): void {
    this.form.controls.overrides.removeAt(index);
  }

  /** Called by the drawer host's Save button (via form submit). */
  onSubmit(): void {
    if (this.form.invalid || this.isSubmitting()) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const overrides: Record<string, Record<string, unknown>> = {};
    for (const row of raw.overrides as {nodeId: string; key: string; value: string}[]) {
      if (!row.nodeId || !row.key.trim()) continue;
      const prop = this.propertyFor(row.nodeId, row.key.trim());
      const value = resolveOverrideValue(prop, row.value);
      if (value === undefined) {
        this.toast.danger(`Invalid value for "${prop?.label ?? row.key}"`);
        return;
      }
      (overrides[row.nodeId] ??= {})[row.key.trim()] = value;
    }

    this.isSubmitting.set(true);
    const recordingIds = raw.recordingIds;
    const label = raw.label.trim();
    const requests = recordingIds.map((recordingId) =>
      this.api
        .startReplay({
          recording_id: recordingId,
          playback_node_id: raw.playbackNodeId,
          // A shared label would be ambiguous across recordings, so append the recording name.
          label: label && recordingIds.length > 1 ? `${label} · ${this.recordingName(recordingId)}` : label,
          overrides,
          capture_nodes: this.captureIds(),
        })
        .pipe(
          map(() => true),
          catchError(() => of(false)), // http-toast interceptor shows the error
        ),
    );
    forkJoin(requests).subscribe((results) => {
      this.isSubmitting.set(false);
      const started = results.filter(Boolean).length;
      if (started === 0) return; // keep the drawer open so the user can retry
      this.toast.success(started === 1 ? 'Replay started' : `${started} replays started`);
      if (started < results.length) this.toast.warning(`${results.length - started} replay(s) could not be started`);
      this.onStarted()?.();
      this.drawer.close();
    });
  }
}
