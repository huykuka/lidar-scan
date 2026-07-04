import {ComponentFixture, TestBed} from '@angular/core/testing';

import {ThreedSceneComponent} from './threed-scene.component';

describe('ThreedSceneComponent', () => {
  let component: ThreedSceneComponent;
  let fixture: ComponentFixture<ThreedSceneComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ThreedSceneComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ThreedSceneComponent);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
