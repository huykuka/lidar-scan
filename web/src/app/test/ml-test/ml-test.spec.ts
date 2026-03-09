import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MlTest } from './ml-test';

describe('MlTest', () => {
  let component: MlTest;
  let fixture: ComponentFixture<MlTest>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MlTest]
    })
    .compileComponents();

    fixture = TestBed.createComponent(MlTest);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
