import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WorkspaceStoreService } from '../../../../core/services/stores/workspace-store.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { TopicApiService } from '../../../../core/services/api/topic-api.service';

@Component({
  selector: 'app-workspace-controls',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  template: `
    <div class="w-full lg:w-[360px] flex flex-col gap-4 shrink-0 h-full">
      <!-- Active Source Card -->
      <div class="bg-white p-6 rounded-2xl shadow-sm border border-syn-color-neutral-200">
        <div class="flex items-center gap-2 mb-4">
          <syn-icon name="sensors" class="text-syn-color-primary-600"></syn-icon>
          <h3 class="text-sm font-black uppercase tracking-wider text-syn-typography-color-text">
            Live Source
          </h3>
        </div>

        <div class="flex flex-col gap-4">
          <syn-select
            [value]="currentTopic()"
            (synChangeEvent)="onTopicChange($event)"
            placeholder="Select topic..."
            label="LiDAR Topic"
            class="w-full"
          >
            <syn-option *ngFor="let topic of topics()" [value]="topic">
              {{ topic }}
            </syn-option>
          </syn-select>

          <syn-button
            variant="outline"
            class="w-full"
            [disabled]="!currentTopic()"
            (click)="onCapturePcd()"
          >
            <syn-icon slot="prefix" name="download"></syn-icon>
            Capture PCD
          </syn-button>

          <div
            class="flex items-center gap-3 bg-syn-color-neutral-50 p-3 rounded-xl border border-syn-color-neutral-200"
          >
            <div class="relative flex h-3 w-3">
              <span
                class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                [ngClass]="isConnected() ? 'bg-green-400' : 'bg-red-400'"
              ></span>
              <span
                class="relative inline-flex rounded-full h-3 w-3"
                [ngClass]="isConnected() ? 'bg-green-500' : 'bg-red-500'"
              ></span>
            </div>
            <p
              class="text-[11px] font-black uppercase tracking-widest"
              [ngClass]="isConnected() ? 'text-green-600' : 'text-red-500'"
            >
              {{ isConnected() ? 'Stream Active' : 'Waiting for data' }}
            </p>
          </div>
        </div>
      </div>

      <!-- Visualization Settings Card -->
      <div class="bg-white p-6 rounded-2xl shadow-sm border border-syn-color-neutral-200 h-fit">
        <div class="flex items-center gap-2 mb-6">
          <syn-icon name="blur_on" class="text-syn-color-primary-600"></syn-icon>
          <h3 class="text-sm font-black uppercase tracking-wider text-syn-typography-color-text">
            Appearance
          </h3>
        </div>

        <div class="flex flex-col gap-8">
          <!-- Point Size -->
          <div class="flex flex-col gap-3">
            <div class="flex justify-between items-center">
              <label class="text-xs font-bold text-syn-color-neutral-600 uppercase tracking-tighter"
                >Point Size</label
              >
              <syn-badge pill variant="neutral">{{ pointSize() | number: '1.2-2' }}</syn-badge>
            </div>
            <syn-range
              [min]="0.01"
              [max]="1"
              [step]="0.01"
              [value]="pointSize().toString()"
              (synInputEvent)="onPointSizeChange($event)"
            ></syn-range>
          </div>

          <!-- Point Color -->
          <div class="flex flex-col gap-3">
            <label class="text-xs font-bold text-syn-color-neutral-600 uppercase tracking-tighter"
              >Point Color</label
            >
            <div
              class="flex items-center gap-4 bg-syn-color-neutral-50 p-3 rounded-xl border border-syn-color-neutral-200"
            >
              <input
                type="color"
                [value]="pointColor()"
                (input)="onPointColorChange($event)"
                class="w-12 h-12 rounded-lg cursor-pointer border-2 border-white shadow-sm ring-1 ring-syn-color-neutral-200"
              />
              <div class="flex flex-col">
                <span
                  class="text-sm font-mono font-black uppercase text-syn-typography-color-text"
                  >{{ pointColor() }}</span
                >
                <span class="text-[10px] text-syn-color-neutral-500 font-medium"
                  >Click to select</span
                >
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
})
export class WorkspaceControlsComponent {
  private store = inject(WorkspaceStoreService);
  private topicApi = inject(TopicApiService);

  protected topics = this.store.topics;
  protected currentTopic = this.store.currentTopic;
  protected isConnected = this.store.isConnected;
  protected pointSize = this.store.pointSize;
  protected pointColor = this.store.pointColor;

  protected onTopicChange(event: any) {
    this.store.set('currentTopic', event.target.value);
  }

  protected onCapturePcd() {
    const topic = this.currentTopic();
    if (topic) {
      this.topicApi.downloadPcd(topic);
    }
  }

  protected onPointSizeChange(event: any) {
    this.store.set('pointSize', parseFloat(event.target.value));
  }

  protected onPointColorChange(event: any) {
    this.store.set('pointColor', event.target.value);
  }
}
