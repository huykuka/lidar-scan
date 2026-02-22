import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NavigationService } from '../../core/services/navigation.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarApiService } from '../../core/services/api/lidar-api.service';
import { FusionApiService } from '../../core/services/api/fusion-api.service';
import { LidarConfig } from '../../core/models/lidar.model';
import { FusionConfig } from '../../core/services/api/fusion-api.service';
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
export class SettingsComponent implements OnInit {
  private navService = inject(NavigationService);
  private lidarApi = inject(LidarApiService);
  private fusionApi = inject(FusionApiService);
  private lidarStore = inject(LidarStoreService);
  protected fusionStore = inject(FusionStoreService);
  private dialogService = inject(DialogService);
  private toast = inject(ToastService);

  protected lidars = this.lidarStore.lidars;
  protected pipelines = this.lidarStore.availablePipelines;
  protected isLoading = this.lidarStore.isLoading;
  protected fusions = this.fusionStore.fusions;

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
