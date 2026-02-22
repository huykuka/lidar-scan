import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NavigationService } from '../../core/services/navigation.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarApiService } from '../../core/services/api/lidar-api.service';
import { LidarConfig } from '../../core/models/lidar.model';
import { LidarEditorComponent } from './components/lidar-editor/lidar-editor';
import { LidarStoreService } from '../../core/services/stores/lidar-store.service';
import { DialogService } from '../../core/services';

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
  private lidarStore = inject(LidarStoreService);
  private dialogService = inject(DialogService);

  protected lidars = this.lidarStore.lidars;
  protected pipelines = this.lidarStore.availablePipelines;
  protected isLoading = this.lidarStore.isLoading;

  // Form State
  protected editMode = this.lidarStore.editMode;
  protected selectedLidar = this.lidarStore.selectedLidar;

  async ngOnInit() {
    this.navService.setHeadline('Settings');
    await this.loadConfig();
  }

  async loadConfig() {
    this.lidarStore.set('isLoading', true);
    try {
      await this.lidarApi.getLidars();
    } catch (error) {
      console.error('Failed to load lidars', error);
    } finally {
      this.lidarStore.set('isLoading', false);
    }
  }

  onAddLidar() {
    this.lidarStore.set('selectedLidar', {});
    this.lidarStore.set('editMode', false);
    this.dialogService.open(LidarEditorComponent, {
      label: 'Add Lidar',
      noHeader: true,
    });
  }

  onEditLidar(lidar: LidarConfig) {
    this.lidarStore.set('selectedLidar', lidar);
    this.lidarStore.set('editMode', true);
    this.dialogService.open(LidarEditorComponent, {
      label: 'Edit Lidar',

      noHeader: true,
    });
  }

  async onDeleteLidar(id: string) {
    if (!confirm(`Are you sure you want to delete ${id}?`)) return;
    try {
      await this.lidarApi.deleteLidar(id);
      await this.onReloadConfig();
    } catch (error) {
      console.error('Failed to delete lidar', error);
    }
  }

  async onReloadConfig() {
    try {
      await this.lidarApi.reloadConfig();
    } catch (error) {
      console.error('Failed to reload config', error);
    }
  }
}
