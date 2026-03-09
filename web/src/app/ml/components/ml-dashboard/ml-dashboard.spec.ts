import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MlDashboardComponent } from './ml-dashboard';

describe('MlDashboardComponent', () => {
  let component: MlDashboardComponent;
  let fixture: ComponentFixture<MlDashboardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MlDashboardComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(MlDashboardComponent);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
