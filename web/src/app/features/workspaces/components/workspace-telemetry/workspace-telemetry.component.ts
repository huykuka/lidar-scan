import { Component, inject, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WorkspaceStoreService } from '../../../../core/services/stores/workspace-store.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-workspace-telemetry',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  template: `
    <div
      *ngIf="showHud()"
      class="absolute top-6 right-6 pointer-events-none animate-in fade-in slide-in-from-left-4 duration-300"
    >
      <div
        class="bg-black/20 backdrop-blur-md p-4 rounded-xl border border-white/10 shadow-lg ring-1 ring-white/5"
      >
        <div class="flex flex-col gap-4 min-w-[200px]">
          <div class="flex flex-col">
            <span class="text-[10px] font-black uppercase tracking-widest text-white/50"
              >Total Points</span
            >
            <span class="text-xl font-mono font-black text-white leading-none mt-1">
              {{ pointCount() | number }}
            </span>
          </div>
          <div class="h-px bg-white/10 w-full"></div>
          <div class="flex flex-col">
            <span class="text-[10px] font-black uppercase tracking-widest text-white/50"
              >Data Framing</span
            >
            <span class="text-xl font-mono font-black text-white leading-none mt-1">
              {{ fps() }} <span class="text-xs">Hz</span>
            </span>
          </div>
          <div class="h-px bg-white/10 w-full"></div>
          <div class="flex flex-col">
            <span class="text-[10px] font-black uppercase tracking-widest text-white/50"
              >Lidar Time</span
            >
            <span class="text-lg font-mono font-black text-white leading-none mt-1">
              {{ lidarTime() }}
            </span>
          </div>
          <div class="h-px bg-white/10 w-full"></div>
          <div class="flex flex-col">
            <span class="text-[10px] font-black uppercase tracking-widest text-white/50"
              >Active Topics ({{ enabledTopicsCount() }})</span
            >
            <div class="flex flex-col gap-1.5 mt-1.5" *ngIf="enabledTopics().length > 0">
              <div *ngFor="let topic of enabledTopics()" class="flex items-center gap-2">
                <div
                  class="w-3 h-3 rounded-full shrink-0 ring-2 ring-white/30"
                  [style.background-color]="topic.color"
                ></div>
                <span class="text-[11px] font-mono font-bold text-white truncate">
                  {{ topic.topic }}
                </span>
              </div>
            </div>
            <span
              *ngIf="enabledTopics().length === 0"
              class="text-[11px] font-mono text-white/50 mt-1"
            >
              No topics selected
            </span>
          </div>
        </div>
      </div>
    </div>
  `,
  styleUrl: './workspace-telemetry.component.css',
})
export class WorkspaceTelemetryComponent {
  private store = inject(WorkspaceStoreService);

  protected showHud = this.store.showHud;
  protected pointCount = this.store.pointCount;
  protected fps = this.store.fps;
  protected lidarTime = this.store.lidarTime;

  // Computed to get only enabled topics
  protected enabledTopics = computed(() => this.store.selectedTopics().filter((t) => t.enabled));

  protected enabledTopicsCount = computed(() => this.enabledTopics().length);
}
