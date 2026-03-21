export const environment = {
  production: true,
  apiUrl: window.location.origin + '/api/v1',
  wsUrl: (topic: string) => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api/v1/ws/${topic}`;
  },
};
