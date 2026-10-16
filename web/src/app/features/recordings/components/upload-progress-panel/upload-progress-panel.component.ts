import {ChangeDetectionStrategy, Component, computed, inject, signal} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {RecordingUploadService} from '@core/services/recording-upload.service';

@Component({
  selector: 'app-upload-progress-panel',
  imports: [SynergyComponentsModule],
  templateUrl: './upload-progress-panel.component.html',
  styleUrl: './upload-progress-panel.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UploadProgressPanelComponent {
  protected uploader = inject(RecordingUploadService);
  protected collapsed = signal(false);

  protected items = this.uploader.items;
  protected doneCount = computed(() => this.items().filter((i) => i.status === 'done').length);
  protected activeCount = computed(
    () => this.items().filter((i) => i.status === 'queued' || i.status === 'uploading' || i.status === 'processing').length,
  );
  protected overall = computed(() => {
    const list = this.items();
    return list.length ? Math.round(list.reduce((a, i) => a + i.progress, 0) / list.length) : 0;
  });
}
