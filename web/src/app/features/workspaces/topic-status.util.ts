import type {NodeStatusUpdate} from '@core/models/node-status.model';

export interface TopicStatusView {
  text: string | null;
  color: string;
  cycle: string | null;
}

const BADGE_COLORS: Record<string, string> = {
  green: '#16a34a',
  blue: '#2563eb',
  orange: '#d97706',
  red: '#dc2626',
  gray: '#6b7280',
};

/** Live status per topic. Topics are named `{node_name}_{node_id[:8]}`. */
export function buildTopicStatuses(
  statuses: NodeStatusUpdate[],
  topics: string[],
): Map<string, TopicStatusView> {
  const result = new Map<string, TopicStatusView>();
  for (const topic of topics) {
    const suffix = topic.slice(topic.lastIndexOf('_') + 1);
    const status = statuses.find((s) => s.node_id.startsWith(suffix));
    if (!status) continue;
    const app = status.application_state;
    const ms = status.cycle_time_ms;
    const cycle =
      ms === null || ms === undefined
        ? null
        : ms >= 1000
          ? `${(ms / 1000).toFixed(1)}s`
          : `${ms.toFixed(ms >= 10 ? 0 : 1)}ms`;
    if (!app && !cycle) continue;
    result.set(topic, {
      text: app ? `${app.label}: ${app.value}` : null,
      color: BADGE_COLORS[app?.color ?? 'gray'] ?? BADGE_COLORS['gray'],
      cycle,
    });
  }
  return result;
}
