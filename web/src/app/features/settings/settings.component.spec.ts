import {signal} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {of} from 'rxjs';

import {SettingsComponent} from './settings.component';
import {NavigationService} from '../../core/services/navigation.service';
import {LidarApiService} from '../../core/services/api/lidar-api.service';
import {FusionApiService} from '../../core/services/api/fusion-api.service';
import {ToastService} from '../../core/services/toast.service';
import {LidarStoreService} from '../../core/services/stores/lidar-store.service';
import {FusionStoreService} from '../../core/services/stores/fusion-store.service';
import {NodesApiService} from '../../core/services/api/nodes-api.service';
import {StatusWebSocketService} from '../../core/services/status-websocket.service';
import {ConfigTransferService} from '../../core/services/api/config-transfer.service';
import {RecordingStoreService} from '../../core/services/stores/recording-store.service';
import {DagApiService} from '../../core/services/api/dag-api.service';
import {NodePluginRegistry} from '../../core/services/node-plugin-registry.service';

/** Minimal stub that satisfies ConfigTransferService's public API */
const configTransferStub = {
  downloadConfig: () => of({blob: new Blob(['{}'], {type: 'application/json'}), filename: 'lidar-config-test.json'}),
  readAndValidate: () => of({config: {version: '1', lidars: [], fusions: []}, validation: {valid: true, errors: [], warnings: [], summary: {nodes: 0, edges: 0}}}),
  importConfig: () => of({success: true, mode: 'replace', imported: {lidars: 0, fusions: 0}, lidar_ids: [], fusion_ids: []}),
};

describe('SettingsComponent', () => {
  it('loads config on init without errors', async () => {
    // JSDOM doesn't implement the Web Animations API; Synergy's <syn-details>
    // calls `getAnimations()` internally.
    if (!(Element.prototype as any).getAnimations) {
      (Element.prototype as any).getAnimations = () => [];
    }

    await TestBed.configureTestingModule({
      imports: [SettingsComponent],

      providers: [
        {
          provide: NavigationService, useValue: {
            setHeadline: () => {},
            setPageConfig: () => {},
          }
        },
        {
          provide: ToastService,
          useValue: {
            success: () => {},
            warning: () => {},
            danger: () => {},
            primary: () => {},
            neutral: () => {},
          },
        },
        {
          provide: LidarApiService,
          useFactory: (store: LidarStoreService) => ({
            getLidars: async () => {
              const lidars: any[] = [{id: 'l1', name: 'Front', hostname: '', mode: 'real'}];
              store.setState({lidars, availablePipelines: [], isLoading: false});
              return {lidars, available_pipelines: []};
            },
            setEnabled: async () => ({status: 'success'}),
            deleteLidar: async () => ({status: 'success'}),
            reloadConfig: async () => ({status: 'success'}),
            saveLidar: async () => ({status: 'success'}),
          }),
          deps: [LidarStoreService],
        },
        {
          provide: FusionApiService,
          useFactory: (store: FusionStoreService) => ({
            getFusions: async () => {
              const fusions: any[] = [];
              store.setState({fusions, isLoading: false});
              return {fusions};
            },
            setEnabled: async () => ({status: 'success'}),
            deleteFusion: async () => ({status: 'success'}),
            saveFusion: async () => ({status: 'success'}),
          }),
          deps: [FusionStoreService],
        },
        {
          provide: NodesApiService,
          useValue: {
            getNodesStatus: async () => ({lidars: [], fusions: []}),
            getNodeDefinitions: async () => [],
          },
        },
        {
          provide: StatusWebSocketService,
          useValue: {
            status: signal(null),
            connected: signal(false),
            connect: () => {},
            disconnect: () => {},
          },
        },
        {provide: ConfigTransferService, useValue: configTransferStub},
        {
          provide: RecordingStoreService, useValue: {
            loadRecordings: async () => {}
          }
        },
        {
          provide: DagApiService,
          useValue: {
            getDagConfig: async () => ({config_version: 1, nodes: [], edges: []}),
            saveDagConfig: async () => ({config_version: 2, node_id_map: {}}),
          },
        },
        {
          provide: NodePluginRegistry,
          useValue: {
            loadFromBackend: async () => {},
            getAll: () => [],
            get: () => undefined,
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SettingsComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    // The component should render without throwing
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('calls loadFromBackend and getDagConfig in parallel on init', async () => {
    if (!(Element.prototype as any).getAnimations) {
      (Element.prototype as any).getAnimations = () => [];
    }

    const loadFromBackend = vi.fn().mockResolvedValue(undefined);
    const getDagConfig = vi.fn().mockResolvedValue({config_version: 1, nodes: [], edges: []});

    await TestBed.configureTestingModule({
      imports: [SettingsComponent],
      providers: [
        {provide: NavigationService, useValue: {setHeadline: () => {}, setPageConfig: () => {}}},
        {provide: ToastService, useValue: {success: () => {}, warning: () => {}, danger: () => {}, primary: () => {}, neutral: () => {}}},
        {provide: LidarApiService, useValue: {getLidars: async () => ({lidars: [], available_pipelines: []}), setEnabled: async () => ({}), deleteLidar: async () => ({}), reloadConfig: async () => ({}), saveLidar: async () => ({})}},
        {provide: FusionApiService, useValue: {getFusions: async () => ({fusions: []}), setEnabled: async () => ({}), deleteFusion: async () => ({}), saveFusion: async () => ({})}},
        {provide: NodesApiService, useValue: {getNodesStatus: async () => ({lidars: [], fusions: []}), getNodeDefinitions: async () => []}},
        {provide: StatusWebSocketService, useValue: {status: signal(null), connected: signal(false), connect: () => {}, disconnect: () => {}}},
        {provide: ConfigTransferService, useValue: configTransferStub},
        {provide: RecordingStoreService, useValue: {loadRecordings: async () => {}}},
        {provide: DagApiService, useValue: {getDagConfig, saveDagConfig: async () => ({config_version: 2, node_id_map: {}})}},
        {provide: NodePluginRegistry, useValue: {loadFromBackend, getAll: () => [], get: () => undefined}},
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SettingsComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(loadFromBackend).toHaveBeenCalledTimes(1);
    expect(getDagConfig).toHaveBeenCalledTimes(1);
  });

  it('sets isInitializing to false after successful init', async () => {
    if (!(Element.prototype as any).getAnimations) {
      (Element.prototype as any).getAnimations = () => [];
    }

    await TestBed.configureTestingModule({
      imports: [SettingsComponent],
      providers: [
        {provide: NavigationService, useValue: {setHeadline: () => {}, setPageConfig: () => {}}},
        {provide: ToastService, useValue: {success: () => {}, warning: () => {}, danger: () => {}, primary: () => {}, neutral: () => {}}},
        {provide: LidarApiService, useValue: {getLidars: async () => ({lidars: [], available_pipelines: []}), setEnabled: async () => ({}), deleteLidar: async () => ({}), reloadConfig: async () => ({}), saveLidar: async () => ({})}},
        {provide: FusionApiService, useValue: {getFusions: async () => ({fusions: []}), setEnabled: async () => ({}), deleteFusion: async () => ({}), saveFusion: async () => ({})}},
        {provide: NodesApiService, useValue: {getNodesStatus: async () => ({lidars: [], fusions: []}), getNodeDefinitions: async () => []}},
        {provide: StatusWebSocketService, useValue: {status: signal(null), connected: signal(false), connect: () => {}, disconnect: () => {}}},
        {provide: ConfigTransferService, useValue: configTransferStub},
        {provide: RecordingStoreService, useValue: {loadRecordings: async () => {}}},
        {provide: DagApiService, useValue: {getDagConfig: async () => ({config_version: 1, nodes: [], edges: []}), saveDagConfig: async () => ({config_version: 2, node_id_map: {}})}},
        {provide: NodePluginRegistry, useValue: {loadFromBackend: async () => {}, getAll: () => [], get: () => undefined}},
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SettingsComponent);
    const component = fixture.componentInstance as any;

    // isInitializing starts true
    fixture.detectChanges();
    expect(component.isInitializing()).toBe(true);

    // Wait for all async init (Promise.all) to resolve
    await fixture.whenStable();
    fixture.detectChanges();
    await fixture.whenStable(); // second pass ensures signal updates propagate

    expect(component.isInitializing()).toBe(false);
  });
});
