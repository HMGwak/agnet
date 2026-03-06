const WS_BASE = "ws://localhost:8001/ws";

export function getWSUrl(taskId?: number): string {
  if (taskId) return `${WS_BASE}?task_id=${taskId}`;
  return WS_BASE;
}

export type WSMessage = {
  type: "task_state_changed" | "task_log_line";
  task_id: number;
  data: Record<string, string>;
};
