export const EXECUTION_LOG_KEY = 'executionLogs';
export const MAX_EXECUTION_LOGS = 40;

export function appendExecutionLog(source, tag, message, level = 'info') {
  const entry = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    ts: new Date().toISOString(),
    source,
    tag,
    message,
    level
  };

  chrome.storage.local.get([EXECUTION_LOG_KEY], (result) => {
    const logs = Array.isArray(result[EXECUTION_LOG_KEY]) ? result[EXECUTION_LOG_KEY] : [];
    logs.unshift(entry);
    chrome.storage.local.set({ [EXECUTION_LOG_KEY]: logs.slice(0, MAX_EXECUTION_LOGS) });
  });
}
