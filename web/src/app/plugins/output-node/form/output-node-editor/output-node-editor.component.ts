import {Component, computed, inject, OnInit, output, signal} from '@angular/core';
import {Router} from '@angular/router';
import {FormControl, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {NodeEditorComponent} from '@core/models/node-plugin.model';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {ToastService} from '@core/services/toast.service';
import {NodeEditorHeaderComponent} from '@plugins/shared/node-editor-header/node-editor-header.component';
import {NodeEditorFacadeService} from '@features/settings/services/node-editor-facade.service';
import {WebhookConfigComponent} from '@features/output-node/components/webhook-config/webhook-config.component';
import {OutputNodeApiService} from '@features/output-node/services/output-node-api.service';
import {WebhookConfig, DEFAULT_WEBHOOK_CONFIG} from '@core/models/output-node.model';

/**
 * Drawer editor for Output Node configuration.
 * Shows node name, "View Live Data" link, and the WebhookConfigComponent.
 */
@Component({
  selector: 'app-output-node-editor',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    SynergyComponentsModule,
    SynergyFormsModule,
    NodeEditorHeaderComponent,
    WebhookConfigComponent,
  ],
  providers: [NodeEditorFacadeService, OutputNodeApiService],
  templateUrl: './output-node-editor.component.html',
  styleUrl: './output-node-editor.component.css',
})
export class OutputNodeEditorComponent implements OnInit, NodeEditorComponent {
  saved = output<void>();
  cancelled = output<void>();

  private nodeStore = inject(NodeStoreService);
  private toast = inject(ToastService);
  private facade = inject(NodeEditorFacadeService);
  private router = inject(Router);
  private outputNodeApi = inject(OutputNodeApiService);

  protected isSaving = signal(false);
  protected webhookConfig = signal<WebhookConfig>({...DEFAULT_WEBHOOK_CONFIG});
  protected webhookLoaded = signal(false);

  protected nodeId = computed(() => this.nodeStore.selectedNode()?.id ?? null);

  protected isEditMode = computed(() => !!this.nodeStore.selectedNode()?.id);

  protected definition = computed(() =>
    this.nodeStore.nodeDefinitions().find((d) => d.type === 'output_node'),
  );

  form!: FormGroup;

  constructor() {
    const node = this.nodeStore.selectedNode();
    this.form = new FormGroup({
      name: new FormControl(node?.name || 'Output', [Validators.required]),
    });
  }

  async ngOnInit(): Promise<void> {
    const id = this.nodeId();
    if (!id) {
      this.webhookLoaded.set(true);
      return;
    }
    try {
      const cfg = await this.outputNodeApi.getWebhookConfig(id);
      this.webhookConfig.set(cfg);
    } catch {
      // Silently ignore — show defaults
    } finally {
      this.webhookLoaded.set(true);
    }
  }

  protected navigateToLiveData(): void {
    const id = this.nodeId();
    if (id) {
      this.router.navigate(['/output', id]);
    }
  }

  protected onWebhookSaved(config: WebhookConfig): void {
    this.webhookConfig.set(config);
  }

  async onSave(): Promise<void> {
    if (!this.form.valid) {
      this.toast.warning('Please enter a node name');
      return;
    }
    const def = this.definition();
    if (!def) {
      this.toast.danger('Node definition not found');
      return;
    }
    this.isSaving.set(true);
    const success = await this.facade.saveNode({
      name: this.form.value.name,
      config: {},
      definition: def,
      existingNode: this.nodeStore.selectedNode() ?? {},
    });
    this.isSaving.set(false);
    if (success) {
      this.saved.emit();
    }
  }

  onCancel(): void {
    this.cancelled.emit();
  }
}
