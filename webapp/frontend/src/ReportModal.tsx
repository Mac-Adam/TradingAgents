import { useState, useEffect, useRef } from 'react';

const API = 'http://localhost:8000';

interface Props {
  runId: string;
  historyId?: string;
  taskId?: string;
  ticker: string;
  taskType: string;   // 'analysis' | 'execution' | ...
  taskStatus: string; // 'running' | 'completed' | 'failed'
  onClose: () => void;
}

export default function ReportModal({ runId, historyId, taskId, ticker, taskType, taskStatus, onClose }: Props) {
  const [report, setReport] = useState<string | null>(null);
  const [logs, setLogs] = useState<string | null>(null);
  const [liveState, setLiveState] = useState<{ agent_status: Record<string, string>, messages: [string, string, string][] } | null>(null);
  const [loading, setLoading] = useState(true);

  // Only analysis tasks that completed successfully have a report tab
  const hasReport = taskType === 'analysis' && taskStatus === 'completed';
  const [activeTab, setActiveTab] = useState<'report' | 'logs'>(hasReport ? 'report' : 'logs');
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Initial fetch
  useEffect(() => {
    const promises: Promise<void>[] = [];

    if (historyId && hasReport) {
      promises.push(
        fetch(`${API}/api/runs/${runId}/history/${historyId}/report`)
          .then(r => r.ok ? r.json() : Promise.reject())
          .then(d => setReport(d.report))
          .catch(() => setReport(null))
      );
    }

    if (taskId) {
      promises.push(
        fetch(`${API}/api/tasks/${taskId}/logs`)
          .then(r => r.ok ? r.json() : Promise.reject())
          .then(d => setLogs(d.logs))
          .catch(() => setLogs(null))
      );
    }

    Promise.allSettled(promises).then(() => setLoading(false));
  }, [runId, historyId, taskId, hasReport]);

  // Polling for live logs (only when task is running)
  useEffect(() => {
    if (taskStatus === 'running' && activeTab === 'logs' && taskId) {
      const interval = setInterval(() => {
        if (taskType === 'analysis') {
          fetch(`${API}/api/tasks/${taskId}/live`)
            .then(r => r.ok ? r.json() : Promise.reject())
            .then(d => setLiveState(d))
            .catch(console.error);
        }
        fetch(`${API}/api/tasks/${taskId}/logs`)
          .then(r => r.ok ? r.json() : Promise.reject())
          .then(d => setLogs(d.logs))
          .catch(console.error);
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [taskStatus, taskType, activeTab, taskId]);

  const handleCancel = () => {
    if (!taskId || !runId) return;
    if (confirm("Are you sure you want to cancel this task?")) {
      fetch(`${API}/api/runs/${runId}/tasks/${taskId}`, { method: 'DELETE' })
        .then(() => onClose())
        .catch(console.error);
    }
  };

  // Auto-scroll
  useEffect(() => {
    if (activeTab === 'logs' && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, activeTab]);

  // Header title per task type + status
  const headerTitle = (() => {
    if (taskStatus === 'running') return `⏳ Running ${taskType}`;
    if (taskStatus === 'failed') return `❌ Failed ${taskType}`;
    if (taskType === 'execution') return '⚡ Trade Execution';
    return '📊 Analysis Report';
  })();

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-8" onClick={onClose}>
      <div
        className="bg-slate-900 border border-slate-600 rounded-2xl shadow-2xl w-full max-w-5xl max-h-[85vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-white">
              {headerTitle}: {ticker}
            </h2>
            <span className={`px-1.5 py-0.5 text-[10px] uppercase font-bold rounded border ${
              taskType === 'execution' ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' : 'bg-blue-500/20 text-blue-400 border-blue-500/30'
            }`}>
              {taskType}
            </span>
            {taskStatus === 'failed' && (
              <span className="px-2 py-0.5 bg-red-500/20 text-red-400 border border-red-500/30 rounded text-xs font-bold">
                FAILED
              </span>
            )}
            {taskStatus === 'running' && (
              <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded text-xs font-bold animate-pulse">
                LIVE
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
            {taskStatus === 'running' && (
              <button onClick={handleCancel} className="px-3 py-1.5 bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 rounded text-sm font-bold transition-colors">
                ⏹ Cancel Task
              </button>
            )}
            <button onClick={onClose} className="text-slate-400 hover:text-white text-2xl leading-none">&times;</button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-700">
          {hasReport && (
            <button
              onClick={() => setActiveTab('report')}
              className={`px-6 py-3 text-sm font-medium transition-colors ${activeTab === 'report'
                  ? 'text-accent border-b-2 border-accent bg-accent/5'
                  : 'text-slate-400 hover:text-white'
                }`}
            >
              📄 Report
            </button>
          )}
          <button
            onClick={() => setActiveTab('logs')}
            className={`px-6 py-3 text-sm font-medium transition-colors flex items-center gap-2 ${activeTab === 'logs'
                ? 'text-accent border-b-2 border-accent bg-accent/5'
                : 'text-slate-400 hover:text-white'
              }`}
          >
            🔍 {taskStatus === 'running' ? 'Live Logs' : 'Logs'}
            {taskStatus === 'running' && activeTab === 'logs' && <span className="w-2 h-2 rounded-full bg-accent animate-ping" />}
          </button>
        </div>

        {/* Content */}
        <div className="flex-grow overflow-y-auto p-6 bg-black rounded-b-2xl flex flex-col">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 rounded-full border-2 border-accent border-t-transparent animate-spin" />
            </div>
          ) : activeTab === 'report' ? (
            report ? (
              <pre className="text-slate-200 text-sm whitespace-pre-wrap font-mono leading-relaxed">{report}</pre>
            ) : (
              <p className="text-slate-400 text-center py-12">Report not available.</p>
            )
          ) : (
            <div className="flex flex-col gap-6 flex-grow">
              {/* Agent Status grid — only for analysis tasks that are running */}
              {taskType === 'analysis' && taskStatus === 'running' && liveState && (
                <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 shrink-0">
                  <h3 className="text-slate-300 font-bold mb-3 border-b border-slate-800 pb-2">Agent Status</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
                    {[
                      { title: "Analyst Team", agents: ["Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst"] },
                      { title: "Research Team", agents: ["Bull Researcher", "Bear Researcher", "Research Manager"] },
                      { title: "Risk & Trading", agents: ["Trader", "Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"] },
                      { title: "Portfolio", agents: ["Portfolio Manager"] }
                    ].map(group => (
                      <div key={group.title} className="space-y-1.5">
                        <div className="text-slate-500 font-bold mb-2">{group.title}</div>
                        {group.agents.map(agent => {
                          const status = liveState.agent_status[agent] || 'pending';
                          return (
                            <div key={agent} className="flex items-center justify-between gap-2">
                              <span className="text-slate-300 truncate" title={agent}>{agent}</span>
                              <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase shrink-0 ${status === 'completed' ? 'bg-green-500/20 text-green-400 border border-green-500/30' :
                                  status === 'in_progress' ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 animate-pulse' :
                                    'bg-slate-800 text-slate-500 border border-slate-700'
                                }`}>
                                {status}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="relative flex-grow flex flex-col bg-slate-950 border border-slate-800 rounded-xl p-4">
                <h3 className="text-slate-500 font-bold mb-3 border-b border-slate-800 pb-2 text-xs">
                  {taskStatus === 'running' ? 'Live Logs' : 'Logs'}
                </h3>
                <div className="flex-grow overflow-x-auto pb-4">
                  {taskType === 'analysis' && taskStatus === 'running' && liveState?.messages && liveState.messages.length > 0 ? (
                    <div className="space-y-2 text-xs font-mono">
                      {liveState.messages.map((msg, i) => (
                        <div key={i} className="flex gap-3">
                          <span className="text-slate-500 shrink-0">[{msg[0]}]</span>
                          <span className={`shrink-0 font-bold ${msg[1] === 'System' ? 'text-blue-400' :
                              msg[1] === 'Agent' ? 'text-green-400' :
                                msg[1] === 'Tool Call' ? 'text-yellow-400' : 'text-slate-400'
                            }`}>[{msg[1]}]</span>
                          <span className="text-slate-300 break-words">{msg[2]}</span>
                        </div>
                      ))}
                      <div ref={logsEndRef} />
                    </div>
                  ) : logs ? (
                    <pre className="text-slate-300 text-xs whitespace-pre-wrap font-mono leading-relaxed">
                      {logs}
                      <div ref={logsEndRef} />
                    </pre>
                  ) : (
                    <p className="text-slate-500 text-center py-8">No logs available.</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
