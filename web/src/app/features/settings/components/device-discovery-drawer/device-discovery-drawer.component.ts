import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {AuthService} from '@core/services/auth.service';
import {ToastService} from '@core/services/toast.service';
import {LidarProfilesApiService} from '@core/services/api/lidar-profiles-api.service';
import {environment} from '@env/environment';
import {DeviceDiscoveryService} from '@core/services/device-discovery.service';
import {DiscoveredDevice} from '@core/models/device-discovery.model';
import {NodeConfig} from '@core/models/node.model';
import {CanvasEditStoreService} from '@features/settings/services/canvas-edit-store.service';

const NODE_WIDTH_OFFSET = 300;
let newSeq = 0;

interface DeviceRow {
  device: DiscoveredDevice;
  model: string | null;
  added: boolean;
  ipOnlyMatch: boolean;
}

@Component({
  selector: 'app-device-discovery-drawer',
  templateUrl: './device-discovery-drawer.component.html',
  styleUrl: './device-discovery-drawer.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, SynergyComponentsModule],
})
export class DeviceDiscoveryDrawerComponent {
  readonly open = input(false);
  readonly closed = output<void>();

  protected readonly discovery = inject(DeviceDiscoveryService);
  protected readonly canvasEditStore = inject(CanvasEditStoreService);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);
  private readonly profiles = inject(LidarProfilesApiService);

  protected readonly canEdit = this.auth.canEdit;
  protected readonly cidrText = signal('');
  protected readonly skeletonRows = [0, 1, 2, 3];

  protected readonly job = this.discovery.job;
  protected readonly isRunning = this.discovery.isRunning;
  protected readonly scanBusy = computed(() => this.isRunning() || this.discovery.starting());

  protected readonly percent = computed(() => {
    const j = this.job();
    if (!j || j.total <= 0) return 0;
    return Math.min(100, Math.round((j.scanned / j.total) * 100));
  });

  protected readonly showSkeleton = computed(
    () =>
      this.discovery.loading() ||
      (this.isRunning() && (this.job()?.devices.length ?? 0) === 0),
  );

  protected readonly showEmpty = computed(() => {
    const j = this.job();
    return j?.status === 'completed' && j.devices.length === 0 && !this.discovery.loading();
  });

  protected readonly rows = computed<DeviceRow[]>(() => {
    const devices = this.job()?.devices ?? [];
    const nodes = this.canvasEditStore.localNodes();
    return devices.map((device) => {
      const profile = device.lidar_type ? this.profiles.getProfileByModelId(device.lidar_type) : null;
      const model = profile?.display_name ?? device.device_name ?? device.lidar_type;
      const dType = device.lidar_type?.trim().toLowerCase() || null;
      let added = false;
      let ipOnlyMatch = false;
      for (const n of nodes) {
        if (n.type !== 'sensor') continue;
        const host = String(n.config?.['hostname'] ?? '').trim();
        if (host !== device.ip) continue;
        const nType = String(n.config?.['lidar_type'] ?? '').trim().toLowerCase() || null;
        if (dType === null || nType === null) {
          added = true;
          ipOnlyMatch = true;
          break;
        }
        if (dType === nType) {
          added = true;
          ipOnlyMatch = false;
          break;
        }
      }
      return {device, model, added, ipOnlyMatch};
    });
  });

  constructor() {
    effect(() => {
      const isOpen = this.open();
      untracked(() => {
        if (isOpen) {
          this.discovery.connect();
          void this.discovery.getScan();
        } else {
          this.discovery.disconnect();
        }
      });
    });
  }

  protected onRequestClose(): void {
    this.closed.emit();
  }

  protected onCidrInput(event: Event): void {
    this.cidrText.set((event.target as HTMLInputElement).value ?? '');
  }

  protected async onScan(): Promise<void> {
    const cidrs = this.cidrText()
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean);
    await this.discovery.startScan(cidrs.length ? cidrs : undefined);
  }

  protected onRetry(): void {
    this.discovery.clearError();
    void this.onScan();
  }

  protected formatTime(iso: string | null | undefined): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d.getTime()) ? '—' : d.toLocaleTimeString();
  }

  /** Stage node locally (unsaved change, like a palette drop). No PUT, no reload. */
  protected onAdd(device: DiscoveredDevice): void {
    if (!this.canEdit()) return;
    const nodes = this.canvasEditStore.localNodes();
    const rightmost = nodes.reduce<NodeConfig | null>(
      (best, n) => (best === null || n.x > best.x ? n : best),
      null,
    );
    const octet = device.ip.split('.').pop() ?? device.ip;
    const base = device.lidar_type ?? 'sensor';
    const config: Record<string, unknown> = {hostname: device.ip};
    if (device.lidar_type) config['lidar_type'] = device.lidar_type;
    this.canvasEditStore.pushUndoState();
    this.canvasEditStore.addNode({
      id: `__new__${Date.now()}_${++newSeq}`,
      name: `${base}_${octet}`,
      type: 'sensor',
      category: 'sensor',
      enabled: true,
      visible: true,
      config,
      x: rightmost ? rightmost.x + NODE_WIDTH_OFFSET : 0,
      y: rightmost ? rightmost.y : 0,
    });
    this.toast.primary(`Sensor ${base}_${octet} added. Save to apply.`);
  }

  protected thumbnail(lidarType: string | null): string {
    const url = lidarType
      ? this.profiles.getProfileByModelId(lidarType)?.thumbnail_url
      : undefined;
    return url ?? `${environment.apiUrl.replace('/api/v1', '')}/api/v1/assets/lidar/placeholder.png`;
  }
}
