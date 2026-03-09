import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MlNodeInspector } from './ml-node-inspector';

describe('MlNodeInspector', () => {
  let component: MlNodeInspector;
  let fixture: ComponentFixture<MlNodeInspector>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MlNodeInspector]
    })
    .compileComponents();

    fixture = TestBed.createComponent(MlNodeInspector);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
