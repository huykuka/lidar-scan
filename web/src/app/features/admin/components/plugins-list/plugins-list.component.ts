import {ChangeDetectionStrategy, Component, ElementRef, inject, OnInit, signal, computed, viewChild} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {PluginsApiService, PluginRecord} from '@core/services/api/plugins-api.service';
import { ToastService } from '@core/services';
import { DialogService } from '@core/services/dialog.service';

@Component({
  selector: 'app-plugins-list',
  imports: [SynergyComponentsModule],
  templateUrl: './plugins-list.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PluginsListComponent implements OnInit {
  private pluginsApi = inject(PluginsApiService);
  private toast = inject(ToastService);
  private dialog = inject(DialogService);

  protected plugins = signal<PluginRecord[]>([]);
  protected isLoading = signal(true);
  protected removingPlugin = signal<string | null>(null);
  protected isUploading = signal(false);
  protected isDragOver = signal(false);

  protected loadedCount = computed(() => this.plugins().filter((p) => p.loaded).length);
  protected totalCount = computed(() => this.plugins().length);

  readonly fileInput = viewChild.required<ElementRef<HTMLInputElement>>('fileInput');

  ngOnInit() {
    this.loadPlugins();
  }

  private async loadPlugins() {
    this.isLoading.set(true);
    try {
      this.plugins.set(await this.pluginsApi.listPlugins());
    } catch {
      this.toast.danger('Failed to load plugins.');
    } finally {
      this.isLoading.set(false);
    }
  }

  protected onUploadClick() {
    this.fileInput().nativeElement.click();
  }

  protected async onFileSelected(event: Event) {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (file) await this.uploadFile(file);
    (event.target as HTMLInputElement).value = '';
  }

  protected onDragOver(event: DragEvent) {
    event.preventDefault();
    this.isDragOver.set(true);
  }

  protected onDragLeave() {
    this.isDragOver.set(false);
  }

  protected async onDrop(event: DragEvent) {
    event.preventDefault();
    this.isDragOver.set(false);
    const file = event.dataTransfer?.files?.[0];
    if (file) await this.uploadFile(file);
  }

  private async uploadFile(file: File) {
    if (!file.name.endsWith('.zip')) {
      this.toast.danger('Only .zip archives are supported.');
      return;
    }
    this.isUploading.set(true);
    try {
      const result = await this.pluginsApi.uploadPlugin(file);
      this.toast.success(
        `Plugin "${result.plugin}" installed — ${result.types.length} type(s) registered.`,
      );
      await this.loadPlugins();
    } catch (err: any) {
      this.toast.danger(err?.error?.detail ?? 'Plugin upload failed.');
    } finally {
      this.isUploading.set(false);
    }
  }

  protected async onRemoveClick(plugin: PluginRecord) {
    const confirmed = await this.dialog.confirm({
      title: 'Remove plugin',
      message: `Remove "${plugin.name}"? This will delete it from disk and unregister all its node types.`,
      confirmLabel: 'Remove',
      confirmIcon: 'delete',
      confirmSeverity: 'danger',
    });
    if (!confirmed) return;

    this.removingPlugin.set(plugin.name);
    try {
      await this.pluginsApi.removePlugin(plugin.name);
      this.plugins.update((list) => list.filter((p) => p.name !== plugin.name));
      this.toast.success(`Plugin "${plugin.name}" removed.`);
    } catch (err: any) {
      this.toast.danger(err?.error?.detail ?? `Failed to remove plugin "${plugin.name}".`);
    } finally {
      this.removingPlugin.set(null);
    }
  }
}
