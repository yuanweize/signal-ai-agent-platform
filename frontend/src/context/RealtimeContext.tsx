import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { RealtimeConnectionState, RealtimeEvent, RealtimeStats } from '../types/realtime';

interface RealtimeContextValue {
  status: RealtimeConnectionState;
  connectionState: RealtimeConnectionState;
  lastEvent: RealtimeEvent | null;
  addEventListener: (type: string, handler: (event: RealtimeEvent) => void) => () => void;
  reconnect: () => void;
  stats: RealtimeStats | null;
}

const RealtimeContext = createContext<RealtimeContextValue>({
  status: 'disconnected',
  connectionState: 'disconnected',
  lastEvent: null,
  addEventListener: () => () => {},
  reconnect: () => {},
  stats: null,
});

// eslint-disable-next-line react-refresh/only-export-components
export const useRealtime = () => useContext(RealtimeContext);

export const RealtimeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [connectionState, setConnectionState] = useState<RealtimeConnectionState>('disconnected');
  const [lastEvent, setLastEvent] = useState<RealtimeEvent | null>(null);
  const [stats] = useState<RealtimeStats | null>(null);

  const listenersRef = useRef<Map<string, Set<(event: RealtimeEvent) => void>>>(new Map());
  const abortControllerRef = useRef<AbortController | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef<number>(0);
  const lastEventIdRef = useRef<string | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const connectRef = useRef<() => Promise<void>>(async () => {});

  const addEventListener = useCallback((type: string, handler: (event: RealtimeEvent) => void) => {
    if (!listenersRef.current.has(type)) {
      listenersRef.current.set(type, new Set());
    }
    listenersRef.current.get(type)!.add(handler);

    return () => {
      const set = listenersRef.current.get(type);
      if (set) {
        set.delete(handler);
        if (set.size === 0) {
          listenersRef.current.delete(type);
        }
      }
    };
  }, []);

  const dispatchEvent = useCallback((event: RealtimeEvent) => {
    setLastEvent(event);

    // Specific type listeners
    const handlers = listenersRef.current.get(event.type);
    if (handlers) {
      handlers.forEach((h) => {
        try {
          h(event);
        } catch (err) {
          console.error('Error in realtime event handler:', err);
        }
      });
    }

    // Wildcard listeners
    const wildcardHandlers = listenersRef.current.get('*');
    if (wildcardHandlers) {
      wildcardHandlers.forEach((h) => {
        try {
          h(event);
        } catch (err) {
          console.error('Error in wildcard realtime handler:', err);
        }
      });
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
    }
    const attempt = reconnectAttemptRef.current;
    // Exponential backoff with jitter: 1s, 2s, 4s, 8s, up to 15s max
    const baseDelay = Math.min(1000 * Math.pow(2, attempt), 15000);
    const jitter = Math.random() * 1000;
    const delay = baseDelay + jitter;
    reconnectAttemptRef.current += 1;

    reconnectTimeoutRef.current = window.setTimeout(() => {
      connectRef.current();
    }, delay);
  }, []);

  const connect = useCallback(async () => {
    if (!isMountedRef.current) return;

    const token = localStorage.getItem('token');
    if (!token) {
      setConnectionState('disconnected');
      return;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setConnectionState((prev) => (prev === 'disconnected' ? 'connecting' : 'reconnecting'));

    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${token}`,
        Accept: 'text/event-stream',
      };
      if (lastEventIdRef.current) {
        headers['Last-Event-ID'] = lastEventIdRef.current;
      }

      const response = await fetch('/api/realtime/events', {
        headers,
        signal: controller.signal,
      });

      if (!response.ok) {
        if (response.status === 401) {
          setConnectionState('disconnected');
          return;
        }
        throw new Error(`Realtime stream failed with status ${response.status}`);
      }

      if (!response.body) {
        throw new Error('ReadableStream not supported on realtime response');
      }

      setConnectionState('connected');
      reconnectAttemptRef.current = 0; // reset on success

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const block of parts) {
          const lines = block.split('\n');
          let eventType = 'message';
          let eventData = '';
          let eventId: string | null = null;

          for (const line of lines) {
            if (line.startsWith(':')) {
              // Heartbeat comment, ignore
              continue;
            }
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              const dataPart = line.slice(5).trim();
              eventData = eventData ? `${eventData}\n${dataPart}` : dataPart;
            } else if (line.startsWith('id:')) {
              eventId = line.slice(3).trim();
            }
          }

          if (eventId) {
            lastEventIdRef.current = eventId;
          }

          if (eventData) {
            try {
              const parsed = JSON.parse(eventData);
              const ev: RealtimeEvent = {
                id: parsed.id || eventId || String(Date.now()),
                type: parsed.type || eventType,
                timestamp: parsed.timestamp || new Date().toISOString(),
                scope: parsed.scope || 'global',
                conversation_id: parsed.conversation_id,
                payload: parsed.payload !== undefined ? parsed.payload : parsed,
              };
              dispatchEvent(ev);
            } catch {
              console.warn('Failed to parse SSE payload:', eventData);
            }
          }
        }
      }
    } catch (err: unknown) {
      const e = err as { name?: string; message?: string };
      if (e?.name === 'AbortError') return;
      console.warn('Realtime SSE disconnected:', e?.message || err);
      if (isMountedRef.current) {
        setConnectionState('reconnecting');
        scheduleReconnect();
      }
    }
  }, [dispatchEvent, scheduleReconnect]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  const reconnect = useCallback(() => {
    reconnectAttemptRef.current = 0;
    connect();
  }, [connect]);

  useEffect(() => {
    isMountedRef.current = true;
    connect();

    return () => {
      isMountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  return (
    <RealtimeContext.Provider
      value={{
        status: connectionState,
        connectionState,
        lastEvent,
        addEventListener,
        reconnect,
        stats,
      }}
    >
      {children}
    </RealtimeContext.Provider>
  );
};
