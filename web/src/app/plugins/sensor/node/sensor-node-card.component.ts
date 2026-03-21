import {Component, computed, CUSTOM_ELEMENTS_SCHEMA, inject, input} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CanvasNode} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {NodeStatusUpdate} from '@core/models/node-status.model';
import {NodeCardComponent} from '@core/models/node-plugin.model';
import {LidarProfilesApiService} from '@core/services/api';
import {ZERO_POSE} from '@core/models/pose.model';

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
  status = input<NodeStatusUpdate | null>(null);

  protected mode = computed(() => this.node().data.config['mode']);

  protected lidarType = computed(() => this.node().data.config['lidar_type']);
  
  protected lidarProfile = computed(() => {
    const typeId = this.lidarType();
    if (!typeId) return null;
    return this.lidarProfileService.getProfileByModelId(typeId as string);
  });

  protected lidarDisplayName = computed(() => {
    // Note: lidar_display_name no longer in status - would need to be in node config if needed
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
    const p = this.node().data.pose ?? ZERO_POSE;
    return [
      p.x.toFixed(2),
      p.y.toFixed(2),
      p.z.toFixed(2),
    ];
  });

  protected rotation = computed(() => {
    const p = this.node().data.pose ?? ZERO_POSE;
    return [
      p.roll.toFixed(1),
      p.pitch.toFixed(1),
      p.yaw.toFixed(1),
    ];
  });

  protected modeBadgeVariant(): 'primary' | 'neutral' {
    return this.mode() === 'real' ? 'primary' : 'neutral';
  }
}
