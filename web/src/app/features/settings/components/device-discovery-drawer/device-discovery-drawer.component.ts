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
import {NodeStoreService} from '@core/services/stores/node-store.service';
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
  private readonly nodeStore = inject(NodeStoreService);
  private readonly profiles = inject(LidarProfilesApiService);

  protected readonly canEdit = this.auth.canEdit;
  protected readonly cidrs = signal<string[]>([]);
  protected readonly cidrDraft = signal('');
  protected readonly cidrInvalid = signal<string | null>(null);
  protected readonly settingsOpen = signal(false);
  protected readonly skeletonRows = [0, 1, 2, 3];

  protected readonly job = this.discovery.job;
  protected readonly isRunning = this.discovery.isRunning;
  protected readonly scanBusy = computed(() => this.isRunning() || this.discovery.starting());

  protected readonly percent = computed(() => {
    const j = this.job();
    if (!j || j.total <= 0) return 0;
    return Math.min(100, Math.round((j.scanned / j.total) * 100));
  });

  protected readonly deviceCount = computed(() => this.job()?.devices.length ?? 0);

  protected readonly duration = computed(() => {
    const j = this.job();
    if (!j?.finished_at) return null;
    const ms = new Date(j.finished_at).getTime() - new Date(j.started_at).getTime();
    return isNaN(ms) || ms < 0 ? null : `${(ms / 1000).toFixed(1)}s`;
  });

  protected readonly statusText = computed(() => {
    const j = this.job();
    if (!j) return 'Not scanned yet';
    const n = j.devices.length;
    const devices = `${n} ${n === 1 ? 'device' : 'devices'}`;
    if (j.status === 'running') return `Scanning… ${j.scanned}/${j.total} · ${devices}`;
    if (j.status === 'failed') return 'Scan failed';
    const d = this.duration();
    return `${devices} · ${j.total} hosts${d ? ' · ' + d : ''}`;
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
      const model =
        device.variant_name ?? profile?.display_name ?? device.device_name ?? device.lidar_type;
      const dType = device.lidar_type?.trim().toLowerCase() || null;
      let added = false;
      const ipOnlyMatch = false;
      if (dType !== null) {
        for (const n of nodes) {
          if (n.type !== 'sensor') continue;
          if (String(n.config?.['hostname'] ?? '').trim() !== device.ip) continue;
          const nType = String(n.config?.['lidar_type'] ?? '').trim().toLowerCase();
          if (nType === dType) {
            added = true;
            break;
          }
        }
      }
      return {device, model, added, ipOnlyMatch};
    });
  });

  /** Rows ordered: addable → added → unsupported; numeric IP order within group. */
  protected readonly sortedRows = computed<DeviceRow[]>(() => {
    const rank = (r: DeviceRow) => (!r.device.lidar_type ? 2 : r.added ? 1 : 0);
    const ipNum = (ip: string) =>
      ip.split('.').reduce((acc, o) => acc * 256 + (parseInt(o, 10) || 0), 0);
    return [...this.rows()].sort(
      (a, b) => rank(a) - rank(b) || ipNum(a.device.ip) - ipNum(b.device.ip),
    );
  });

  constructor() {
    // Auto-expand scan settings on CIDR-related error.
    effect(() => {
      const err = this.discovery.error();
      if (err && /cidr|hosts|subnet/i.test(err)) this.settingsOpen.set(true);
    });
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

  protected async onScan(): Promise<void> {
    this.commitDraft();
    if (this.cidrInvalid()) {
      this.settingsOpen.set(true);
      return;
    }
    const list = this.cidrs();
    await this.discovery.startScan(list.length ? list : undefined);
  }

  private static readonly CIDR_RE =
    /^((25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(25[0-5]|2[0-4]\d|1?\d?\d)\/(3[0-2]|[12]?\d)$/;

  protected onCidrDraftInput(event: Event): void {
    const v = (event.target as HTMLInputElement).value ?? '';
    if (v.includes(',')) {
      this.cidrDraft.set(v);
      this.commitDraft();
      return;
    }
    this.cidrDraft.set(v);
    this.cidrInvalid.set(null);
  }

  protected onCidrKey(event: KeyboardEvent): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      this.commitDraft();
    }
  }

  /** Commit comma-separated draft as chips; sets inline error if any entry is invalid. */
  protected commitDraft(): void {
    const parts = this.cidrDraft()
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean);
    if (!parts.length) return;
    const bad = parts.find((c) => !DeviceDiscoveryDrawerComponent.CIDR_RE.test(c));
    if (bad) {
      this.cidrInvalid.set(`"${bad}" is not a valid IPv4 CIDR (e.g. 192.168.1.0/24)`);
      return;
    }
    this.cidrs.update((cur) => [...cur, ...parts.filter((c) => !cur.includes(c))]);
    this.cidrDraft.set('');
    this.cidrInvalid.set(null);
  }

  protected removeCidr(c: string): void {
    this.cidrs.update((cur) => cur.filter((x) => x !== c));
  }

  protected onRetry(): void {
    this.discovery.clearError();
    void this.onScan();
  }

  protected openDevicePage(ip: string): void {
    window.open(`http://${ip}`, '_blank', 'noopener');
  }

  protected async copyIp(ip: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(ip);
      this.toast.primary(`Copied ${ip}`);
    } catch {
      this.toast.warning('Copy failed');
    }
  }

  protected formatTime(iso: string | null | undefined): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d.getTime()) ? '—' : d.toLocaleTimeString();
  }

  /** Stage node locally (unsaved change, like a palette drop). No PUT, no reload. */
  protected onAdd(device: DiscoveredDevice): void {
    if (!this.canEdit() || !device.lidar_type) return;
    const nodes = this.canvasEditStore.localNodes();
    const rightmost = nodes.reduce<NodeConfig | null>(
      (best, n) => (best === null || n.x > best.x ? n : best),
      null,
    );
    const octet = device.ip.split('.').pop() ?? device.ip;
    const base = device.lidar_type ?? 'sensor';
    // Merge NodeDefinition defaults (e.g. required udp_receiver_ip) so the node validates & saves.
    const def = this.nodeStore.nodeDefinitions().find((d) => d.type === 'sensor');
    const config: Record<string, unknown> = {};
    for (const prop of def?.properties ?? []) {
      if (prop.default !== undefined && prop.default !== null && prop.type !== 'pose') {
        config[prop.name] = structuredClone(prop.default);
      }
    }
    config['hostname'] = device.ip;
    if (device.lidar_type) {
      config['lidar_type'] = device.lidar_type;
      const profile = this.profiles.getProfileByModelId(device.lidar_type);
      if (profile?.default_port) config['port'] = profile.default_port;
    }
    // Unique name: suffix on collision.
    const names = new Set(nodes.map((n) => n.name));
    let name = `${base}_${octet}`;
    for (let i = 2; names.has(name); i++) name = `${base}_${octet}_${i}`;
    this.canvasEditStore.pushUndoState();
    this.canvasEditStore.addNode({
      id: `__new__${Date.now()}_${++newSeq}`,
      name,
      type: 'sensor',
      category: 'sensor',
      enabled: true,
      visible: true,
      config,
      x: rightmost ? rightmost.x + NODE_WIDTH_OFFSET : 0,
      y: rightmost ? rightmost.y : 0,
    });
    this.toast.primary(`Sensor ${name} added. Save to apply.`);
  }

  protected thumbnail(lidarType: string | null): string {
    const url = lidarType
      ? this.profiles.getProfileByModelId(lidarType)?.thumbnail_url
      : undefined;
    return url ?? `${environment.apiUrl.replace('/api/v1', '')}/api/v1/assets/lidar/placeholder.png`;
  }
}
