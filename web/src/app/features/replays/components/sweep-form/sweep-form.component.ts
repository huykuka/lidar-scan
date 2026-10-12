import {ChangeDetectionStrategy, Component, computed, effect, inject, input, OnInit, signal} from '@angular/core';
import {FormControl, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {NodeDefinition, PropertySchema} from '@core/models/node.model';
import {Sweep} from '@core/models';
import {NodesApiService} from '@core/services/api/nodes-api.service';
import {ReplayApiService} from '@core/services/api/replay-api.service';
import {DrawerService} from '@core/services/drawer.service';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {RecordingStoreService} from '@core/services/stores/recording-store.service';
import {ToastService} from '@core/services/toast.service';
import {formatOverrideValue} from '../../utils/override-values';
import {downstreamNodes} from '../../utils/replay-graph';
import {
  defaultRange,
  describeValues,
  isSweepable,
  MAX_SWEEP_RUNS,
  parseNumberList,
  plannedRuns,
  rangeValues,
} from '../../utils/sweep-values';

type ValueMode = 'range' | 'list';

/**
 * Drawer content for a parameter sweep: pick one parameter and a set of values, and the app
 * replays the recording once per value.  The drawer host's primary button submits the <form>.
 */
@Component({
  selector: 'app-sweep-form',
  imports: [ReactiveFormsModule, SynergyComponentsModule, SynergyFormsModule],
  templateUrl: './sweep-form.component.html',
  styleUrl: './sweep-form.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SweepFormComponent implements OnInit {
  /** Called with the created sweep (so the page can open it). */
  readonly onStarted = input<((sweep: Sweep) => void) | undefined>(undefined);

  private readonly api = inject(ReplayApiService);
  private readonly nodesApi = inject(NodesApiService);
  private readonly drawer = inject(DrawerService);
  private readonly toast = inject(ToastService);
  private readonly nodeStore = inject(NodeStoreService);
  private readonly recordingStore = inject(RecordingStoreService);

  protected readonly maxRuns = MAX_SWEEP_RUNS;
  protected readonly isSubmitting = signal(false);
  private readonly fetchedDefinitions = signal<NodeDefinition[]>([]);
  private readonly definitions = computed(() => {
    const stored = this.nodeStore.nodeDefinitions();
    return stored.length > 0 ? stored : this.fetchedDefinitions();
  });

  // NOTE: DrawerHost drives its primary button from the first AbstractControl property.
  readonly form = new FormGroup(
    {
      label: new FormControl('', {nonNullable: true, validators: [Validators.maxLength(80)]}),
      playbackNodeId: new FormControl('', {nonNullable: true, validators: [Validators.required]}),
      recordingId: new FormControl('', {nonNullable: true, validators: [Validators.required]}),
      nodeId: new FormControl('', {nonNullable: true, validators: [Validators.required]}),
      parameter: new FormControl('', {nonNullable: true, validators: [Validators.required]}),
    },
    {validators: () => (this.valuesError() ? {values: true} : null)},
  );

  // Form values mirrored as signals so computed state can react to them.
  private readonly playbackNodeId = signal('');
  protected readonly nodeId = signal('');
  protected readonly parameter = signal('');

  // ── How the values are chosen ────────────────────────────────────────────
  protected readonly mode = signal<ValueMode>('range');
  protected readonly start = signal('');
  protected readonly end = signal('');
  protected readonly step = signal('');
  protected readonly listText = signal('');
  /** For select parameters: indexes of the chosen options. */
  protected readonly chosenOptions = signal<number[]>([]);
  protected readonly includeCurrent = signal(true);
  protected readonly keepClouds = signal(false);

  protected readonly recordings = computed(() =>
    this.recordingStore.recordings().filter((r) => (r.status ?? 'ready') === 'ready'),
  );
  protected readonly playbackNodes = computed(() =>
    this.nodeStore.nodes().filter((n) => n.type === 'playback' && n.enabled),
  );
  /** Nodes that run in the replay, excluding the playback source itself. */
  protected readonly sweepTargets = computed(() =>
    downstreamNodes(this.playbackNodeId(), this.nodeStore.nodes(), this.nodeStore.edges()).filter(
      (n) => n.id !== this.playbackNodeId(),
    ),
  );
  protected readonly properties = computed<PropertySchema[]>(() => {
    const node = this.nodeStore.nodes().find((n) => n.id === this.nodeId());
    const def = this.definitions().find((d) => d.type === node?.type);
    return (def?.properties ?? []).filter(isSweepable);
  });
  protected readonly prop = computed(() => this.properties().find((p) => p.name === this.parameter()));
  protected readonly currentValue = computed(() => {
    const node = this.nodeStore.nodes().find((n) => n.id === this.nodeId());
    const saved = node?.config?.[this.parameter()];
    return saved !== undefined && saved !== null && saved !== '' ? saved : this.prop()?.default;
  });

  /** Values to run, or the reason they are not valid yet. */
  protected readonly valuesResult = computed<{values: unknown[]; error: string | null}>(() => {
    const prop = this.prop();
    if (!prop) return {values: [], error: 'Choose a parameter'};
    if (prop.type === 'boolean') return {values: [true, false], error: null};
    if (prop.type === 'select') {
      const options = prop.options ?? [];
      const values = this.chosenOptions().map((i) => options[i]?.value);
      return values.length ? {values, error: null} : {values: [], error: 'Choose at least one option'};
    }
    return this.mode() === 'range'
      ? rangeValues(Number(this.start()), Number(this.end()), Number(this.step()))
      : parseNumberList(this.listText());
  });
  protected readonly valuesError = computed(() => this.valuesResult().error);
  protected readonly runCount = computed(() =>
    plannedRuns(this.valuesResult().values, this.currentValue(), this.includeCurrent()),
  );
  protected readonly overLimit = computed(() => this.runCount() > MAX_SWEEP_RUNS);
  protected readonly preview = computed(() => describeValues(this.valuesResult().values));
  protected readonly currentText = computed(() => formatOverrideValue(this.currentValue()));

  constructor() {
    if (this.nodeStore.nodeDefinitions().length === 0) {
      this.nodesApi
        .getNodeDefinitions()
        .then((defs) => this.fetchedDefinitions.set(defs))
        .catch(() => undefined);
    }

    // Keep the form's validity in step with the values (the host reads it for its button).
    effect(() => {
      this.valuesResult();
      this.overLimit();
      this.form.updateValueAndValidity();
    });
  }

  ngOnInit(): void {
    const f = this.form.controls;
    f.playbackNodeId.valueChanges.subscribe((v) => {
      this.playbackNodeId.set(v);
      f.nodeId.setValue('');
      f.parameter.setValue('');
    });
    f.nodeId.valueChanges.subscribe((v) => {
      this.nodeId.set(v);
      f.parameter.setValue('');
    });
    f.parameter.valueChanges.subscribe((v) => {
      this.parameter.set(v);
      this.resetValuesFor(this.prop());
    });

    const nodes = this.playbackNodes();
    if (nodes.length === 1) f.playbackNodeId.setValue(nodes[0].id);
  }

  /** Fill sensible defaults whenever the parameter changes. */
  private resetValuesFor(prop: PropertySchema | undefined): void {
    this.chosenOptions.set((prop?.options ?? []).map((_, i) => i));
    if (prop?.type !== 'number') return;
    const r = defaultRange(this.currentValue(), prop);
    this.start.set(String(r.start));
    this.end.set(String(r.end));
    this.step.set(String(r.step));
    this.listText.set('');
  }

  protected isChosen(index: number): boolean {
    return this.chosenOptions().includes(index);
  }

  protected toggleOption(index: number, checked: boolean): void {
    this.chosenOptions.update((list) =>
      checked ? [...new Set([...list, index])].sort((a, b) => a - b) : list.filter((i) => i !== index),
    );
  }

  protected setMode(mode: string): void {
    if (mode === 'range' || mode === 'list') this.mode.set(mode);
  }

  /** Called by the drawer host's primary button (via form submit). */
  onSubmit(): void {
    if (this.form.invalid || this.overLimit() || this.isSubmitting()) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    this.isSubmitting.set(true);
    this.api
      .startSweep({
        recording_id: raw.recordingId,
        playback_node_id: raw.playbackNodeId,
        node_id: raw.nodeId,
        parameter: raw.parameter,
        values: this.valuesResult().values,
        label: raw.label.trim(),
        include_current: this.includeCurrent(),
        // Omit for the default capture; [] stores no point clouds.
        ...(this.keepClouds() ? {} : {capture_nodes: []}),
      })
      .subscribe({
        next: (sweep) => {
          this.isSubmitting.set(false);
          this.toast.success(`Sweep started: ${sweep.progress?.total ?? this.runCount()} runs queued`);
          this.onStarted()?.(sweep);
          this.drawer.close();
        },
        error: () => this.isSubmitting.set(false), // http-toast interceptor shows the error
      });
  }
}
