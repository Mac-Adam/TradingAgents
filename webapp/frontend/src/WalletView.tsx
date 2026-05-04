import { useState, useEffect, useCallback } from 'react';
import type { Run, TaskRecord, DecisionRecord } from './types';
import TaskForm from './TaskForm';
import ReportModal from './ReportModal';

const API = 'http://localhost:8000';

interface WalletViewProps {
  wallet: Run;
  onBack: () => void;
  onDelete: () => void;
}

interface AccountData {
  equity: number;
  portfolio_value: number;
  cash: number;
  buying_power: number;
  currency: string;
  account_number: string;
  status: string;
}

interface Position {
  symbol: string;
  qty: number;
  avg_entry_price: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pl: number | null;
  unrealized_plpc: number | null;
  side: string;
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-6">
      <div className="w-5 h-5 rounded-full border-2 border-accent border-t-transparent animate-spin" />
    </div>
  );
}

function Err({ msg }: { msg: string }) {
  return <p className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded p-3">{msg}</p>;
}

export default function WalletView({ wallet, onBack, onDelete }: WalletViewProps) {
  const isReal = wallet.account_type === 'REAL';

  // Alpaca
  const [account, setAccount] = useState<AccountData | null>(null);
  const [accountLoading, setAccountLoading] = useState(true);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [positionsLoading, setPositionsLoading] = useState(true);
  const [positionsError, setPositionsError] = useState<string | null>(null);

  // Tasks (from API)
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  // History (from API)
  const [history, setHistory] = useState<DecisionRecord[]>([]);
  // Report modal
  const [viewingReport, setViewingReport] = useState<{ id: string; ticker: string; taskId?: string; isFailed?: boolean; isRunning?: boolean } | null>(null);

  // Server time
  const [serverTime, setServerTime] = useState<string>('');

  // Delete confirm
  const [isDeleting, setIsDeleting] = useState(false);

  // ── Fetchers ────────────────────────────────
  const fetchAccount = useCallback(() => {
    setAccountLoading(true); setAccountError(null);
    fetch(`${API}/api/runs/${wallet.id}/account`)
      .then(r => r.ok ? r.json() : r.json().then(d => Promise.reject(d.detail ?? 'Error')))
      .then((d: AccountData) => setAccount(d))
      .catch(e => setAccountError(String(e)))
      .finally(() => setAccountLoading(false));
  }, [wallet.id]);

  const fetchPositions = useCallback(() => {
    setPositionsLoading(true); setPositionsError(null);
    fetch(`${API}/api/runs/${wallet.id}/positions`)
      .then(r => r.ok ? r.json() : r.json().then(d => Promise.reject(d.detail ?? 'Error')))
      .then((d: Position[]) => setPositions(d))
      .catch(e => setPositionsError(String(e)))
      .finally(() => setPositionsLoading(false));
  }, [wallet.id]);

  const fetchTasks = useCallback(() => {
    fetch(`${API}/api/runs/${wallet.id}/tasks`).then(r => r.json()).then(setTasks).catch(console.error);
  }, [wallet.id]);

  const fetchHistory = useCallback(() => {
    fetch(`${API}/api/runs/${wallet.id}/history`).then(r => r.json()).then(setHistory).catch(console.error);
  }, [wallet.id]);

  const fetchServerTime = useCallback(() => {
    fetch(`${API}/api/server-time`).then(r => r.json()).then(d => setServerTime(d.utc)).catch(() => {});
  }, []);

  useEffect(() => {
    fetchAccount(); fetchPositions(); fetchTasks(); fetchHistory(); fetchServerTime();
    const iv = setInterval(() => { fetchTasks(); fetchHistory(); fetchServerTime(); }, 10_000);
    return () => clearInterval(iv);
  }, [fetchAccount, fetchPositions, fetchTasks, fetchHistory, fetchServerTime]);

  // ── Helpers ─────────────────────────────────
  const fmt = (n: number) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const plColor = (v: number | null) => v === null ? 'text-slate-300' : v >= 0 ? 'text-green-400' : 'text-red-400';

  const handleRemoveTask = (taskId: string) => {
    fetch(`${API}/api/runs/${wallet.id}/tasks/${taskId}`, { method: 'DELETE' }).then(fetchTasks).catch(console.error);
  };

  const handleConfirmDelete = () => {
    fetch(`${API}/api/runs/${wallet.id}`, { method: 'DELETE' }).then(() => onDelete()).catch(console.error);
  };

  const actionColor: Record<string, string> = {
    Buy: 'bg-green-500/20 text-green-400 border-green-500/30',
    Overweight: 'bg-green-500/15 text-green-300 border-green-500/20',
    Hold: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    Underweight: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    Sell: 'bg-red-500/20 text-red-400 border-red-500/30',
    FAILED: 'bg-red-500/30 text-red-300 border-red-500/40',
  };

  const statusBadge = (s: string) => {
    const m: Record<string, string> = {
      queued: 'bg-blue-500/20 text-blue-400',
      running: 'bg-green-500/20 text-green-400',
      completed: 'bg-slate-700 text-slate-300',
      failed: 'bg-red-500/20 text-red-400',
    };
    return m[s] || 'bg-slate-600 text-white';
  };

  const fmtTime = (iso: string) => {
    try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }); } catch { return iso; }
  };

  const formatTokens = (n: number) => n >= 1000 ? (n / 1000).toFixed(1) + 'K' : n.toString();

  const getActionStyle = (action: string) => {
    if (action.startsWith('Target ')) {
      const val = parseInt(action.replace('Target ', '').replace('%', ''));
      if (!isNaN(val)) {
        if (val > 0) return 'bg-green-500/20 text-green-400 border-green-500/30';
        if (val < 0) return 'bg-red-500/20 text-red-400 border-red-500/30';
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      }
    }
    return actionColor[action] ?? 'bg-slate-600 text-white border-slate-500';
  };

  const totalStats = history.reduce((acc, curr) => {
    if (curr.stats) {
      acc.calls += curr.stats.llm_calls || 0;
      acc.in += curr.stats.tokens_in || 0;
      acc.out += curr.stats.tokens_out || 0;
      acc.tools += curr.stats.tool_calls || 0;
    }
    return acc;
  }, { calls: 0, in: 0, out: 0, tools: 0 });

  // ── Render ──────────────────────────────────
  return (
    <div className="max-w-[1600px] mx-auto space-y-6">
      {/* Report modal */}
      {viewingReport && (
        <ReportModal
          runId={wallet.id}
          historyId={viewingReport.id}
          taskId={viewingReport.taskId}
          ticker={viewingReport.ticker}
          isFailed={viewingReport.isFailed}
          isRunning={viewingReport.isRunning}
          onClose={() => setViewingReport(null)}
        />
      )}

      {/* ── Header ────────────────────────────── */}
      <div className="flex items-center gap-4 p-5 bg-slate-900 border border-slate-700 rounded-2xl shadow-xl">
        <button onClick={onBack} className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors border border-slate-600 shrink-0">← Back</button>
        <h1 className="text-3xl font-bold text-white truncate max-w-md">{wallet.wallet_name}</h1>
        {isReal ? (
          <span className="px-4 py-2 bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg font-bold text-xl tracking-wider animate-pulse shadow-[0_0_15px_rgba(239,68,68,0.5)]">REAL</span>
        ) : wallet.account_type === 'PAPER' ? (
          <span className="px-4 py-2 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-lg font-bold text-xl tracking-wider">PAPER</span>
        ) : (
          <span className="px-4 py-2 bg-slate-600 text-white border border-slate-500 rounded-lg font-bold">{wallet.account_type}</span>
        )}
        {account && <span className="text-slate-400 text-sm font-mono">#{account.account_number}</span>}

        {/* Server time */}
        {serverTime && (
          <span className="text-slate-500 text-xs font-mono ml-2" title="Server UTC time">
            🕐 {fmtTime(serverTime)} UTC
          </span>
        )}

        <button onClick={() => { fetchAccount(); fetchPositions(); fetchTasks(); fetchHistory(); }}
          className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg transition-colors border border-slate-600 text-sm" title="Refresh">↻</button>

        {/* Delete */}
        <div className="ml-auto pl-5 border-l border-slate-700 flex items-center">
          {isDeleting ? (
            <div className="flex items-center gap-3">
              <span className="text-red-400 font-bold">Are you sure?</span>
              <button onClick={handleConfirmDelete} className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg font-bold transition-colors">Yes, Delete</button>
              <button onClick={() => setIsDeleting(false)} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors">Cancel</button>
            </div>
          ) : (
            <button onClick={() => setIsDeleting(true)} className="px-4 py-2 bg-slate-800 hover:bg-red-900/40 hover:text-red-400 hover:border-red-500/40 text-slate-400 rounded-lg transition-colors border border-slate-600">Delete Wallet</button>
          )}
        </div>
      </div>

      {/* ── Grid: 3 + 5 + 4 ──────────────────── */}
      <div className="grid grid-cols-12 gap-6" style={{ minHeight: 'calc(100vh - 220px)' }}>

        {/* LEFT col */}
        <div className="col-span-3 flex flex-col gap-6">
          {/* Balance */}
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 shadow-lg">
            <h2 className="text-base font-semibold text-white border-b border-slate-700 pb-2 mb-4">Account Balance</h2>
            {accountLoading ? <Spinner /> : accountError ? <Err msg={accountError} /> : account && (
              <div className="space-y-3">
                <div>
                  <p className="text-slate-400 text-xs uppercase">Portfolio Value</p>
                  <p className="text-2xl font-bold text-white">${fmt(account.portfolio_value)}</p>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><p className="text-slate-400 text-xs uppercase">Equity</p><p className="text-lg font-bold text-green-400">${fmt(account.equity)}</p></div>
                  <div><p className="text-slate-400 text-xs uppercase">Cash</p><p className="text-lg font-semibold text-slate-200">${fmt(account.cash)}</p></div>
                  <div className="col-span-2"><p className="text-slate-400 text-xs uppercase">Buying Power</p><p className="text-lg font-semibold text-slate-200">${fmt(account.buying_power)}</p></div>
                </div>
                <div className="pt-2 border-t border-slate-700 flex justify-between items-center">
                  <span className="text-slate-400 text-xs">{account.currency}</span>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${account.status === 'ACTIVE' ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>{account.status}</span>
                </div>
              </div>
            )}
          </div>

          {/* Env */}
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 shadow-lg">
            <h2 className="text-base font-semibold text-white border-b border-slate-700 pb-2 mb-4">Environment</h2>
            <div className="space-y-3">
              <div><p className="text-slate-400 text-xs uppercase">Config</p><p className="text-white font-mono text-xs bg-black p-2 rounded border border-slate-700 mt-1 break-all">{wallet.config_file}</p></div>
              <div><p className="text-slate-400 text-xs uppercase">Env File</p><p className="text-white font-mono text-xs bg-black p-2 rounded border border-slate-700 mt-1 break-all">{wallet.env_file}</p></div>
            </div>
          </div>

          {/* Positions */}
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 shadow-lg flex flex-col flex-grow">
            <div className="flex justify-between items-center border-b border-slate-700 pb-2 mb-4">
              <h2 className="text-base font-semibold text-white">Open Positions</h2>
              {!positionsLoading && !positionsError && <span className="text-sm bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-bold">{positions.length}</span>}
            </div>
            {positionsLoading ? <Spinner /> : positionsError ? <Err msg={positionsError} /> : (
              <div className="flex-grow overflow-y-auto space-y-3 pr-1">
                {positions.length === 0 ? <div className="text-center py-6 text-slate-400 text-sm">No open positions.</div> : positions.map(pos => (
                  <div key={pos.symbol} className="p-3 bg-black border border-slate-700 rounded-lg">
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-lg font-bold text-white">{pos.symbol}</span>
                      {pos.unrealized_pl !== null && <span className={`font-bold text-sm ${plColor(pos.unrealized_pl)}`}>{pos.unrealized_pl >= 0 ? '+' : ''}{fmt(pos.unrealized_pl)}</span>}
                    </div>
                    <div className="grid grid-cols-2 gap-1.5 text-xs">
                      <div><span className="text-slate-500 uppercase">Qty</span><p className="text-slate-200">{pos.qty}</p></div>
                      <div className="text-right"><span className="text-slate-500 uppercase">Entry</span><p className="text-slate-200">${fmt(pos.avg_entry_price)}</p></div>
                      {pos.current_price !== null && (<><div><span className="text-slate-500 uppercase">Price</span><p className="text-slate-200">${fmt(pos.current_price)}</p></div>
                      {pos.unrealized_plpc !== null && <div className="text-right"><span className="text-slate-500 uppercase">P&L %</span><p className={plColor(pos.unrealized_plpc)}>{pos.unrealized_plpc >= 0 ? '+' : ''}{(pos.unrealized_plpc * 100).toFixed(2)}%</p></div>}</>)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* CENTER: Agent Dashboard */}
        <div className="col-span-5 bg-slate-900 border border-slate-700 rounded-xl p-6 shadow-lg flex flex-col">
          <div className="flex justify-between items-center border-b border-slate-700 pb-2 mb-5">
            <h2 className="text-xl font-semibold text-white">Agent Dashboard</h2>
            <span className="text-sm bg-accent/20 text-accent px-3 py-1 rounded-full font-bold">{tasks.length} Tasks</span>
          </div>

          <TaskForm walletId={wallet.id} onTaskAdded={fetchTasks} />

          {/* Task list */}
          <div className="flex-grow overflow-y-auto space-y-2.5 pr-1">
            {tasks.map(task => (
              <div key={task.id} 
                onClick={() => {
                  if (task.status === 'running') setViewingReport({ id: '', ticker: task.ticker, taskId: task.id, isRunning: true });
                  else if (task.status === 'completed') setViewingReport({ id: '', ticker: task.ticker, taskId: task.id, isFailed: false });
                  else if (task.status === 'failed') setViewingReport({ id: '', ticker: task.ticker, taskId: task.id, isFailed: true });
                }}
                className={`p-4 bg-slate-800 border rounded-lg transition-all flex justify-between items-center group ${
                  task.status === 'running' ? 'cursor-pointer border-blue-500/30 hover:border-blue-400 shadow-[0_0_10px_rgba(59,130,246,0.1)]' : 
                  task.status === 'queued' ? 'border-slate-700 hover:border-slate-500' :
                  'cursor-pointer border-slate-700 hover:border-slate-500'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="text-white font-bold font-mono">{task.ticker}</span>
                  {task.scheduled_at && <span className="text-slate-500 text-xs">⏱ {fmtTime(task.scheduled_at)}</span>}
                  {task.recurrence && <span className="text-blue-400 text-xs bg-blue-500/10 px-1.5 py-0.5 rounded">↻ {task.recurrence}</span>}
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-3">
                  <span className={`px-2 py-1 text-xs font-bold rounded flex items-center ${statusBadge(task.status)}`}>
                    {task.status === 'running' && <span className="w-2 h-2 rounded-full bg-green-500 mr-1.5 animate-pulse" />}
                    {task.status}
                  </span>
                  {task.decision && <span className="text-xs text-accent font-bold">{task.decision}</span>}
                  {task.status === 'queued' && (
                    <button onClick={(e) => { e.stopPropagation(); handleRemoveTask(task.id); }} className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-500/20 rounded transition-colors" title="Remove">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            ))}
            {tasks.length === 0 && <div className="text-center py-10 text-slate-500">No tasks queued. Add a ticker above.</div>}
          </div>
        </div>

        {/* RIGHT: Decision History */}
        <div className="col-span-4 bg-slate-900 border border-slate-700 rounded-xl p-6 shadow-lg flex flex-col">
          <div className="flex flex-col border-b border-slate-700 pb-4 mb-5 space-y-3">
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-semibold text-white">Decision History</h2>
              <span className="text-xs text-slate-500 font-medium">Click for report</span>
            </div>
            {history.length > 0 && (
              <div className="flex gap-4 text-xs font-mono text-slate-400 bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/50">
                <span title="Total LLM Calls">🧠 {totalStats.calls}</span>
                <span title="Total Input Tokens">📥 {formatTokens(totalStats.in)}</span>
                <span title="Total Output Tokens">📤 {formatTokens(totalStats.out)}</span>
                <span title="Total Tool Executions">🛠 {totalStats.tools}</span>
              </div>
            )}
          </div>
          <div className="flex-grow overflow-y-auto space-y-2.5 pr-1">
            {history.length === 0 ? (
              <div className="text-center py-10 text-slate-500 text-sm">No decisions yet. Queue a task to get started.</div>
            ) : history.map(d => (
              <div key={d.id}
                onClick={() => setViewingReport({ id: d.id, ticker: d.ticker, taskId: d.task_id, isFailed: d.action === 'FAILED' })}
                className={`p-4 border rounded-lg cursor-pointer hover:border-slate-500 transition-all ${
                  d.action === 'FAILED' ? 'bg-red-950/30 border-red-500/30' : 'bg-slate-800 border-slate-700'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className={`px-2 py-0.5 text-xs font-bold rounded border ${getActionStyle(d.action)}`}>{d.action}</span>
                  <span className="text-white font-bold">{d.ticker}</span>
                  <span className="text-slate-500 text-xs ml-auto">{fmtTime(d.timestamp)}</span>
                </div>
                {d.action === 'FAILED' && (
                  <p className="mt-2 text-xs leading-relaxed line-clamp-2 text-red-400">{d.rationale}</p>
                )}
                {d.stats && (
                  <div className="mt-3 flex gap-4 text-[10px] text-slate-500 font-mono border-t border-slate-700/50 pt-2">
                    <span title="LLM Calls">🧠 {d.stats.llm_calls || 0}</span>
                    <span title="Input Tokens">📥 {formatTokens(d.stats.tokens_in || 0)}</span>
                    <span title="Output Tokens">📤 {formatTokens(d.stats.tokens_out || 0)}</span>
                    <span title="Tool Executions">🛠 {d.stats.tool_calls || 0}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
