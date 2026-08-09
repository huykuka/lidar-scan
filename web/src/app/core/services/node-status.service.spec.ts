import {TestBed} from '@angular/core/testing';
import {Subject} from 'rxjs';

import {NodeStatusService} from './node-status.service';
import {MultiWebsocketService} from './multi-websocket.service';
import {SystemStatusService} from './system-status.service';
import {SystemStatusBroadcast} from '@core/models/status.model';

// Minimal mock — only what NodeStatusService touches
const mockSubject = new Subject<any>();
const wsServiceMock = {
  connect: vi.fn(() => mockSubject.asObservable()),
  disconnect: vi.fn(),
};

const systemStatusMock = {
  applyReloadEvent: vi.fn(),
  applySystemStatus: vi.fn(),
  setOffline: vi.fn(),
  clearReloadingState: vi.fn(),
};

describe('NodeStatusService', () => {
  let service: NodeStatusService;

  beforeEach(() => {
    vi.clearAllMocks();

    TestBed.configureTestingModule({
      providers: [
        NodeStatusService,
        {provide: MultiWebsocketService, useValue: wsServiceMock},
        {provide: SystemStatusService, useValue: systemStatusMock},
      ],
    });
    service = TestBed.inject(NodeStatusService);
  });

  function connectAndEmit(msg: SystemStatusBroadcast | string) {
    service.connect();
    mockSubject.next(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }

  it('forwards data.system to applySystemStatus when present', () => {
    const msg: SystemStatusBroadcast = {
      nodes: [],
      system: {is_running: true, active_sensors: ['l1'], version: '1.0.0'},
    };
    connectAndEmit(msg);
    expect(systemStatusMock.applySystemStatus).toHaveBeenCalledWith(msg.system);
  });

  it('does NOT call applySystemStatus when system field absent', () => {
    const msg: SystemStatusBroadcast = {nodes: []};
    connectAndEmit(msg);
    expect(systemStatusMock.applySystemStatus).not.toHaveBeenCalled();
  });

  it('forwards reload_event to applyReloadEvent', () => {
    const event = {
      node_id: 'n1', status: 'reloading' as const, error_message: null,
      reload_mode: 'selective' as const, timestamp: 1000,
    };
    const msg: SystemStatusBroadcast = {nodes: [], reload_event: event};
    connectAndEmit(msg);
    expect(systemStatusMock.applyReloadEvent).toHaveBeenCalledWith(event);
  });

  it('calls setOffline + clearReloadingState on WS complete', () => {
    // Need fresh subject for complete test
    const completeSubject = new Subject<any>();
    wsServiceMock.connect.mockReturnValueOnce(completeSubject.asObservable());
    service.connect();
    completeSubject.complete();
    expect(systemStatusMock.setOffline).toHaveBeenCalledTimes(1);
    expect(systemStatusMock.clearReloadingState).toHaveBeenCalledTimes(1);
  });

  it('ignores ping messages', () => {
    connectAndEmit('ping');
    expect(systemStatusMock.applySystemStatus).not.toHaveBeenCalled();
    expect(systemStatusMock.applyReloadEvent).not.toHaveBeenCalled();
  });
});
