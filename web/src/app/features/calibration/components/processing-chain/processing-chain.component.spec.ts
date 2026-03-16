import {ComponentFixture, TestBed} from '@angular/core/testing';
import {ProcessingChainComponent} from './processing-chain.component';
import {ComponentRef} from '@angular/core';

describe('ProcessingChainComponent', () => {
  let component: ProcessingChainComponent;
  let componentRef: ComponentRef<ProcessingChainComponent>;
  let fixture: ComponentFixture<ProcessingChainComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProcessingChainComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ProcessingChainComponent);
    component = fixture.componentInstance;
    componentRef = fixture.componentRef;
  });

  it('should create', () => {
    componentRef.setInput('processingChain', []);
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should render empty chain message when processing chain is empty', () => {
    componentRef.setInput('processingChain', []);
    fixture.detectChanges();
    
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('No processing chain');
  });

  it('should render single-node chain correctly', () => {
    componentRef.setInput('processingChain', ['sensor-A']);
    fixture.detectChanges();
    
    const badges = fixture.nativeElement.querySelectorAll('syn-badge');
    expect(badges.length).toBe(1);
  });

  it('should render multi-node chain with arrows', () => {
    componentRef.setInput('processingChain', ['sensor-A', 'crop-node', 'downsample-node']);
    fixture.detectChanges();
    
    const compiled = fixture.nativeElement as HTMLElement;
    const badges = compiled.querySelectorAll('syn-badge');
    const arrows = compiled.querySelectorAll('span');
    
    expect(badges.length).toBe(3);
    // Should have 2 arrows for 3 nodes
    const arrowCount = Array.from(arrows).filter(span => span.textContent?.includes('→')).length;
    expect(arrowCount).toBe(2);
  });

  it('should render in compact mode', () => {
    componentRef.setInput('processingChain', ['sensor-A', 'crop-node', 'downsample-node']);
    componentRef.setInput('displayMode', 'compact');
    fixture.detectChanges();
    
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('3 nodes');
  });

  it('should shorten long node IDs', () => {
    const longId = 'very-long-uuid-1234-5678-9012-34567890';
    componentRef.setInput('processingChain', [longId]);
    fixture.detectChanges();
    
    const shortenedName = component.getNodeDisplayName(longId);
    expect(shortenedName).toContain('...');
    expect(shortenedName.length).toBeLessThan(longId.length);
  });

  it('should hide last node when showLastNode is false', () => {
    componentRef.setInput('processingChain', ['sensor-A', 'crop-node', 'calibration-node']);
    componentRef.setInput('showLastNode', false);
    fixture.detectChanges();
    
    const displayChain = component.getDisplayChain();
    expect(displayChain.length).toBe(2);
    expect(displayChain).toEqual(['sensor-A', 'crop-node']);
  });
});
