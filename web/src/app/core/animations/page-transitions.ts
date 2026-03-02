import { trigger, transition, style, query, animate, group } from '@angular/animations';

export const pageTransition = trigger('routeAnimations', [
  transition('* <=> *', [
    style({ position: 'relative', overflow: 'hidden' }),
    query(
      ':enter, :leave',
      [
        style({
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          opacity: 0,
        }),
      ],
      { optional: true },
    ),
    query(
      ':enter',
      [
        style({
          opacity: 0,
          transform: 'scale(0.95)',
        }),
      ],
      { optional: true },
    ),
    group([
      query(
        ':leave',
        [
          animate(
            '200ms ease-in',
            style({
              opacity: 0,
              transform: 'scale(0.95)',
            }),
          ),
        ],
        { optional: true },
      ),
      query(
        ':enter',
        [
          animate(
            '300ms 100ms ease-out',
            style({
              opacity: 1,
              transform: 'scale(1)',
            }),
          ),
        ],
        { optional: true },
      ),
    ]),
  ]),
]);
