import {Component, effect, HostListener, inject, OnDestroy, OnInit, signal} from '@angular/core';

import {FormsModule} from '@angular/forms';
import {NavigationService, ToastService} from '@core/services';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {StatusWebSocketService} from '@core/services/status-websocket.service';
import {SystemStatusService} from '@core/services/system-status.service';
import {ConfigApiService} from '@core/services/api/config-api.service';
import {DagApiService} from '@core/services/api/dag-api.service';
import {ConfigExport, ConfigValidationResponse,} from '@core/models/config.model';
import {ConfigImportDialogComponent} from './components/config-import-dialog/config-import-dialog.component';
import {FlowCanvasComponent} from './components/flow-canvas/flow-canvas.component';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {CanvasEditStoreService} from '@features/settings/services/canvas-edit-store.service';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {DialogService} from '@core/services/dialog.service';
import {NodePluginRegistry} from '@core/services/node-plugin-registry.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css',
  providers: [CanvasEditStoreService],
  imports: [
    FormsModule,
    SynergyComponentsModule,
    ConfigImportDialogComponent,
    FlowCanvasComponent
  ],
})
export class SettingsComponent implements OnInit, OnDestroy {
  protected nodeStore = inject(NodeStoreService);
  protected systemStatus = inject(SystemStatusService);
  protected lidars = this.nodeStore.sensorNodes;
  protected isLoading = this.nodeStore.isLoading;
  protected fusions = this.nodeStore.fusionNodes;
  protected operations = this.nodeStore.operationNodes;
  protected isSystemRunning = this.systemStatus.isRunning;

  // Phase 4.1: feature-scoped canvas edit store
  protected canvasEditStore = inject(CanvasEditStoreService);

  // Phase 7.2: global initializing state — true until both node definitions + DAG config are loaded
  protected isInitializing = signal(true);

  // Import/Export state
  protected isExporting = signal(false);
  protected isImporting = signal(false);
  protected showValidationDialog = signal(false);
  protected validationResult = signal<ConfigValidationResponse | null>(null);
  protected pendingImportConfig = signal<ConfigExport | null>(null);
  protected importMergeMode = signal(false);

  private navService = inject(NavigationService);
  private statusWs = inject(StatusWebSocketService);
  private configApi = inject(ConfigApiService);
  private dagApi = inject(DagApiService);
  private dialog = inject(DialogService);
  private toast = inject(ToastService);
  private pluginRegistry = inject(NodePluginRegistry);

  constructor() {
    // Phase 4.6: dirty indicator title effect
    effect(() => {
      const dirty = this.canvasEditStore.isDirty();
      this.navService.setPageConfig({
        title: dirty ? 'Settings ●' : 'Settings',
        subtitle: 'Configure LiDAR sensors, fusion nodes, and recording settings',
        showActionsSlot: false,
      });
    });

    // Phase 4.5: subscribe to conflict events
    this.canvasEditStore.conflictDetected$
      .pipe(takeUntilDestroyed())
      .subscribe((detail) => {
        this.dialog
          .confirm({
            title: 'DAG Conflict Detected',
            message: `Another save has occurred. Your unsaved changes are preserved but cannot be saved. Click "Sync & Discard" to load the latest configuration.`,
            confirmLabel: 'Sync & Discard My Changes',
            cancelLabel: 'Stay & Keep Editing',
            variant: 'neutral',
          })
          .then((confirmed) => {
            if (confirmed) this.canvasEditStore.syncFromBackend(true);
          });
      });
  }

  async ngOnInit() {
    this.navService.setPageConfig({
      title: 'Settings',
      subtitle: 'Configure LiDAR sensors, fusion nodes, and recording settings',
    });

    // Connect to WebSocket for real-time status updates
    this.statusWs.connect();

    // Phase 7.2: load node definitions + DAG config in parallel so both are
    // available before the canvas becomes interactive (fixes empty palette bug).
    this.isInitializing.set(true);
    try {
      const [dagConfig] = await Promise.all([
        this.dagApi.getDagConfig(),
        this.pluginRegistry.loadFromBackend(),
      ]);
      this.canvasEditStore.initFromBackend(dagConfig);
    } catch (error) {
      console.error('Failed to initialize canvas', error);
      this.toast.danger('Failed to load canvas configuration.');
    } finally {
      this.isInitializing.set(false);
    }
  }

  ngOnDestroy(): void {
    // Disconnect WebSocket when component is destroyed
    this.statusWs.disconnect();
  }

  // Phase 4.4: prevent accidental page-leave when dirty
  @HostListener('window:beforeunload', ['$event'])
  onBeforeUnload(event: BeforeUnloadEvent) {
    if (this.canvasEditStore.isDirty()) {
      event.preventDefault();
    }
  }

  // Phase 4.3: action handlers
  onSaveAndReload() {
    this.canvasEditStore.saveAndReload();
  }

  onSync() {
    this.canvasEditStore.syncFromBackend();
  }

  onReloadRuntime() {
    this.canvasEditStore.reloadRuntime();
  }

  async onStartSystem() {
    try {
      await this.systemStatus.startSystem();
      this.toast.success('Data flow started.');
    } catch (e) {
      console.error(e);
      this.toast.danger('Failed to start data flow.');
    }
  }

  async onStopSystem() {
    try {
      await this.systemStatus.stopSystem();
      this.toast.success('Data flow stopped.');
    } catch (e) {
      console.error(e);
      this.toast.danger('Failed to stop data flow.');
    }
  }

  async onExportConfig() {
    this.isExporting.set(true);
    try {
      const config = await this.configApi.exportConfig();

      // Create blob and download
      const blob = new Blob([JSON.stringify(config, null, 2)], {type: 'application/json'});
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `lidar-config-${new Date().toISOString().split('T')[0]}.json`;
      link.click();
      window.URL.revokeObjectURL(url);

      this.toast.success('Configuration exported successfully.');
    } catch (error) {
      console.error('Failed to export config', error);
      this.toast.danger('Failed to export configuration.');
    } finally {
      this.isExporting.set(false);
    }
  }

  onImportConfigClick() {
    // Trigger file input
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (event: any) => {
      const file = event.target.files?.[0];
      if (file) {
        await this.readAndValidateConfigFile(file);
      }
    };
    input.click();
  }

  onCancelImport() {
    this.showValidationDialog.set(false);
    this.validationResult.set(null);
    this.pendingImportConfig.set(null);
    this.isImporting.set(false);
  }

  async onConfirmImport() {
    const config = this.pendingImportConfig();
    if (!config) return;

    try {
      const result = await this.configApi.importConfig(config, this.importMergeMode());

      this.showValidationDialog.set(false);
      this.validationResult.set(null);
      this.pendingImportConfig.set(null);

      // Phase 4.3: after config import, sync the canvas from the backend
      this.toast.success(
        `Configuration imported: ${result.imported.lidars} lidars, ${result.imported.fusions} fusions.`,
      );
      this.onSync();
    } catch (error) {
      console.error('Failed to import config', error);
      this.toast.danger('Failed to import configuration.');
    } finally {
      this.isImporting.set(false);
    }
  }

  private async readAndValidateConfigFile(file: File) {
    this.isImporting.set(true);
    try {
      const text = await file.text();
      const config = JSON.parse(text) as ConfigExport;

      // Validate the config
      const validation = await this.configApi.validateConfig(config);
      this.validationResult.set(validation);
      this.pendingImportConfig.set(config);
      this.showValidationDialog.set(true);

      if (!validation.valid) {
        this.toast.warning('Configuration has validation errors. Please review.');
      }
    } catch (error) {
      console.error('Failed to read or validate config file', error);
      this.toast.danger('Failed to read configuration file. Please check the file format.');
      this.isImporting.set(false);
    }
  }
}
