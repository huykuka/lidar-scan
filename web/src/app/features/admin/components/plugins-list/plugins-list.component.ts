import {ChangeDetectionStrategy, Component, ElementRef, inject, OnInit, signal, computed, viewChild} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {PluginsApiService, PluginRecord} from '@core/services/api/plugins-api.service';
import {ToastService} from '@core/services';
import { NodePluginRegistry } from '@core/services/node-plugin-registry.service';

@Component({
  selector: 'app-plugins-list',
  imports: [SynergyComponentsModule],
  templateUrl: './plugins-list.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PluginsListComponent implements OnInit {
  private pluginsApi = inject(PluginsApiService);
  private nodePluginRegistry = inject(NodePluginRegistry);
  private toast = inject(ToastService);

  protected plugins = signal<PluginRecord[]>([]);
  protected isLoading = signal(true);
  protected actionInProgress = signal<string | null>(null);
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

  protected async onToggle(plugin: PluginRecord) {
    this.actionInProgress.set(plugin.name);
    try {
      if (plugin.loaded) {
        await this.pluginsApi.unloadPlugin(plugin.name);
        this.plugins.update((list) =>
          list.map((p) => (p.name === plugin.name ? { ...p, loaded: false, types: [] } : p)),
        );
        this.toast.warning(`Plugin "${plugin.name}" unloaded.`);
      } else {
        const result = await this.pluginsApi.loadPlugin(plugin.name);
        this.plugins.update((list) =>
          list.map((p) =>
            p.name === plugin.name ? { ...p, loaded: true, types: result.types } : p,
          ),
        );
        this.toast.success(
          `Plugin "${plugin.name}" loaded - ${result.types.length} type(s) registered.`,
        );
      }
      // Refresh the node palette so Settings page reflects the change immediately
      await this.nodePluginRegistry.loadFromBackend();
    } catch (err: any) {
      this.toast.danger(err?.error?.detail ?? `Failed to toggle plugin "${plugin.name}".`);
    } finally {
      this.actionInProgress.set(null);
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
        `Plugin "${result.plugin}" installed - ${result.types.length} type(s) registered.`,
      );
      await this.loadPlugins();
      // Refresh the node palette so Settings page reflects the new plugin immediately
      await this.nodePluginRegistry.loadFromBackend();
    } catch (err: any) {
      this.toast.danger(err?.error?.detail ?? 'Plugin upload failed.');
    } finally {
      this.isUploading.set(false);
    }
  }
}
