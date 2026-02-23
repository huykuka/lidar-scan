import { Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NavigationService } from '../../core/services/navigation.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarApiService } from '../../core/services/api/lidar-api.service';
import { FusionApiService } from '../../core/services/api/fusion-api.service';
import { NodesApiService, NodesStatusResponse } from '../../core/services/api/nodes-api.service';
import { StatusWebSocketService } from '../../core/services/status-websocket.service';
import { ConfigApiService } from '../../core/services/api/config-api.service';
import { LidarConfig } from '../../core/models/lidar.model';
import { FusionConfig } from '../../core/models/fusion.model';
import { ConfigExport, ConfigValidationResponse } from '../../core/models/config.model';
import { LidarEditorComponent } from './components/lidar-editor/lidar-editor';
import { FusionEditorComponent } from './components/fusion-editor/fusion-editor';
import { LidarCardComponent } from './components/lidar-card/lidar-card.component';
import { FusionCardComponent } from './components/fusion-card/fusion-card.component';
import { ConfigImportDialogComponent } from './components/config-import-dialog/config-import-dialog.component';
import { FlowCanvasComponent } from './components/flow-canvas/flow-canvas.component';
import { LidarStoreService } from '../../core/services/stores/lidar-store.service';
import { FusionStoreService } from '../../core/services/stores/fusion-store.service';
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
    LidarCardComponent,
    FusionCardComponent,
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
  private lidarStore = inject(LidarStoreService);
  protected fusionStore = inject(FusionStoreService);
  private dialogService = inject(DialogService);
  private toast = inject(ToastService);

  protected lidars = this.lidarStore.lidars;
  protected pipelines = this.lidarStore.availablePipelines;
  protected isLoading = this.lidarStore.isLoading;
  protected fusions = this.fusionStore.fusions;
  
  // Tab state
  protected activeTab = signal<'all' | 'sensors' | 'fusions'>('all');
  
  // View mode state
  protected viewMode = signal<'grid' | 'canvas'>('canvas');
  
  // Node status (from WebSocket)
  protected nodesStatus = this.statusWs.status;
  protected statusConnected = this.statusWs.connected;
  
  // Loading state for individual nodes
  protected lidarLoadingStates = signal<Record<string, boolean>>({});
  protected fusionLoadingStates = signal<Record<string, boolean>>({});

  // Import/Export state
  protected isExporting = signal(false);
  protected isImporting = signal(false);
  protected showValidationDialog = signal(false);
  protected validationResult = signal<ConfigValidationResponse | null>(null);
  protected pendingImportConfig = signal<ConfigExport | null>(null);
  protected importMergeMode = signal(false);

  // Form State
  protected editMode = this.lidarStore.editMode;
  protected selectedLidar = this.lidarStore.selectedLidar;

  protected lidarNameById(id?: string): string {
    if (!id) return '';
    const lidar = this.lidars().find((l) => l.id === id);
    return lidar?.name || id;
  }

  protected fusionSensorsLabel(sensorIds?: string[]): string {
    if (!sensorIds || sensorIds.length === 0) return 'All';
    return sensorIds.map((id) => this.lidarNameById(id)).join(', ');
  }

  async ngOnInit() {
    this.navService.setHeadline('Settings');
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
    return status.lidars.find(l => l.id === lidarId);
  }
  
  protected getFusionStatus(fusionId: string) {
    const status = this.nodesStatus();
    if (!status) return null;
    return status.fusions.find(f => f.id === fusionId);
  }
  
  protected isLidarLoading(lidarId: string): boolean {
    return this.lidarLoadingStates()[lidarId] || false;
  }
  
  protected isFusionLoading(fusionId: string): boolean {
    return this.fusionLoadingStates()[fusionId] || false;
  }

  async loadConfig() {
    this.lidarStore.set('isLoading', true);
    try {
      await Promise.all([this.lidarApi.getLidars(), this.fusionApi.getFusions()]);
    } catch (error) {
      console.error('Failed to load lidars', error);
      this.toast.warning('Unable to load configuration.');
    } finally {
      this.lidarStore.set('isLoading', false);
    }
  }

  onAddLidar() {
    this.lidarStore.set('selectedLidar', {});
    this.lidarStore.set('editMode', false);
    this.dialogService.open(LidarEditorComponent, {
      label: 'Add Lidar',
    });
  }

  onEditLidar(lidar: LidarConfig) {
    this.lidarStore.set('selectedLidar', lidar);
    this.lidarStore.set('editMode', true);
    this.dialogService.open(LidarEditorComponent, {
      label: 'Edit Lidar',
    });
  }

  async onDeleteLidar(id?: string) {
    if (!id) return;
    const name = this.lidarNameById(id);
    if (!confirm(`Are you sure you want to delete ${name}?`)) return;
    try {
      await this.lidarApi.deleteLidar(id);
      await this.onReloadConfig();
      this.toast.success(`${name} deleted.`);
    } catch (error) {
      console.error('Failed to delete lidar', error);
      this.toast.danger(`Failed to delete ${name}.`);
    }
  }

  protected async onToggleLidarEnabled(lidar: LidarConfig, enabled: boolean) {
    if (!lidar?.id) return;
    const next = enabled;
    
    // Set loading state for this specific lidar
    this.lidarLoadingStates.update(states => ({...states, [lidar.id!]: true}));
    
    try {
      await this.lidarApi.setEnabled(lidar.id, next);
      await this.loadConfig();
      this.toast.success(`${lidar.name} ${next ? 'enabled' : 'disabled'}.`);
    } catch (error) {
      console.error('Failed to toggle lidar', error);
      this.toast.danger(`Failed to update ${lidar.name}.`);
    } finally {
      // Clear loading state
      this.lidarLoadingStates.update(states => {
        const newStates = {...states};
        delete newStates[lidar.id!];
        return newStates;
      });
    }
  }

  onAddFusion() {
    this.fusionStore.set('selectedFusion', {});
    this.fusionStore.set('editMode', false);
    this.dialogService.open(FusionEditorComponent, {
      label: 'Add Fusion',
    });
  }

  onEditFusion(fusion: FusionConfig) {
    this.fusionStore.set('selectedFusion', fusion);
    this.fusionStore.set('editMode', true);
    this.dialogService.open(FusionEditorComponent, {
      label: 'Edit Fusion',
    });
  }

  async onDeleteFusion(id?: string) {
    if (!id) return;
    const fusion = this.fusions().find((f) => f.id === id);
    const label = fusion?.name || id;
    if (!confirm(`Are you sure you want to delete fusion ${label}?`)) return;
    try {
      await this.fusionApi.deleteFusion(id);
      await this.onReloadConfig(); // Reload backend fusions
      this.toast.success(`Fusion ${label} deleted.`);
    } catch (error) {
      console.error('Failed to delete fusion', error);
      this.toast.danger(`Failed to delete fusion ${label}.`);
    }
  }

  protected async onToggleFusionEnabled(fusion: FusionConfig, enabled: boolean) {
    if (!fusion?.id) return;
    const next = enabled;
    
    // Set loading state for this specific fusion
    this.fusionLoadingStates.update(states => ({...states, [fusion.id!]: true}));
    
    try {
      await this.fusionApi.setEnabled(fusion.id, next);
      await this.loadConfig();
      this.toast.success(`${fusion.name} ${next ? 'enabled' : 'disabled'}.`);
    } catch (error) {
      console.error('Failed to toggle fusion', error);
      this.toast.danger(`Failed to update ${fusion.name}.`);
    } finally {
      // Clear loading state
      this.fusionLoadingStates.update(states => {
        const newStates = {...states};
        delete newStates[fusion.id!];
        return newStates;
      });
    }
  }

  async onReloadConfig() {
    try {
      await this.lidarApi.reloadConfig();
      await this.loadConfig();
      this.toast.success('Configuration reloaded.');
    } catch (error) {
      console.error('Failed to reload config', error);
      this.toast.danger('Failed to reload backend configuration.');
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
        `Configuration imported: ${result.imported.lidars} lidars, ${result.imported.fusions} fusions.`
      );
    } catch (error) {
      console.error('Failed to import config', error);
      this.toast.danger('Failed to import configuration.');
    } finally {
      this.isImporting.set(false);
    }
  }
}
