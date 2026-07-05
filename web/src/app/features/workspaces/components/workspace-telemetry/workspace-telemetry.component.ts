import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { WorkspaceStoreService } from '@core/services';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-workspace-telemetry',
  imports: [DecimalPipe, SynergyComponentsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './workspace-telemetry.component.html',
  styleUrl: './workspace-telemetry.component.css',
})
export class WorkspaceTelemetryComponent {
  private store = inject(WorkspaceStoreService);

  protected pointCount = this.store.pointCount;
  protected fps = this.store.fps;
  protected lidarTime = this.store.lidarTime;
}
