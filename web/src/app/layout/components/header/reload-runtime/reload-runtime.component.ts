import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { AuthService } from '@core/services/auth.service';
import { ToastService } from '@core/services/toast.service';
import { NodesApiService } from '@core/services/api/nodes-api.service';

/**
 * Reload runtime button for the header.
 * Triggers a backend DAG reload without saving config changes.
 */
@Component({
  selector: 'app-reload-runtime',
  imports: [SynergyComponentsModule],
  templateUrl: './reload-runtime.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
    }
  `,
})
export class ReloadRuntimeComponent {
  readonly mobile = input(false);

  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);
  private readonly nodesApi = inject(NodesApiService);

  protected readonly canEdit = this.auth.canEdit;
  protected readonly loading = signal(false);

  protected async onReload(): Promise<void> {
    if (!this.canEdit()) return;
    this.loading.set(true);
    try {
      await this.nodesApi.reloadConfig();
      this.toast.success('DAG runtime reloaded successfully.');
    } catch {
      this.toast.danger('Failed to reload runtime.');
    } finally {
      this.loading.set(false);
    }
  }
}
