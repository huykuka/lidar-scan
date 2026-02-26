import {
  Component,
  inject,
  computed,
  signal,
  effect,
  Output,
  EventEmitter,
  CUSTOM_ELEMENTS_SCHEMA,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeStoreService } from '../../../../core/services/stores/node-store.service';
import { NodesApiService } from '../../../../core/services/api/nodes-api.service';
import { DialogService } from '../../../../core/services';
import { ToastService } from '../../../../core/services/toast.service';
import { NodeConfig, Edge } from '../../../../core/models/node.model';
import { EdgesApiService } from '../../../../core/services/api/edges-api.service';

@Component({
  selector: 'app-dynamic-node-editor',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [CommonModule, ReactiveFormsModule, SynergyComponentsModule],
  templateUrl: './dynamic-node-editor.component.html',
  styleUrl: './dynamic-node-editor.component.css',
})
export class DynamicNodeEditorComponent {
  private fb = inject(FormBuilder);
  private nodeStore = inject(NodeStoreService);
  private nodesApi = inject(NodesApiService);
  private edgesApi = inject(EdgesApiService);
  private dialogService = inject(DialogService);
  private toast = inject(ToastService);

  @Output() save = new EventEmitter<any>();

  protected editMode = this.nodeStore.editMode;
  protected isSaving = signal(false);

  protected definition = computed(() => {
    const data = this.nodeStore.selectedNode();
    const type = data.type === 'operation' ? (data.config as any)?.op_type : data.type;
    const def = this.nodeStore.nodeDefinitions().find((d) => d.type === type);

    if (!def && data.type) {
      console.warn(
        `DynamicNodeEditor: No definition found for type "${type}" (data.type: ${data.type})`,
      );
      console.debug(
        'Available definitions:',
        this.nodeStore.nodeDefinitions().map((d) => d.type),
      );
    }

    return def;
  });

  protected form!: FormGroup;
  protected configForm!: FormGroup;

  constructor() {
    effect(() => {
      const def = this.definition();
      if (def) {
        this.initForm();
      }
    });
  }

  private initForm() {
    const data = this.nodeStore.selectedNode();
    const def = this.definition();

    const configGroup: any = {};
    if (def) {
      def.properties.forEach((prop) => {
        // Support both old nested operation format and new flat format
        const currentConfig = data.config?.['op_config'] ?? data.config;
        const val = currentConfig ? currentConfig[prop.name] : prop.default;

        if (prop.type === 'vec3') {
          configGroup[prop.name] = this.fb.group({
            0: [val ? val[0] : prop.default ? prop.default[0] : 0],
            1: [val ? val[1] : prop.default ? prop.default[1] : 0],
            2: [val ? val[2] : prop.default ? prop.default[2] : 0],
          });
        } else {
          configGroup[prop.name] = [
            val ?? prop.default,
            prop.required ? [Validators.required] : [],
          ];
        }
      });
    }

    this.configForm = this.fb.group(configGroup);
    this.form = this.fb.group({
      name: [data.name || def?.display_name || '', [Validators.required]],
    });
  }

  async onSave() {
    if (this.form.invalid || this.configForm.invalid) return;

    this.isSaving.set(true);
    const val = this.form.value;
    const configRaw = this.configForm.getRawValue();
    const def = this.definition();
    const data = this.nodeStore.selectedNode();

    if (!def) {
      this.toast.danger('No definition found for node type.');
      this.isSaving.set(false);
      return;
    }

    const config: any = { ...configRaw };
    def.properties.forEach((prop) => {
      if (prop.type === 'vec3') {
        config[prop.name] = [
          Number(configRaw[prop.name][0]),
          Number(configRaw[prop.name][1]),
          Number(configRaw[prop.name][2]),
        ];
      }
    });

    // For operation nodes, store op_type at top level of config (flat)
    // so build_operation in node_registry.py can read config.get('op_type') directly
    const payload: Partial<NodeConfig> = {
      id: data.id,
      name: val.name,
      type: def.type, // 'crop', 'downsample', 'sensor', 'fusion', etc.
      category: def.category,
      enabled: data.enabled ?? true,
      config:
        def.category === 'operation'
          ? { op_type: def.type, ...config } // flat: op_type + all schema props
          : config,
      x: data.x ?? 100,
      y: data.y ?? 100,
    };

    try {
      await this.nodesApi.upsertNode(payload);
      // Refresh the store so the canvas shows the new/updated node immediately
      const [nodes, edges] = await Promise.all([
        this.nodesApi.getNodes(),
        this.edgesApi.getEdges(),
      ]);
      this.nodeStore.setState({ nodes, edges });
      this.toast.success(`Node "${val.name}" saved.`);
      this.save.emit(payload);
      this.dialogService.close();
    } catch (error) {
      console.error('Failed to save node', error);
      this.toast.danger('Failed to save configuration.');
    } finally {
      this.isSaving.set(false);
    }
  }

  onCancel() {
    this.dialogService.close();
  }

  /** syn-select emits 'syn-change', not 'change' — sync value manually */
  onSelectChange(propName: string, event: Event) {
    const value = (event.target as any).value;
    this.configForm.get(propName)?.setValue(value);
  }

  /** syn-checkbox emits 'syn-change', not 'change' — sync checked manually */
  onCheckboxChange(propName: string, event: Event) {
    const checked = (event.target as any).checked;
    this.configForm.get(propName)?.setValue(checked);
  }
}
