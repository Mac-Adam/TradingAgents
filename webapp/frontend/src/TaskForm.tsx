import { useState } from 'react';

const API = 'http://localhost:8000';

interface Props {
  walletId: string;
  onTaskAdded: () => void;
}

const PRESETS = [
  { label: "Select a Preset...", value: "" },
  { label: "S&P Top 10", value: "AAPL, MSFT, NVDA, AMZN, META, GOOGL, BRK.B, LLY, AVGO, JPM" },
  { label: "Big Tech 5", value: "AAPL, MSFT, GOOGL, AMZN, META" }
];

export default function TaskForm({ walletId, onTaskAdded }: Props) {
  const [ticker, setTicker] = useState('');
  const [scheduleMode, setScheduleMode] = useState<'asap' | 'scheduled'>('asap');
  const [scheduledAt, setScheduledAt] = useState(() => new Date().toISOString().slice(0, 16));
  const [recurring, setRecurring] = useState(false);
  const [isQueueing, setIsQueueing] = useState(false);
  const [taskType, setTaskType] = useState<'analysis' | 'execution' | 'bookkeeping'>('analysis');

  const handleSubmit = async () => {
    if (isQueueing) return;
    if (taskType === 'analysis' && !ticker.trim()) return;

    const tickersToQueue = taskType === 'analysis'
      ? ticker.split(',').map(t => t.trim().toUpperCase()).filter(t => t)
      : ['PORTFOLIO'];

    if (tickersToQueue.length === 0) return;

    setIsQueueing(true);
    try {
      await Promise.all(tickersToQueue.map(t => {
        const body: Record<string, string | null> = {
          ticker: t,
          task_type: taskType,
          schedule_mode: scheduleMode,
          scheduled_at: scheduleMode === 'scheduled' && scheduledAt
            ? new Date(scheduledAt + ':00Z').toISOString()
            : null,
          recurrence: scheduleMode === 'scheduled' && recurring && scheduledAt
            ? `daily:${scheduledAt.slice(11, 16)}`
            : null,
        };
        return fetch(`${API}/api/runs/${walletId}/tasks`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      }));
      setTicker('');
      onTaskAdded();
    } catch (err) {
      console.error(err);
    } finally {
      setIsQueueing(false);
    }
  };

  return (
    <div className="space-y-3 mb-5 p-4 bg-slate-800 border border-slate-700 rounded-lg">
      {/* Task type selector — FIRST, controls everything below */}
      <div className="flex items-center gap-1 bg-black rounded-lg p-1 w-fit">
        <button
          type="button"
          onClick={() => setTaskType('analysis')}
          className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-all ${
            taskType === 'analysis'
              ? 'bg-blue-500/20 text-blue-400 shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          📊 Analysis
        </button>
        <button
          type="button"
          onClick={() => setTaskType('execution')}
          className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-all ${
            taskType === 'execution'
              ? 'bg-purple-500/20 text-purple-400 shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          ⚡ Execution
        </button>
        <button
          type="button"
          onClick={() => setTaskType('bookkeeping')}
          className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-all ${
            taskType === 'bookkeeping'
              ? 'bg-amber-500/20 text-amber-400 shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          📚 Bookkeeping
        </button>
      </div>

      {/* Task input — different per type */}
      {taskType === 'analysis' ? (
        <div className="flex gap-3">
          <select
            onChange={(e) => {
              if (e.target.value) setTicker(e.target.value);
              e.target.value = "";
            }}
            className="bg-black border border-slate-600 rounded-lg p-3 text-white outline-none focus:border-accent transition-colors"
          >
            {PRESETS.map((p, i) => <option key={i} value={p.value}>{p.label}</option>)}
          </select>
          <input
            type="text"
            placeholder="Ticker(s) comma-separated (e.g. AAPL, NVDA)"
            value={ticker}
            onChange={e => setTicker(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            className="flex-grow bg-black border border-slate-600 rounded-lg p-3 text-white outline-none focus:border-accent transition-colors uppercase font-mono"
            disabled={isQueueing}
          />
          <button
            onClick={handleSubmit}
            disabled={isQueueing || !ticker.trim()}
            className="px-5 py-3 bg-accent hover:bg-accent/80 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-lg transition-colors shadow-lg shadow-accent/20 shrink-0"
          >
            {isQueueing ? "Queueing..." : scheduleMode === 'scheduled' ? "Schedule Analysis" : "Queue Analysis"}
          </button>
        </div>
      ) : taskType === 'execution' ? (
        /* Execution flow — simple and distinct */
        <div className="flex gap-3 items-center">
          <div className="flex-grow bg-slate-900/50 border border-purple-500/20 rounded-lg p-3 text-slate-300 text-sm flex items-center gap-2">
            <span className="text-purple-400">⚡</span>
            Execute all pending trades queued by previous analyses.
          </div>
          <button
            onClick={handleSubmit}
            disabled={isQueueing}
            className="px-5 py-3 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-lg transition-colors shadow-lg shadow-purple-600/20 shrink-0"
          >
            {isQueueing ? "Queueing..." : scheduleMode === 'scheduled' ? "Schedule Execution" : "Execute Trades"}
          </button>
        </div>
      ) : (
        /* Bookkeeping flow */
        <div className="flex gap-3 items-center">
          <div className="flex-grow bg-slate-900/50 border border-amber-500/20 rounded-lg p-3 text-slate-300 text-sm flex items-center gap-2">
            <span className="text-amber-400">📚</span>
            Reconcile virtual portfolio positions and cash with actual IBKR fills and commissions.
          </div>
          <button
            onClick={handleSubmit}
            disabled={isQueueing}
            className="px-5 py-3 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-lg transition-colors shadow-lg shadow-amber-600/20 shrink-0"
          >
            {isQueueing ? "Queueing..." : scheduleMode === 'scheduled' ? "Schedule Bookkeeping" : "Run Bookkeeper"}
          </button>
        </div>
      )}

      {/* Schedule options — for all types */}
      <div className="flex items-center gap-4 pt-2 border-t border-slate-700/50">
        <span className="text-slate-400 text-xs font-semibold uppercase">Schedule:</span>
        <label className="flex items-center gap-2 cursor-pointer">
          <input 
            type="radio" 
            checked={scheduleMode === 'asap'} 
            onChange={() => setScheduleMode('asap')} 
            className="accent-accent" 
          />
          <span className="text-slate-300 text-sm">ASAP</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input 
            type="radio" 
            checked={scheduleMode === 'scheduled'} 
            onChange={() => setScheduleMode('scheduled')} 
            className="accent-accent" 
          />
          <span className="text-slate-300 text-sm">Scheduled</span>
        </label>
      </div>

      {scheduleMode === 'scheduled' && (
        <div className={`space-y-3 pl-3 border-l-2 ${taskType === 'execution' ? 'border-purple-500/50' : taskType === 'bookkeeping' ? 'border-amber-500/50' : 'border-accent/50'} mt-2`}>
          <div className="flex items-end gap-3">
            <div className="flex-grow">
              <label className="text-slate-400 text-xs uppercase block mb-1">Run at (UTC)</label>
              <input
                type="datetime-local"
                value={scheduledAt}
                onChange={e => setScheduledAt(e.target.value)}
                className={`w-full bg-black border ${taskType === 'execution' ? 'border-purple-500/30 focus:border-purple-500' : taskType === 'bookkeeping' ? 'border-amber-500/30 focus:border-amber-500' : 'border-slate-600 focus:border-accent'} rounded p-2 text-white text-sm outline-none transition-colors`}
              />
            </div>
            <div className="text-[10px] text-slate-500 font-mono mb-2 bg-slate-900 px-2 py-1 rounded border border-slate-700">
              Current UTC: {new Date().toISOString().slice(0, 16).replace('T', ' ')}
            </div>
          </div>
          
          <label className="flex items-center gap-2 cursor-pointer">
            <input 
              type="checkbox" 
              checked={recurring} 
              onChange={e => setRecurring(e.target.checked)} 
              className="accent-accent" 
            />
            <span className="text-slate-300 text-sm">Repeat daily</span>
          </label>
        </div>
      )}
    </div>
  );
}
