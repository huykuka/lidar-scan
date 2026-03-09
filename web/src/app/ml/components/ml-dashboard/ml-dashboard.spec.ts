import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MlDashboard } from './ml-dashboard';

describe('MlDashboard', () => {
  let component: MlDashboard;
  let fixture: ComponentFixture<MlDashboard>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MlDashboard]
    })
    .compileComponents();

    fixture = TestBed.createComponent(MlDashboard);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
