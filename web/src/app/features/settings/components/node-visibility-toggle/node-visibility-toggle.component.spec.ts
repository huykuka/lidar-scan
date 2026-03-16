import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component, signal } from '@angular/core';
import { vi } from 'vitest';
import { NodeVisibilityToggleComponent } from './node-visibility-toggle.component';
import { NodeConfig } from '../../../../core/models/node.model';

// Test host component to test inputs/outputs
@Component({
  template: `
    <app-node-visibility-toggle 
      [node]="testNode()" 
      [isPending]="isPending()"
      (visibilityChanged)="onVisibilityChanged($event)">
    </app-node-visibility-toggle>
  `,
  imports: [NodeVisibilityToggleComponent]
})
class TestHostComponent {
  testNode = signal<NodeConfig>({
    id: 'test-node-1',
    name: 'Test Node',
    type: 'sensor',
    category: 'sensor',
    enabled: true,
    visible: true,
    config: {},
    x: 0,
    y: 0
  });
  isPending = signal(false);
  onVisibilityChanged = vi.fn();
}

describe('NodeVisibilityToggleComponent', () => {
  let component: NodeVisibilityToggleComponent;
  let fixture: ComponentFixture<NodeVisibilityToggleComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NodeVisibilityToggleComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(NodeVisibilityToggleComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
