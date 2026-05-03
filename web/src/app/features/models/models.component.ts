import {Component, computed, ElementRef, inject, OnInit, signal, ViewChild} from '@angular/core';
import {DatePipe} from '@angular/common';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {DetectionModelApiService} from '@core/services/api/detection-model-api.service';
import {NavigationService} from '@core/services';
import {DetectionModel} from '@core/models';
import {DialogService} from '@core/services/dialog.service';
import {firstValueFrom} from 'rxjs';

@Component({
  selector: 'app-models',
  standalone: true,
  imports: [SynergyComponentsModule, DatePipe],
  templateUrl: './models.component.html',
  styleUrl: './models.component.css',
})
export class ModelsComponent implements OnInit {
  @ViewChild('fileInput') private fileInputRef!: ElementRef<HTMLInputElement>;

  private modelApi = inject(DetectionModelApiService);
  private navService = inject(NavigationService);
  private dialogService = inject(DialogService);

  protected models = signal<DetectionModel[]>([]);
  protected isLoading = signal(false);
  protected isUploading = signal(false);
  protected uploadError = signal<string | null>(null);
  protected searchQuery = signal('');

  // Upload form fields
  protected uploadDisplayName = signal('');
  protected uploadModelType = signal('pointpillars');
  protected uploadDescription = signal('');

  protected filteredModels = computed(() => {
    const query = this.searchQuery().toLowerCase();
    const all = this.models();
    if (!query) return all;
    return all.filter(
      (m) =>
        m.display_name.toLowerCase().includes(query) ||
        m.model_type.toLowerCase().includes(query) ||
        m.filename.toLowerCase().includes(query),
    );
  });

  async ngOnInit(): Promise<void> {
    this.navService.setPageConfig({
      title: 'Models',
      subtitle: 'Upload and manage detection model checkpoints',
    });
    await this.loadModels();
  }

  protected async loadModels(): Promise<void> {
    this.isLoading.set(true);
    try {
      const response = await firstValueFrom(this.modelApi.listModels());
      this.models.set(response.models);
    } catch (error) {
      console.error('Failed to load models:', error);
    } finally {
      this.isLoading.set(false);
    }
  }

  protected triggerUpload(): void {
    this.fileInputRef.nativeElement.click();
  }

  protected async onFileSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    this.isUploading.set(true);
    this.uploadError.set(null);

    try {
      await firstValueFrom(
        this.modelApi.uploadModel(
          file,
          this.uploadDisplayName() || undefined,
          this.uploadModelType() || undefined,
          this.uploadDescription() || undefined,
        ),
      );
      // Reset form
      this.uploadDisplayName.set('');
      this.uploadDescription.set('');
      await this.loadModels();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Upload failed';
      this.uploadError.set(message);
    } finally {
      this.isUploading.set(false);
      input.value = '';
    }
  }

  protected async confirmDelete(model: DetectionModel): Promise<void> {
    const confirmed = await this.dialogService.confirm({
      title: 'Delete Model',
      message: `Are you sure you want to delete <strong>${model.display_name}</strong>? This action cannot be undone.`,
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });

    if (!confirmed) return;

    try {
      await firstValueFrom(this.modelApi.deleteModel(model.id));
      await this.loadModels();
    } catch (error) {
      console.error('Failed to delete model:', error);
    }
  }

  protected formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  }

  protected formatDate(timestamp: number): Date {
    return new Date(timestamp * 1000);
  }
}
