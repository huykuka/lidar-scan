import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DagOverviewPanelComponent } from './dag-overview-panel.component';
import { DagNodeMetrics } from '../../../../core/models/metrics.model';

describe('DagOverviewPanelComponent', () => {
  let component: DagOverviewPanelComponent;
  let fixture: ComponentFixture<DagOverviewPanelComponent>;

  const mockDagNodes: DagNodeMetrics[] = [
    {
      node_id: 'test-node-1',
      node_type: 'filter',
      calls_total: 100,
      avg_exec_ms: 2.5,
      last_exec_ms: 2.1,
      throughput_pps: 1500.5,
      points_last_frame: 1000,
      throttled_count: 0,
      last_seen_ts: Date.now() - 5000 // 5 seconds ago
    },
    {
      node_id: 'test-node-2',
      node_type: 'transform',
      calls_total: 150,
      avg_exec_ms: 25.0, // High latency - should be highlighted
      last_exec_ms: 24.8,
      throughput_pps: 800.2,
      points_last_frame: 500,
      throttled_count: 2,
      last_seen_ts: Date.now() - 2000 // 2 seconds ago
    }
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DagOverviewPanelComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(DagOverviewPanelComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render node rows for each DagNodeMetrics input', () => {
    // Set inputs using the new signal-based API
    fixture.componentRef.setInput('nodes', mockDagNodes);
    fixture.componentRef.setInput('totalNodes', 2);
    fixture.componentRef.setInput('runningNodes', 2);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const rows = compiled.querySelectorAll('tbody tr');
    
    expect(rows.length).toBe(2);
    
    // Check first row content
    const firstRowCells = rows[0].querySelectorAll('td');
    expect(firstRowCells[0].textContent).toContain('test-node-1');
    expect(firstRowCells[1].textContent).toContain('filter');
    expect(firstRowCells[2].textContent).toContain('2.5');
    
    // Check second row has highlighting for high latency
    const secondRow = rows[1] as HTMLElement;
    expect(secondRow.classList).toContain('bg-amber-950/30');
  });

  it('should show empty state when nodes array is empty', () => {
    fixture.componentRef.setInput('nodes', []);
    fixture.componentRef.setInput('totalNodes', 0);
    fixture.componentRef.setInput('runningNodes', 0);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('No DAG nodes reporting metrics yet.');
  });

  it('should emit nodeSelected when a row is clicked', () => {
    fixture.componentRef.setInput('nodes', mockDagNodes);
    fixture.componentRef.setInput('totalNodes', 2);
    fixture.componentRef.setInput('runningNodes', 2);
    fixture.detectChanges();

    spyOn(component.nodeSelected, 'emit');

    const compiled = fixture.nativeElement as HTMLElement;
    const firstRow = compiled.querySelector('tbody tr') as HTMLElement;
    
    firstRow.click();
    
    expect(component.nodeSelected.emit).toHaveBeenCalledWith(mockDagNodes[0]);
  });
});