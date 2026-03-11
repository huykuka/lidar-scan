import {Component, computed, CUSTOM_ELEMENTS_SCHEMA, inject, input} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CanvasNode} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {NodeStatus} from '@core/models/node.model';
import {NodeCardComponent} from '@core/models/node-plugin.model';
import {LidarProfilesApiService} from '@core/services/api';

@Component({
  selector: 'app-sensor-node-card',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [SynergyComponentsModule],
  templateUrl: './sensor-node-card.component.html',
  styleUrl: './sensor-node-card.component.css',
})
export class SensorNodeCardComponent implements NodeCardComponent {
  lidarProfileService = inject(LidarProfilesApiService)

  node = input.required<CanvasNode>();
  status = input<NodeStatus | null>(null);

  protected mode = computed(() => this.node().data.config['mode']);

  protected lidarType = computed(() => this.node().data.config['lidar_type']);
  
  protected lidarProfile = computed(() => {
    const typeId = this.lidarType();
    if (!typeId) return null;
    return this.lidarProfileService.getProfileByModelId(typeId as string);
  });

  protected lidarDisplayName = computed(() => {
    const st = this.status();
    if (st?.lidar_display_name) return st.lidar_display_name;
    
    const profile = this.lidarProfile();
    return profile?.display_name || this.lidarType() || 'Unknown';
  });

  protected sensorImage = computed(() => {
    const profile = this.lidarProfile();
    if (!profile?.thumbnail_url) return '/lidar-placeholder.svg';
    return profile.thumbnail_url;
  });

  // Network settings
  protected hostname = computed(() => this.node().data.config['hostname']);
  protected port = computed(() => this.node().data.config['port']);
  protected udpReceiverIp = computed(() => this.node().data.config['udp_receiver_ip']);
  protected imuUdpPort = computed(() => this.node().data.config['imu_udp_port']);

  protected pcdPath = computed(() => {
    const path = this.node().data.config['pcd_path'];
    if (!path) return null;
    return String(path).split('/').pop() || path;
  });

  protected throttleMs = computed(() => this.node().data.config['throttle_ms']);

  protected pose = computed(() => {
    const config = this.node().data.config;
    const x = config['x'] ?? 0;
    const y = config['y'] ?? 0;
    const z = config['z'] ?? 0;

    return [
      typeof x === 'number' ? x.toFixed(2) : x,
      typeof y === 'number' ? y.toFixed(2) : y,
      typeof z === 'number' ? z.toFixed(2) : z,
    ];
  });

  protected rotation = computed(() => {
    const config = this.node().data.config;
    const roll = config['roll'] ?? 0;
    const pitch = config['pitch'] ?? 0;
    const yaw = config['yaw'] ?? 0;

    return [
      typeof roll === 'number' ? roll.toFixed(1) : roll,
      typeof pitch === 'number' ? pitch.toFixed(1) : pitch,
      typeof yaw === 'number' ? yaw.toFixed(1) : yaw,
    ];
  });

  protected modeBadgeVariant(): 'primary' | 'neutral' {
    return this.mode() === 'real' ? 'primary' : 'neutral';
  }
}
