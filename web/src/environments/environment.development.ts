export const environment = {
  production: false,
  apiUrl: 'http://fedora:8004/api/v1',
  wsUrl: (topic: string) => `ws://fedora:8004/api/v1/ws/${topic}`,
};
