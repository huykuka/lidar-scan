import {Component, inject, OnDestroy, OnInit, signal, viewChild} from '@angular/core';

import {FormsModule} from '@angular/forms';
import {NavigationService, ToastService} from '@core/services';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NodesApiService} from '@core/services/api/nodes-api.service';
import {StatusWebSocketService} from '@core/services/status-websocket.service';
import {SystemStatusService} from '@core/services/system-status.service';
import {ConfigApiService} from '@core/services/api/config-api.service';
import {ConfigExport, ConfigValidationResponse,} from '@core/models/config.model';
import {ConfigImportDialogComponent} from './components/config-import-dialog/config-import-dialog.component';
import {FlowCanvasComponent} from './components/flow-canvas/flow-canvas.component';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {RecordingStoreService} from '@core/services/stores/recording-store.service';
import {LidarProfilesApiService} from '@core/services/api/lidar-profiles-api';

@Component({
  selector: 'app-settings',
  standalone: true,
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css',
  imports: [
    FormsModule,
    SynergyComponentsModule,
    ConfigImportDialogComponent,
    FlowCanvasComponent
  ],
})
export class SettingsComponent implements OnInit, OnDestroy {
  readonly flowCanvas = viewChild.required(FlowCanvasComponent);
  protected nodeStore = inject(NodeStoreService);
  protected systemStatus = inject(SystemStatusService);
  protected lidars = this.nodeStore.sensorNodes;
  protected isLoading = this.nodeStore.isLoading;
  protected fusions = this.nodeStore.fusionNodes;
  protected operations = this.nodeStore.operationNodes;
  protected isSystemRunning = this.systemStatus.isRunning;
  // Loading state for individual nodes

  // Import/Export state
  protected isExporting = signal(false);
  protected isImporting = signal(false);
  protected showValidationDialog = signal(false);
  protected validationResult = signal<ConfigValidationResponse | null>(null);
  protected pendingImportConfig = signal<ConfigExport | null>(null);
  protected importMergeMode = signal(false);

  // Computed signal for unsaved changes
  protected hasUnsavedChanges = signal(false);
  private navService = inject(NavigationService);
  private lidarProfilesApi = inject(LidarProfilesApiService);
  private nodesApi = inject(NodesApiService);
  private statusWs = inject(StatusWebSocketService);
  private configApi = inject(ConfigApiService);
  private recordingStore = inject(RecordingStoreService);
  private toast = inject(ToastService);

  async ngOnInit() {
    this.navService.setPageConfig({
      title: 'Settings',
      subtitle: 'Configure LiDAR sensors, fusion nodes, and recording settings',
    });
    await this.loadConfig();

    // Connect to WebSocket for real-time status updates
    this.statusWs.connect();
  }

  ngOnDestroy(): void {
    // Disconnect WebSocket when component is destroyed
    this.statusWs.disconnect();
  }

  async loadConfig() {
    this.nodeStore.set('isLoading', true);
    try {
      const [nodes, definitions] = await Promise.all([
        this.nodesApi.getNodes(),
        this.nodesApi.getNodeDefinitions(),
        this.recordingStore.loadRecordings(),
      ]);
      this.nodeStore.set('nodes', nodes);
      this.nodeStore.set('nodeDefinitions', definitions);
      this.nodeStore.set('isLoading', false);
    } catch (error) {
      console.error('Failed to load configuration', error);
      this.toast.warning('Unable to load configuration.');
      this.nodeStore.set('isLoading', false);
    }
  }

  async onReloadConfig() {
    try {
      // Save any unsaved node positions before reloading
      const flowCanvas = this.flowCanvas();
      if (flowCanvas && flowCanvas.hasUnsavedChanges()) {
        await flowCanvas.saveAllPositions();
      }

      await this.nodesApi.reloadConfig();
      // Refresh LiDAR profiles to get any backend updates
      await this.lidarProfilesApi.loadProfiles();
      await this.loadConfig();
      this.toast.success('Configuration and LiDAR profiles reloaded.');
    } catch (error) {
      console.error('Failed to reload config:', error);
      this.toast.danger('Failed to reload backend configuration.');
    }
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

      await this.onReloadConfig();

      this.toast.success(
        `Configuration imported: ${result.imported.lidars} lidars, ${result.imported.fusions} fusions.`,
      );
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
