import { Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NavigationService } from '../../core/services/navigation.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarApiService } from '../../core/services/api/lidar-api.service';
import { FusionApiService } from '../../core/services/api/fusion-api.service';
import { NodesApiService, NodesStatusResponse } from '../../core/services/api/nodes-api.service';
import { LidarConfig } from '../../core/models/lidar.model';
import { FusionConfig } from '../../core/models/fusion.model';
import { LidarEditorComponent } from './components/lidar-editor/lidar-editor';
import { FusionEditorComponent } from './components/fusion-editor/fusion-editor';
import { LidarStoreService } from '../../core/services/stores/lidar-store.service';
import { FusionStoreService } from '../../core/services/stores/fusion-store.service';
import { DialogService } from '../../core/services';
import { ToastService } from '../../core/services/toast.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css',
  imports: [CommonModule, FormsModule, SynergyComponentsModule],
})
export class SettingsComponent implements OnInit, OnDestroy {
  private navService = inject(NavigationService);
  private lidarApi = inject(LidarApiService);
  private fusionApi = inject(FusionApiService);
  private nodesApi = inject(NodesApiService);
  private lidarStore = inject(LidarStoreService);
  protected fusionStore = inject(FusionStoreService);
  private dialogService = inject(DialogService);
  private toast = inject(ToastService);

  protected lidars = this.lidarStore.lidars;
  protected pipelines = this.lidarStore.availablePipelines;
  protected isLoading = this.lidarStore.isLoading;
  protected fusions = this.fusionStore.fusions;
  
  // Node status
  protected nodesStatus = signal<NodesStatusResponse | null>(null);
  private statusPollInterval: any = null;
  
  // Loading state for individual nodes
  protected lidarLoadingStates = signal<Record<string, boolean>>({});
  protected fusionLoadingStates = signal<Record<string, boolean>>({});

  // Form State
  protected editMode = this.lidarStore.editMode;
  protected selectedLidar = this.lidarStore.selectedLidar;

  // Drag and drop state
  protected isDraggingOver = false;

  protected lidarNameById(id?: string): string {
    if (!id) return '';
    const lidar = this.lidars().find((l) => l.id === id);
    return lidar?.name || id;
  }

  protected fusionSensorsLabel(sensorIds?: string[]): string {
    if (!sensorIds || sensorIds.length === 0) return 'All';
    return sensorIds.map((id) => this.lidarNameById(id)).join(', ');
  }

  onDragStart(event: DragEvent, type: 'lidar' | 'fusion') {
    if (event.dataTransfer) {
      event.dataTransfer.setData('componentType', type);
      event.dataTransfer.effectAllowed = 'copy';
    }
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
    this.isDraggingOver = true;
  }

  onDragLeave(event: DragEvent) {
    event.preventDefault();
    this.isDraggingOver = false;
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.isDraggingOver = false;
    if (event.dataTransfer) {
      const type = event.dataTransfer.getData('componentType');
      if (type === 'lidar') {
        this.onAddLidar();
      } else if (type === 'fusion') {
        this.onAddFusion();
      }
    }
  }

  async ngOnInit() {
    this.navService.setHeadline('Settings');
    await this.loadConfig();
    this.startStatusPolling();
  }

  ngOnDestroy(): void {
    this.stopStatusPolling();
  }
  
  private startStatusPolling() {
    // Poll every 2 seconds
    this.statusPollInterval = setInterval(async () => {
      try {
        const status = await this.nodesApi.getNodesStatus();
        this.nodesStatus.set(status);
      } catch (error) {
        // Silently fail - don't toast on every poll failure
        console.error('Failed to fetch node status', error);
      }
    }, 2000);
    
    // Also fetch immediately
    this.nodesApi.getNodesStatus().then(status => this.nodesStatus.set(status)).catch(console.error);
  }
  
  private stopStatusPolling() {
    if (this.statusPollInterval) {
      clearInterval(this.statusPollInterval);
      this.statusPollInterval = null;
    }
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
}
