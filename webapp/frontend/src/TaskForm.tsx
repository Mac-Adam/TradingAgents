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
  const [scheduledAt, setScheduledAt] = useState('');
  const [recurring, setRecurring] = useState(false);
  const [recurTime, setRecurTime] = useState('21:00');
  const [isQueueing, setIsQueueing] = useState(false);

  const handleSubmit = async () => {
    if (!ticker.trim() || isQueueing) return;

    const tickersToQueue = ticker.split(',').map(t => t.trim().toUpperCase()).filter(t => t);
    if (tickersToQueue.length === 0) return;

    setIsQueueing(true);
    try {
      await Promise.all(tickersToQueue.map(t => {
        const body: Record<string, string | null> = {
          ticker: t,
          schedule_mode: scheduleMode,
          scheduled_at: scheduleMode === 'scheduled' && scheduledAt ? new Date(scheduledAt).toISOString() : null,
          recurrence: scheduleMode === 'scheduled' && recurring ? `daily:${recurTime}` : null,
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
      <div className="flex flex-col gap-3">
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
            {isQueueing ? "Queueing..." : "Queue"}
          </button>
        </div>
      </div>


      {/* Schedule toggle */}
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="radio" checked={scheduleMode === 'asap'} onChange={() => setScheduleMode('asap')} className="accent-accent" />
          <span className="text-slate-300 text-sm">ASAP</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="radio" checked={scheduleMode === 'scheduled'} onChange={() => setScheduleMode('scheduled')} className="accent-accent" />
          <span className="text-slate-300 text-sm">Scheduled</span>
        </label>
      </div>

      {scheduleMode === 'scheduled' && (
        <div className="space-y-2 pl-2 border-l-2 border-accent/30">
          <div>
            <label className="text-slate-400 text-xs uppercase block mb-1">Run at</label>
            <input
              type="datetime-local"
              value={scheduledAt}
              onChange={e => setScheduledAt(e.target.value)}
              className="bg-black border border-slate-600 rounded p-2 text-white text-sm outline-none focus:border-accent"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={recurring} onChange={e => setRecurring(e.target.checked)} className="accent-accent" />
            <span className="text-slate-300 text-sm">Repeat daily</span>
          </label>
          {recurring && (
            <div>
              <label className="text-slate-400 text-xs uppercase block mb-1">Daily at (UTC)</label>
              <input
                type="time"
                value={recurTime}
                onChange={e => setRecurTime(e.target.value)}
                className="bg-black border border-slate-600 rounded p-2 text-white text-sm outline-none focus:border-accent"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
