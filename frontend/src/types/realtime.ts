/**
 * Types for v0.5.0 Realtime Event system.
 */

export type RealtimeConnectionState =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'error';

export interface RealtimeEvent<T = any> {
  id: string;
  type: string;
  timestamp: string;
  scope: string;
  conversation_id?: number | null;
  payload: T;
}

export interface RealtimeStats {
  status: string;
  connected_clients: number;
  events_emitted: number;
  dropped_events: number;
  reconnect_count: number;
  replay_buffer_size: number;
}
