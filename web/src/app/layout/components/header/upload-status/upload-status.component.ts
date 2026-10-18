import {NgTemplateOutlet} from '@angular/common';
import {ChangeDetectionStrategy, Component, computed, inject, input, signal} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {RecordingUploadService} from '@core/services/recording-upload.service';

/**
 * Recording import progress (browser -> app).
 * Hidden until a file is queued; shows a progress ring while active and a check when done.
 * The dropdown lists every file with cancel / retry / dismiss. Survives page navigation
 * because the queue lives in RecordingUploadService (root).
 */
@Component({
  selector: 'app-upload-status',
  imports: [SynergyComponentsModule, NgTemplateOutlet],
  templateUrl: './upload-status.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host {
      display: inline-flex;
      position: relative;
      align-items: center;
    }
    .upload-idle {
      color: var(--syn-color-neutral-500);
    }
    .upload-active {
      color: var(--syn-color-primary-600);
    }
    .upload-done {
      color: var(--syn-color-success-600);
    }
    .upload-panel {
      width: 360px;
      max-width: calc(100vw - 2rem);
      padding: 12px 14px;
      background: var(--syn-panel-background-color, var(--syn-color-neutral-0));
      border: 1px solid var(--syn-color-neutral-300);
      box-shadow: var(--syn-shadow-large);
    }
  `,
})
export class UploadStatusComponent {
  readonly mobile = input(false);

  protected readonly uploader = inject(RecordingUploadService);
  protected readonly dropdownOpen = signal(false);

  protected readonly items = this.uploader.items;
  protected readonly doneCount = computed(() => this.items().filter((i) => i.status === 'done').length);
  protected readonly activeCount = computed(
    () => this.items().filter((i) => i.status === 'queued' || i.status === 'uploading' || i.status === 'processing').length,
  );
  protected readonly overall = computed(() => {
    const list = this.items();
    return list.length ? Math.round(list.reduce((a, i) => a + i.progress, 0) / list.length) : 0;
  });
  protected readonly label = computed(() =>
    this.items().length === 0 ? 'No uploads' : this.activeCount() > 0 ? `Uploading ${this.doneCount()}/${this.items().length} (${this.overall()}%)` : 'Uploads complete',
  );

  protected clear(): void {
    this.uploader.clearFinished();
    this.dropdownOpen.set(false);
  }
}
