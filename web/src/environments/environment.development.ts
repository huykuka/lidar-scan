export const environment = {
  production: false,
  apiUrl: 'http://localhost:8004',
  wsUrl: (topic: string) => `ws://localhost:8004/ws/${topic}`,
};
