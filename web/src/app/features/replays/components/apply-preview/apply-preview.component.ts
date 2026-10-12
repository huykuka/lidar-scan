import {ChangeDetectionStrategy, Component, computed, inject, input, OnInit, signal} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {ApplyPreview} from '@core/models';
import {ReplayApiService} from '@core/services/api/replay-api.service';
import {DrawerService} from '@core/services/drawer.service';
import {ToastService} from '@core/services/toast.service';
import {formatOverrideValue} from '../../utils/override-values';

/** Drawer content: review what a run would change in the live pipeline, then apply it. */
@Component({
  selector: 'app-apply-preview',
  imports: [SynergyComponentsModule],
  templateUrl: './apply-preview.component.html',
  styleUrl: './apply-preview.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplyPreviewComponent implements OnInit {
  readonly runId = input.required<string>();
  /** Called after the parameters were written to the pipeline. */
  readonly onApplied = input<(() => void) | undefined>(undefined);

  private readonly api = inject(ReplayApiService);
  private readonly drawer = inject(DrawerService);
  private readonly toast = inject(ToastService);

  protected readonly preview = signal<ApplyPreview | null>(null);
  protected readonly isLoading = signal(true);
  protected readonly isApplying = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly changes = computed(() => this.preview()?.changes.filter((c) => c.changed) ?? []);
  protected readonly unchanged = computed(() => this.preview()?.changes.filter((c) => !c.changed && c.node_exists) ?? []);
  protected readonly canApply = computed(
    () => this.changes().length > 0 && (this.preview()?.missing_nodes.length ?? 0) === 0 && !this.isApplying(),
  );

  ngOnInit(): void {
    this.api.previewApply(this.runId()).subscribe({
      next: (p) => {
        this.preview.set(p);
        this.isLoading.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'Could not load the preview.');
        this.isLoading.set(false);
      },
    });
  }

  protected show(value: unknown): string {
    const text = formatOverrideValue(value);
    return text === '' ? '—' : text;
  }

  protected close(): void {
    this.drawer.close();
  }

  protected apply(): void {
    if (!this.canApply()) return;
    this.isApplying.set(true);
    this.api.applyToPipeline(this.runId()).subscribe({
      next: (res) => {
        this.isApplying.set(false);
        this.toast.success(`Applied ${res.applied.length} parameter(s) to the pipeline`);
        this.onApplied()?.();
        this.drawer.close();
      },
      // 401/403/409 etc. are shown by the http-toast interceptor.
      error: () => this.isApplying.set(false),
    });
  }
}
