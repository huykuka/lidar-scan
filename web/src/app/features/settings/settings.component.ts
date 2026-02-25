import { Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NavigationService } from '../../core/services/navigation.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarApiService } from '../../core/services/api/lidar-api.service';
import { FusionApiService } from '../../core/services/api/fusion-api.service';
import { NodesApiService } from '../../core/services/api/nodes-api.service';
import { StatusWebSocketService } from '../../core/services/status-websocket.service';
import { SystemStatusService } from '../../core/services/system-status.service';
import { ConfigApiService } from '../../core/services/api/config-api.service';
import { ConfigExport, ConfigValidationResponse } from '../../core/models/config.model';
import { NodeConfig } from '../../core/models/node.model';
import { DynamicNodeEditorComponent } from './components/dynamic-node-editor/dynamic-node-editor.component';
import { NodeCardComponent } from './components/node-card/node-card.component';
import { ConfigImportDialogComponent } from './components/config-import-dialog/config-import-dialog.component';
import { FlowCanvasComponent } from './components/flow-canvas/flow-canvas.component';
import { NodeStoreService } from '../../core/services/stores/node-store.service';
import { RecordingStoreService } from '../../core/services/stores/recording-store.service';
import { DialogService } from '../../core/services';
import { ToastService } from '../../core/services/toast.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css',
  imports: [
    CommonModule,
    FormsModule,
    SynergyComponentsModule,
    ConfigImportDialogComponent,
    FlowCanvasComponent,
  ],
})
export class SettingsComponent implements OnInit, OnDestroy {
  private navService = inject(NavigationService);
  private lidarApi = inject(LidarApiService);
  private fusionApi = inject(FusionApiService);
  private nodesApi = inject(NodesApiService);
  private statusWs = inject(StatusWebSocketService);
  private configApi = inject(ConfigApiService);
  protected nodeStore = inject(NodeStoreService);
  private recordingStore = inject(RecordingStoreService);
  private dialogService = inject(DialogService);
  private toast = inject(ToastService);
  protected systemStatus = inject(SystemStatusService);

  protected lidars = this.nodeStore.sensorNodes;
  protected pipelines = this.nodeStore.availablePipelines;
  protected isLoading = this.nodeStore.isLoading;
  protected fusions = this.nodeStore.fusionNodes;
  protected operations = this.nodeStore.operationNodes;

  // Node status (from WebSocket)
  protected nodesStatus = this.statusWs.status;
  protected statusConnected = this.statusWs.connected;
  protected isSystemRunning = this.systemStatus.isRunning;

  // Loading state for individual nodes
  protected lidarLoadingStates = signal<Record<string, boolean>>({});
  protected fusionLoadingStates = signal<Record<string, boolean>>({});
  protected operationLoadingStates = signal<Record<string, boolean>>({});

  // Import/Export state
  protected isExporting = signal(false);
  protected isImporting = signal(false);
  protected showValidationDialog = signal(false);
  protected validationResult = signal<ConfigValidationResponse | null>(null);
  protected pendingImportConfig = signal<ConfigExport | null>(null);
  protected importMergeMode = signal(false);

  // Form State
  protected editMode = this.nodeStore.editMode;
  protected selectedNode = this.nodeStore.selectedNode;

  protected lidarNameById(id?: string): string {
    if (!id) return '';
    const lidar = this.lidars().find((l: any) => l.id === id);
    return lidar?.name || id;
  }

  protected fusionSensorsLabel(sensorIds?: string[]): string {
    if (!sensorIds || sensorIds.length === 0) return 'All';
    return sensorIds.map((id) => this.lidarNameById(id)).join(', ');
  }

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

  protected getNodeStatus(lidarId: string) {
    const status = this.nodesStatus();
    if (!status) return null;
    return status.nodes.find((l: any) => l.id === lidarId);
  }

  protected getFusionStatus(fusionId: string) {
    const status = this.nodesStatus();
    if (!status) return null;
    return status.nodes.find((f: any) => f.id === fusionId);
  }

  protected getOperationStatus(opId: string) {
    const status = this.nodesStatus();
    if (!status) return null;
    return status.nodes.find((o: any) => o.id === opId);
  }

  protected isLidarLoading(lidarId: string): boolean {
    return this.lidarLoadingStates()[lidarId] || false;
  }

  protected isFusionLoading(fusionId: string): boolean {
    return this.fusionLoadingStates()[fusionId] || false;
  }

  protected isOperationLoading(opId: string): boolean {
    return this.operationLoadingStates()[opId] || false;
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

  onAddLidar() {
    this.nodeStore.set('selectedNode', { type: 'sensor' });
    this.nodeStore.set('editMode', false);
    this.dialogService.open(DynamicNodeEditorComponent, {
      label: 'Add Sensor',
    });
  }

  onEditLidar(lidar: NodeConfig) {
    this.nodeStore.set('selectedNode', lidar);
    this.nodeStore.set('editMode', true);
    this.dialogService.open(DynamicNodeEditorComponent, {
      label: 'Edit Sensor',
    });
  }

  async onDeleteLidar(id?: string) {
    if (!id) return;
    const name = this.lidarNameById(id);
    if (!confirm(`Are you sure you want to delete ${name}?`)) return;
    try {
      await this.nodesApi.deleteNode(id);
      await this.onReloadConfig();
      this.toast.success(`${name} deleted.`);
    } catch (error) {
      console.error('Failed to delete lidar', error);
      this.toast.danger(`Failed to delete ${name}.`);
    }
  }

  protected async onToggleLidarEnabled(lidar: NodeConfig, enabled: boolean) {
    if (!lidar?.id) return;
    const next = enabled;

    // Set loading state for this specific lidar
    this.lidarLoadingStates.update((states) => ({ ...states, [lidar.id!]: true }));

    try {
      await this.nodesApi.setNodeEnabled(lidar.id, next);
      await this.loadConfig();
      this.toast.success(`${lidar.name} ${next ? 'enabled' : 'disabled'}.`);
    } catch (error) {
      console.error('Failed to toggle lidar', error);
      this.toast.danger(`Failed to update ${lidar.name}.`);
    } finally {
      // Clear loading state
      this.lidarLoadingStates.update((states) => {
        const newStates = { ...states };
        delete newStates[lidar.id!];
        return newStates;
      });
    }
  }

  onAddFusion() {
    this.nodeStore.set('selectedNode', { type: 'fusion' });
    this.nodeStore.set('editMode', false);
    this.dialogService.open(DynamicNodeEditorComponent, {
      label: 'Add Fusion',
    });
  }

  onEditFusion(fusion: NodeConfig) {
    this.nodeStore.set('selectedNode', fusion);
    this.nodeStore.set('editMode', true);
    this.dialogService.open(DynamicNodeEditorComponent, {
      label: 'Edit Fusion',
    });
  }

  async onDeleteFusion(id?: string) {
    if (!id) return;
    const node = this.fusions().find((f: any) => f.id === id);
    const label = node?.name || id;
    if (!confirm(`Are you sure you want to delete fusion ${label}?`)) return;
    try {
      await this.nodesApi.deleteNode(id);
      await this.onReloadConfig();
      this.toast.success(`Fusion ${label} deleted.`);
    } catch (error) {
      console.error('Failed to delete fusion', error);
      this.toast.danger(`Failed to delete fusion ${label}.`);
    }
  }

  protected async onToggleFusionEnabled(fusion: NodeConfig, enabled: boolean) {
    if (!fusion?.id) return;
    const next = enabled;

    // Set loading state for this specific fusion
    this.fusionLoadingStates.update((states) => ({ ...states, [fusion.id!]: true }));

    try {
      await this.nodesApi.setNodeEnabled(fusion.id, next);
      await this.loadConfig();
      this.toast.success(`${fusion.name} ${next ? 'enabled' : 'disabled'}.`);
    } catch (error) {
      console.error('Failed to toggle fusion', error);
      this.toast.danger(`Failed to update ${fusion.name}.`);
    } finally {
      // Clear loading state
      this.fusionLoadingStates.update((states) => {
        const newStates = { ...states };
        delete newStates[fusion.id!];
        return newStates;
      });
    }
  }

  onAddOperation() {
    this.nodeStore.set('selectedNode', { type: 'crop', category: 'operation' });
    this.nodeStore.set('editMode', false);
    this.dialogService.open(DynamicNodeEditorComponent, {
      label: 'Add Operation',
    });
  }

  onEditOperation(node: NodeConfig) {
    this.nodeStore.set('selectedNode', node);
    this.nodeStore.set('editMode', true);
    this.dialogService.open(DynamicNodeEditorComponent, {
      label: 'Edit Operation',
    });
  }

  async onDeleteOperation(id?: string) {
    if (!id) return;
    const node = this.operations().find((o: any) => o.id === id);
    const label = node?.name || id;
    if (!confirm(`Are you sure you want to delete operation ${label}?`)) return;
    try {
      await this.nodesApi.deleteNode(id);
      await this.onReloadConfig();
      this.toast.success(`Operation ${label} deleted.`);
    } catch (error) {
      console.error('Failed to delete operation', error);
      this.toast.danger(`Failed to delete operation ${label}.`);
    }
  }

  protected async onToggleOperationEnabled(node: NodeConfig, enabled: boolean) {
    if (!node?.id) return;
    const next = enabled;

    // Set loading state
    this.operationLoadingStates.update((states) => ({ ...states, [node.id!]: true }));

    try {
      await this.nodesApi.setNodeEnabled(node.id, next);
      await this.loadConfig();
      this.toast.success(`${node.name} ${next ? 'enabled' : 'disabled'}.`);
    } catch (error) {
      console.error('Failed to toggle operation', error);
      this.toast.danger(`Failed to update ${node.name}.`);
    } finally {
      this.operationLoadingStates.update((states) => {
        const newStates = { ...states };
        delete newStates[node.id!];
        return newStates;
      });
    }
  }

  async onReloadConfig() {
    try {
      await this.nodesApi.reloadConfig();
      await this.loadConfig();
      this.toast.success('Configuration reloaded.');
    } catch (error) {
      console.error('Failed to reload config', error);
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
      const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
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
    input.onchange = (event: any) => {
      const file = event.target.files?.[0];
      if (file) {
        this.readAndValidateConfigFile(file);
      }
    };
    input.click();
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
}
