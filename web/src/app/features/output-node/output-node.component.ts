import {Component, inject, OnDestroy, OnInit, signal} from '@angular/core';
import {ActivatedRoute, Router} from '@angular/router';
import {Subscription} from 'rxjs';
import {filter, map} from 'rxjs/operators';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {MultiWebsocketService} from '@core/services/multi-websocket.service';
import {OutputNodeApiService} from '@features/output-node/services/output-node-api.service';
import {MetadataTableComponent} from '@features/output-node/components/metadata-table/metadata-table.component';
import {WebhookConfigComponent} from '@features/output-node/components/webhook-config/webhook-config.component';
import {WebhookConfig, DEFAULT_WEBHOOK_CONFIG} from '@core/models/output-node.model';
import {environment} from '@env/environment';

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

/**
 * Smart container page for a single Output Node.
 * Route: /output/:nodeId
 *
 * Subscribes to the system_status WebSocket topic and filters
 * for messages with type === 'output_node_metadata' and the matching node_id.
 */
@Component({
  selector: 'app-output-node',
  standalone: true,
  imports: [SynergyComponentsModule, MetadataTableComponent, WebhookConfigComponent],
  templateUrl: './output-node.component.html',
})
export class OutputNodeComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private wsService = inject(MultiWebsocketService);
  private outputNodeApi = inject(OutputNodeApiService);

  protected metadata = signal<Record<string, any> | null>(null);
  protected connectionStatus = signal<ConnectionStatus>('connecting');
  protected nodeNotFound = signal(false);
  protected nodeName = signal('');
  protected webhookConfig = signal<WebhookConfig>({...DEFAULT_WEBHOOK_CONFIG});
  protected webhookLoaded = signal(false);

  protected nodeId = '';
  protected wsSub?: Subscription;

  async ngOnInit(): Promise<void> {
    this.nodeId = this.route.snapshot.params['nodeId'];

    // Load node details
    try {
      const node = await this.outputNodeApi.getNode(this.nodeId);
      this.nodeName.set(node.name);
    } catch (err: any) {
      if (err?.status === 404) {
        this.nodeNotFound.set(true);
        return;
      }
      // Non-404 error: still connect WS, show node ID as fallback name
      this.nodeName.set(this.nodeId);
    }

    // Load webhook config (best-effort)
    try {
      const cfg = await this.outputNodeApi.getWebhookConfig(this.nodeId);
      this.webhookConfig.set(cfg);
    } catch {
      // silently ignore — webhook section still renders with defaults
    } finally {
      this.webhookLoaded.set(true);
    }

    // Connect to system_status WebSocket
    this.wsSub = this.wsService
      .connect('system_status', environment.wsUrl('system_status'))
      .pipe(
        map(raw => {
          try {
            return typeof raw === 'string' ? JSON.parse(raw) : raw;
          } catch {
            return null;
          }
        }),
        filter(
          msg =>
            msg !== null &&
            msg.type === 'output_node_metadata' &&
            msg.node_id === this.nodeId,
        ),
      )
      .subscribe({
        next: msg => {
          this.connectionStatus.set('connected');
          this.metadata.set(msg.metadata);
        },
        error: () => this.connectionStatus.set('disconnected'),
        complete: () => this.connectionStatus.set('disconnected'),
      });
  }

  ngOnDestroy(): void {
    // Unsubscribe only — do NOT disconnect the shared system_status topic
    this.wsSub?.unsubscribe();
  }

  protected onWebhookSaved(config: WebhookConfig): void {
    this.webhookConfig.set(config);
  }

  protected goBack(): void {
    this.router.navigate(['/settings']);
  }
}
