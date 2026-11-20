export const EXECUTION_LOG_KEY = 'executionLogs';
export const MAX_EXECUTION_LOGS = 40;
export const PROGRESS_STORAGE_KEY = 'pointageProgress';
export const GITHUB_REPO = 'MattiaPARRINELLO/CheckMate';

export function progressState(message, pourcentage, enCours) {
  return { message, pourcentage, enCours, ts: Date.now() };
}

export function appendExecutionLog(tag, message, level = 'info') {
  const entry = {
    ts: new Date().toISOString(),
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
