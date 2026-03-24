import { ComponentFixture, TestBed } from '@angular/core/testing';

import { OutputViewerComponent } from './output-viewer.component';

describe('OutputViewerComponent', () => {
  let component: OutputViewerComponent;
  let fixture: ComponentFixture<OutputViewerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [OutputViewerComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(OutputViewerComponent);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
