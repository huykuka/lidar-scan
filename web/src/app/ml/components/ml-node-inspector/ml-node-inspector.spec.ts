import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MlNodeInspectorComponent } from './ml-node-inspector';

describe('MlNodeInspectorComponent', () => {
  let component: MlNodeInspectorComponent;
  let fixture: ComponentFixture<MlNodeInspectorComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MlNodeInspectorComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(MlNodeInspectorComponent);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
