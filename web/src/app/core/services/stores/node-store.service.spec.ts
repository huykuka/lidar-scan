// @ts-nocheck
import { TestBed } from '@angular/core/testing';
import { NodeStoreService } from './node-store.service';
import { NodeStatusService } from '../node-status.service';
import { NodesStatusResponse } from '../../models/node-status.model';

describe('NodeStoreService', () => {
  let service: NodeStoreService;
  let mockStatusWebSocketService: jasmine.SpyObj<NodeStatusService>;

  beforeEach(() => {
    const statusServiceSpy = jasmine.createSpyObj('NodeStatusService', [], {
      status: jasmine.createSpy('status'),
    });

    TestBed.configureTestingModule({
      providers: [
        NodeStoreService,
        { provide: NodeStatusService, useValue: statusServiceSpy },
      ],
    });

    service = TestBed.inject(NodeStoreService);
    mockStatusWebSocketService = TestBed.inject(NodeStatusService) as jasmine.SpyObj<NodeStatusService>;
  });

  describe('nodeStatusMap', () => {
    it('should build a Map keyed by node_id', () => {
      const mockResponse: NodesStatusResponse = {
        nodes: [
          {
            node_id: 'node_1',
            operational_state: 'RUNNING',
            timestamp: Date.now() / 1000,
          },
          {
            node_id: 'node_2',
            operational_state: 'ERROR',
            error_message: 'Test error',
            timestamp: Date.now() / 1000,
          },
        ],
      };

      // Mock the signal to return our test data
      Object.defineProperty(mockStatusWebSocketService, 'status', {
        get: () => jasmine.createSpy('status').and.returnValue(mockResponse),
      });

      const statusMap = service.nodeStatusMap();
      
      expect(statusMap.size).toBe(2);
      expect(statusMap.get('node_1')?.operational_state).toBe('RUNNING');
      expect(statusMap.get('node_2')?.operational_state).toBe('ERROR');
      expect(statusMap.get('node_2')?.error_message).toBe('Test error');
    });

    it('should return empty Map when status is null', () => {
      // Mock the signal to return null
      Object.defineProperty(mockStatusWebSocketService, 'status', {
        get: () => jasmine.createSpy('status').and.returnValue(null),
      });

      const statusMap = service.nodeStatusMap();
      
      expect(statusMap.size).toBe(0);
    });

    it('should return empty Map when status.nodes is undefined', () => {
      // Mock the signal to return an empty response
      Object.defineProperty(mockStatusWebSocketService, 'status', {
        get: () => jasmine.createSpy('status').and.returnValue({ nodes: undefined }),
      });

      const statusMap = service.nodeStatusMap();
      
      expect(statusMap.size).toBe(0);
    });
  });
});
