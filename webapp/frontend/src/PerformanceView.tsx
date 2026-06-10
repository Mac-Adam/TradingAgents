import { useState, useEffect, useRef } from 'react';
import type { Run } from './types';

const API = 'http://localhost:8000';

interface PerformanceViewProps {
  runs: Run[];
}

interface ChartPoint {
  date: string;
  [key: string]: any;
}

interface ChartLine {
  id: string;
  key: string;
  color: string;
  label: string;
  dashed?: boolean;
  isPnL?: boolean;
}

export default function PerformanceView({ runs }: PerformanceViewProps) {
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [timeframe, setTimeframe] = useState<'7d' | '30d' | '90d' | 'all'>('all');
  const [benchmarks, setBenchmarks] = useState<Set<string>>(new Set(['SPY']));
  const [showBuyAndHold, setShowBuyAndHold] = useState(true);
  
  // Stock-specific drilldown states
  const [selectedTicker, setSelectedTicker] = useState<string>('');
  const [selectedStockRunId, setSelectedStockRunId] = useState<string>('');

  // Correlation analysis states
  const [selectedHorizon, setSelectedHorizon] = useState<'1d' | '3d' | '5d' | '10d' | '30d'>('5d');
  const [selectedCorrelationModel, setSelectedCorrelationModel] = useState<string>('');

  const [performanceData, setPerformanceData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initialize: select the first two runs if available
  useEffect(() => {
    if (runs.length > 0 && selectedRunIds.size === 0) {
      const initial = new Set<string>();
      initial.add(runs[0].id);
      if (runs.length > 1) {
        initial.add(runs[1].id);
      }
      setSelectedRunIds(initial);
    }
  }, [runs, selectedRunIds]);

  // Fetch performance data from backend
  useEffect(() => {
    if (selectedRunIds.size === 0) {
      setPerformanceData(null);
      return;
    }
    setLoading(true);
    setError(null);

    const runIdsParam = Array.from(selectedRunIds).join(',');
    const benchmarkParam = Array.from(benchmarks).join(',');
    
    let startDateParam = '';
    const now = new Date();
    if (timeframe === '7d') {
      const d = new Date();
      d.setDate(now.getDate() - 7);
      startDateParam = d.toISOString().split('T')[0];
    } else if (timeframe === '30d') {
      const d = new Date();
      d.setDate(now.getDate() - 30);
      startDateParam = d.toISOString().split('T')[0];
    } else if (timeframe === '90d') {
      const d = new Date();
      d.setDate(now.getDate() - 90);
      startDateParam = d.toISOString().split('T')[0];
    }

    const url = `${API}/api/performance?run_ids=${runIdsParam}&benchmarks=${benchmarkParam}${startDateParam ? `&start_date=${startDateParam}` : ''}`;

    fetch(url)
      .then(res => {
        if (!res.ok) throw new Error('Failed to load performance metrics');
        return res.json();
      })
      .then(data => {
        setPerformanceData(data);
        
        // Resolve tickers and default selectors
        const allTickers: string[] = [];
        Object.keys(data.runs).forEach(runId => {
          if (data.runs[runId]?.stocks) {
            allTickers.push(...Object.keys(data.runs[runId].stocks));
          }
        });
        const uniqueTickers = Array.from(new Set(allTickers));

        if (uniqueTickers.length > 0) {
          let ticker = selectedTicker;
          if (!uniqueTickers.includes(selectedTicker)) {
            ticker = uniqueTickers[0];
            setSelectedTicker(ticker);
          }

          // Resolve runs that traded this ticker
          const validRunIds = Array.from(selectedRunIds).filter(runId => 
            data.runs[runId]?.stocks && data.runs[runId].stocks[ticker]
          );
          if (validRunIds.length > 0 && !validRunIds.includes(selectedStockRunId)) {
            setSelectedStockRunId(validRunIds[0]);
          }
        }
      })
      .catch(err => {
        setError(err.message);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [selectedRunIds, timeframe, benchmarks]);

  // Handle auto run update when selectedTicker changes
  useEffect(() => {
    if (performanceData && selectedTicker) {
      const validRunIds = Array.from(selectedRunIds).filter(runId => 
        performanceData.runs[runId]?.stocks && performanceData.runs[runId].stocks[selectedTicker]
      );
      if (validRunIds.length > 0 && !validRunIds.includes(selectedStockRunId)) {
        setSelectedStockRunId(validRunIds[0]);
      }
    }
  }, [selectedTicker, performanceData]);

  // Reset correlation model filter if the model is no longer in selected runs
  useEffect(() => {
    const validModels = getUniqueModelsForSelectedRuns();
    if (selectedCorrelationModel && !validModels.includes(selectedCorrelationModel)) {
      setSelectedCorrelationModel('');
    }
  }, [selectedRunIds]);

  const toggleRun = (runId: string) => {
    const next = new Set(selectedRunIds);
    if (next.has(runId)) {
      if (next.size > 1) next.delete(runId);
    } else {
      next.add(runId);
    }
    setSelectedRunIds(next);
  };

  const toggleBenchmark = (sym: string) => {
    const next = new Set(benchmarks);
    if (next.has(sym)) {
      next.delete(sym);
    } else {
      next.add(sym);
    }
    setBenchmarks(next);
  };

  const getRunColor = (index: number) => {
    const colors = ['#10b981', '#06b6d4', '#a855f7', '#ec4899', '#3b82f6'];
    return colors[index % colors.length];
  };

  // Build main time-series chart data
  const buildMainChartData = () => {
    if (!performanceData || !performanceData.timeline) return { points: [], lines: [] };

    const { timeline, runs: apiRuns, benchmarks: apiBenchmarks } = performanceData;
    const points: ChartPoint[] = timeline.map((date: string) => ({ date }));
    const lines: ChartLine[] = [];

    Array.from(selectedRunIds).forEach((runId, i) => {
      const runRes = apiRuns[runId];
      if (!runRes) return;
      const color = getRunColor(i);

      lines.push({
        id: runId,
        key: `${runId}_active`,
        color,
        label: `${runRes.wallet_name} (Active)`
      });

      if (showBuyAndHold) {
        lines.push({
          id: `${runId}_bh`,
          key: `${runId}_bh`,
          color,
          label: `${runRes.wallet_name} (Buy & Hold)`,
          dashed: true
        });
      }

      runRes.series.forEach((dp: any) => {
        const pt = points.find(p => p.date === dp.date);
        if (pt) pt[`${runId}_active`] = dp.return_pct;
      });

      if (showBuyAndHold && runRes.buy_and_hold_series) {
        runRes.buy_and_hold_series.forEach((dp: any) => {
          const pt = points.find(p => p.date === dp.date);
          if (pt) pt[`${runId}_bh`] = dp.return_pct;
        });
      }
    });

    Array.from(benchmarks).forEach((bench) => {
      const benchRes = apiBenchmarks[bench];
      if (!benchRes) return;

      const colors: Record<string, string> = { SPY: '#f59e0b', QQQ: '#f97316' };
      lines.push({
        id: bench,
        key: `${bench}_index`,
        color: colors[bench] || '#94a3b8',
        label: `${bench} Benchmark`
      });

      benchRes.forEach((dp: any) => {
        const pt = points.find(p => p.date === dp.date);
        if (pt) pt[`${bench}_index`] = dp.return_pct;
      });
    });

    return { points, lines };
  };

  // Build stock specific chart data (now per model selection)
  const buildStockChartData = () => {
    if (!performanceData || !selectedTicker || !selectedStockRunId) return { points: [], lines: [] };

    const runRes = performanceData.runs[selectedStockRunId];
    if (!runRes || !runRes.stocks) return { points: [], lines: [] };

    const stockData = runRes.stocks[selectedTicker];
    if (!stockData) return { points: [], lines: [] };

    const points: ChartPoint[] = stockData.map((dp: any) => ({
      date: dp.date,
      model_pnl: dp.model_pnl,
      bh_pnl: dp.bh_pnl,
      price: dp.stock_price
    }));

    const lines: ChartLine[] = [
      { id: 'model_pnl', key: 'model_pnl', color: '#10b981', label: 'Model Cumulative P&L ($)', isPnL: true },
      { id: 'bh_pnl', key: 'bh_pnl', color: '#f59e0b', label: 'Buy & Hold P&L ($)', dashed: true, isPnL: true }
    ];

    return { points, lines };
  };

  // Helper to format config file name to readable model name
  const formatModelName = (configFile: string) => {
    if (!configFile) return 'Unknown Model';
    let name = configFile.replace(/\.json$/i, '');
    name = name.replace(/[_-]/g, ' ');
    if (name.toLowerCase() === 'default') return 'Default LLM';
    if (name.toLowerCase().includes('gemma4 31b')) return 'Gemma 4 (31B)';
    if (name.toLowerCase().includes('gemma4 32k')) return 'Gemma 4 (32k)';
    if (name.toLowerCase().includes('qwen3.5 32k')) return 'Qwen 3.5 (32k)';
    return name.split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  };

  // Get unique models (config files) for selected runs
  const getUniqueModelsForSelectedRuns = () => {
    const models = new Set<string>();
    Array.from(selectedRunIds).forEach(runId => {
      const run = runs.find(r => r.id === runId);
      if (run && run.config_file) {
        models.add(run.config_file);
      }
    });
    return Array.from(models);
  };

  const { points: mainPoints, lines: mainLines } = buildMainChartData();
  const { points: stockPoints, lines: stockLines } = buildStockChartData();

  // Filter scatter data based on selected correlation model and horizon
  const getFilteredScatterData = () => {
    if (!performanceData || !performanceData.scatter_data) return [];
    return performanceData.scatter_data.filter((item: any) => {
      const run = runs.find(r => r.id === item.run_id);
      const matchesModel = !selectedCorrelationModel || (run && run.config_file === selectedCorrelationModel);
      const matchesSelectedRun = selectedRunIds.has(item.run_id);
      return matchesSelectedRun && matchesModel && item.returns[selectedHorizon] !== undefined;
    });
  };

  const filteredScatterPoints = getFilteredScatterData();

  // Find all unique tickers across selected runs
  const getUniqueTickers = () => {
    if (!performanceData) return [];
    const all: string[] = [];
    Object.keys(performanceData.runs).forEach(runId => {
      if (performanceData.runs[runId]?.stocks) {
        all.push(...Object.keys(performanceData.runs[runId].stocks));
      }
    });
    return Array.from(new Set(all));
  };

  // Find valid runs for the selected ticker
  const getValidRunsForTicker = () => {
    if (!performanceData || !selectedTicker) return [];
    return runs.filter(run => 
      performanceData.runs[run.id]?.stocks && performanceData.runs[run.id].stocks[selectedTicker]
    );
  };

  return (
    <div className="space-y-6 w-full pb-12">
      {/* Page Header */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-700 shadow-xl flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-accent to-purple-400 bg-clip-text text-transparent pb-1 leading-normal mb-1">
            Performance & Portfolio Analytics
          </h1>
          <p className="text-slate-300 text-sm">
            Audit portfolio value trajectories, compare against index benchmarks, and analyze agent decision signal accuracy.
          </p>
        </div>
      </div>

      {/* Control Panel & Horizontal Tools */}
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex flex-wrap items-center gap-6 justify-between">
          {/* Wallet Selection Toggles */}
          <div className="flex flex-col space-y-1.5 min-w-[250px]">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Select Wallets</span>
            <div className="flex flex-wrap gap-2">
              {runs.map((run, i) => (
                <button
                  key={run.id}
                  onClick={() => toggleRun(run.id)}
                  className={`px-3 py-1.5 rounded-lg border text-xs font-bold flex items-center space-x-2 transition-all cursor-pointer ${
                    selectedRunIds.has(run.id)
                      ? 'bg-slate-800 border-slate-650 text-white'
                      : 'bg-black border-slate-850 hover:border-slate-700 text-slate-400'
                  }`}
                >
                  <span 
                    className="w-2.5 h-2.5 rounded-full" 
                    style={{ backgroundColor: selectedRunIds.has(run.id) ? getRunColor(i) : 'transparent', border: '1px solid #555' }}
                  />
                  <span>{run.wallet_name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Timeframe Buttons */}
          <div className="flex flex-col space-y-1.5">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Timeframe</span>
            <div className="flex bg-black p-1 rounded-lg border border-slate-850">
              {(['7d', '30d', '90d', 'all'] as const).map(tf => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={`px-4 py-1 text-xs font-semibold rounded-md uppercase transition-all cursor-pointer ${
                    timeframe === tf 
                      ? 'bg-accent text-white font-bold' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>

          {/* Benchmarks Selector */}
          <div className="flex flex-col space-y-1.5">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Benchmarks</span>
            <div className="flex bg-black p-1 rounded-lg border border-slate-850">
              {['SPY', 'QQQ'].map(sym => (
                <button
                  key={sym}
                  onClick={() => toggleBenchmark(sym)}
                  className={`px-4 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                    benchmarks.has(sym)
                      ? 'bg-slate-800 text-white font-bold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>

          {/* Buy & Hold Switch */}
          <div className="flex flex-col space-y-1.5">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Options</span>
            <label className="flex items-center space-x-2.5 cursor-pointer bg-black px-4 py-2.5 rounded-lg border border-slate-850 hover:border-slate-700">
              <input 
                type="checkbox"
                checked={showBuyAndHold}
                onChange={e => setShowBuyAndHold(e.target.checked)}
                className="rounded border-slate-700 bg-black text-accent focus:ring-accent"
              />
              <span className="text-slate-300 text-xs font-semibold">Overlay Buy & Hold</span>
            </label>
          </div>
        </div>
      </div>

      {/* Main Performance Chart: Full Width */}
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 shadow-lg flex flex-col w-full">
        <div className="flex justify-between items-center mb-4 border-b border-slate-800 pb-3">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <span>Cumulative Returns (%)</span>
            {loading && <div className="w-4 h-4 border-2 border-accent border-t-transparent animate-spin rounded-full" />}
          </h2>
          <span className="text-xs text-slate-500 font-medium">Hover chart to inspect details</span>
        </div>

        {error && (
          <div className="text-red-400 text-center py-24 bg-red-950/20 border border-red-900/30 rounded-lg">
            <p className="font-bold">Error loading chart data</p>
            <p className="text-sm">{error}</p>
          </div>
        )}

        {!error && mainPoints.length === 0 && !loading && (
          <div className="text-slate-400 text-center py-28">
            Select one or more wallets above to load performance charts.
          </div>
        )}

        {!error && mainPoints.length > 0 && (
          <div style={{ height: '58vh', minHeight: '480px' }} className="relative w-full">
            <LineChart data={mainPoints} lines={mainLines} />
          </div>
        )}

        {/* Chart Legend */}
        {mainLines.length > 0 && (
          <div className="flex flex-wrap gap-4 mt-5 p-3.5 bg-slate-950/40 rounded-lg border border-slate-850 text-xs">
            {mainLines.map(line => (
              <div key={line.key} className="flex items-center space-x-2">
                <span 
                  className={`w-3.5 h-1.5 rounded-full inline-block ${line.dashed ? 'border-b-2 border-dashed' : ''}`}
                  style={{ borderBottomColor: line.dashed ? line.color : 'transparent', backgroundColor: line.dashed ? 'transparent' : line.color }}
                />
                <span className="text-slate-300 font-medium">{line.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Grid: Stock Drift + Correlation Scatter */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 w-full">

        {/* Panel 1: Per-Stock Analysis (Per Model) */}
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 shadow-lg flex flex-col justify-between">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-3 mb-4 gap-3">
            <h3 className="text-lg font-bold text-white">Stock Performance vs Model</h3>
            
            <div className="flex gap-3">
              {/* Ticker Selector */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Stock:</span>
                <select
                  value={selectedTicker}
                  onChange={e => setSelectedTicker(e.target.value)}
                  className="bg-black border border-slate-700 rounded-lg p-1 text-xs text-white font-bold outline-none focus:border-accent"
                >
                  {getUniqueTickers().map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              {/* Run/Model Selector */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Model:</span>
                <select
                  value={selectedStockRunId}
                  onChange={e => setSelectedStockRunId(e.target.value)}
                  className="bg-black border border-slate-700 rounded-lg p-1 text-xs text-white font-bold outline-none focus:border-accent"
                >
                  {getValidRunsForTicker().map(run => (
                    <option key={run.id} value={run.id}>
                      {run.wallet_name} ({formatModelName(run.config_file)})
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {!selectedTicker ? (
            <div className="text-slate-500 text-center py-20 text-sm">No ticker data available.</div>
          ) : (
            <div className="space-y-4 flex-grow flex flex-col justify-between">
              {/* Return stats cards */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <span className="text-slate-400 text-[10px] uppercase font-medium">Model Profit</span>
                  <h4 className={`text-lg font-bold font-mono mt-0.5 ${
                    stockPoints.length > 0 && stockPoints[stockPoints.length - 1].model_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {stockPoints.length > 0 ? (
                      `$${stockPoints[stockPoints.length - 1].model_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                    ) : '$0.00'}
                  </h4>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <span className="text-slate-400 text-[10px] uppercase font-medium">Buy & Hold Profit</span>
                  <h4 className={`text-lg font-bold font-mono mt-0.5 ${
                    stockPoints.length > 0 && stockPoints[stockPoints.length - 1].bh_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {stockPoints.length > 0 ? (
                      `$${stockPoints[stockPoints.length - 1].bh_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                    ) : '$0.00'}
                  </h4>
                </div>
              </div>

              {/* Single Stock P&L chart */}
              {stockPoints.length > 0 && (
                <div style={{ height: '35vh', minHeight: '260px' }} className="relative w-full">
                  <LineChart data={stockPoints} lines={stockLines} />
                </div>
              )}

              {/* Transactions Ledger */}
              {selectedTicker && selectedStockRunId && performanceData?.ledger && (
                <div className="border-t border-slate-800 pt-3 flex-grow">
                  <h4 className="text-xs font-bold text-white mb-2">Trades Ledger ({selectedTicker})</h4>
                  <div className="overflow-x-auto max-h-[140px] overflow-y-auto pr-1 border border-slate-800 rounded-lg">
                    <table className="w-full text-xs text-left text-slate-200">
                      <thead className="bg-slate-800/80 text-slate-200 uppercase font-bold text-[9px] border-b border-slate-700 sticky top-0">
                        <tr>
                          <th className="p-2 text-slate-200">Date</th>
                          <th className="p-2 text-slate-200">Action</th>
                          <th className="p-2 text-right text-slate-200">Shares</th>
                          <th className="p-2 text-right text-slate-200">Price</th>
                          <th className="p-2 text-right text-slate-200">Total ($)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {performanceData.ledger
                          .filter((trade: any) => trade.run_id === selectedStockRunId && trade.ticker === selectedTicker)
                          .map((trade: any) => {
                            const totalCost = Math.abs(trade.qty) * (trade.execution_price ?? trade.estimated_price);
                            const isBuy = trade.action === 'BUY';
                            return (
                              <tr key={trade.id} className="border-b border-slate-850 hover:bg-slate-800/40">
                                <td className="p-2 font-mono text-slate-200">{new Date(trade.timestamp).toLocaleDateString()}</td>
                                <td className="p-2">
                                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                                    isBuy ? 'bg-green-500/20 text-green-450' : 'bg-red-500/20 text-red-450'
                                  }`}>
                                    {trade.action}
                                  </span>
                                </td>
                                <td className="p-2 text-right font-mono text-slate-200">{Math.abs(trade.qty)}</td>
                                <td className="p-2 text-right font-mono text-slate-200">${(trade.execution_price ?? trade.estimated_price).toFixed(2)}</td>
                                <td className="p-2 text-right font-mono text-slate-200">${totalCost.toFixed(2)}</td>
                              </tr>
                            );
                          })
                        }
                        {performanceData.ledger.filter((trade: any) => trade.run_id === selectedStockRunId && trade.ticker === selectedTicker).length === 0 && (
                          <tr>
                            <td colSpan={5} className="p-4 text-center text-slate-400">No trades executed for this ticker and model.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Panel 2: Signal Correlation & Scatter Plot */}
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 shadow-lg flex flex-col justify-between">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-3 mb-4 gap-3">
            <h3 className="text-lg font-bold text-white">Signal vs Returns Correlation</h3>
            
            <div className="flex flex-wrap items-center gap-3">
              {/* Model Selector for Correlation */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Model:</span>
                <select
                  value={selectedCorrelationModel}
                  onChange={e => setSelectedCorrelationModel(e.target.value)}
                  className="bg-black border border-slate-700 rounded-lg p-1.5 text-xs text-white font-bold outline-none focus:border-accent"
                >
                  <option value="">All Models</option>
                  {getUniqueModelsForSelectedRuns().map(modelConfig => (
                    <option key={modelConfig} value={modelConfig}>
                      {formatModelName(modelConfig)}
                    </option>
                  ))}
                </select>
              </div>

              {/* Horizon Selection */}
              <div className="flex bg-black p-1 rounded-lg border border-slate-850">
                {(['1d', '3d', '5d', '10d', '30d'] as const).map(h => (
                  <button
                    key={h}
                    onClick={() => setSelectedHorizon(h)}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                      selectedHorizon === h
                        ? 'bg-accent text-white font-bold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {h}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {!performanceData || !performanceData.scatter_data || performanceData.scatter_data.length === 0 ? (
            <div className="text-slate-500 text-center py-20 text-sm">
              Not enough signal data. Run tasks to populate correlation plots.
            </div>
          ) : (
            <div className="space-y-4 flex-grow flex flex-col justify-between">
              {/* Stats & Pearson summary */}
              {(() => {
                const points = filteredScatterPoints.map((item: any) => ({
                  x: item.grade,
                  y: item.returns[selectedHorizon]
                }));

                const r = calculateCorrelation(points);
                const rText = getCorrelationText(r);

                return (
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 flex justify-between items-center">
                    <div>
                      <span className="text-slate-400 text-[10px] uppercase font-medium">Pearson Correlation (r)</span>
                      <h4 className="text-lg font-mono font-bold text-white mt-0.5">
                        {r.toFixed(3)}
                      </h4>
                    </div>
                    <div className="text-right">
                      <span className="text-slate-400 text-[10px] uppercase font-medium">Strength</span>
                      <p className={`text-xs font-bold mt-1 ${
                        Math.abs(r) >= 0.4 ? 'text-purple-400' : Math.abs(r) >= 0.2 ? 'text-blue-400' : 'text-slate-400'
                      }`}>
                        {rText}
                      </p>
                    </div>
                  </div>
                );
              })()}

              {/* Scatter Plot Chart */}
              <div style={{ height: '38vh', minHeight: '300px' }} className="w-full relative">
                <ScatterPlot 
                  data={filteredScatterPoints} 
                  horizon={selectedHorizon} 
                  runs={runs}
                  formatModelName={formatModelName}
                />
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

// ── Pearson Correlation Math ──────────────────────────────
function calculateCorrelation(points: { x: number; y: number }[]) {
  if (points.length < 2) return 0;
  const n = points.length;
  const sumX = points.reduce((acc, p) => acc + p.x, 0);
  const sumY = points.reduce((acc, p) => acc + p.y, 0);
  const sumXY = points.reduce((acc, p) => acc + p.x * p.y, 0);
  const sumX2 = points.reduce((acc, p) => acc + p.x * p.x, 0);
  const sumY2 = points.reduce((acc, p) => acc + p.y * p.y, 0);

  const num = n * sumXY - sumX * sumY;
  const den = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
  if (den === 0) return 0;
  return num / den;
}

function getCorrelationText(r: number): string {
  const absR = Math.abs(r);
  let direction = r >= 0 ? "Positive" : "Negative";
  if (absR < 0.1) return "No Linear Correlation";
  if (absR < 0.3) return `Weak ${direction}`;
  if (absR < 0.5) return `Moderate ${direction}`;
  return `Strong ${direction}`;
}

// ── Scatter Plot custom SVG Component ──────────────────────────────
interface ScatterPlotProps {
  data: any[];
  horizon: string;
  runs: Run[];
  formatModelName: (configFile: string) => string;
}

function ScatterPlot({ data, horizon, runs, formatModelName }: ScatterPlotProps) {
  const [hoveredPoint, setHoveredPoint] = useState<any | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number; containerWidth: number; containerHeight: number } | null>(null);
  const containerRef = useRef<SVGSVGElement | null>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 300 });

  useEffect(() => {
    if (!containerRef.current) return;
    const resizeObserver = new ResizeObserver(() => {
      const parent = containerRef.current?.parentElement;
      if (parent) {
        setDimensions({
          width: parent.clientWidth,
          height: parent.clientHeight
        });
      }
    });
    const parent = containerRef.current.parentElement;
    if (parent) {
      resizeObserver.observe(parent);
      setDimensions({
        width: parent.clientWidth,
        height: parent.clientHeight
      });
    }
    return () => resizeObserver.disconnect();
  }, []);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement, MouseEvent>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setMousePos({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      containerWidth: rect.width,
      containerHeight: rect.height
    });
  };

  // Filter valid items
  const validItems = data.filter(item => item.returns[horizon] !== undefined);
  if (validItems.length === 0) return null;

  const { width, height } = dimensions;
  const margin = { top: 20, right: 30, bottom: 40, left: 50 };

  const grades = validItems.map(item => item.grade);
  let minX = Math.min(...grades, -3);
  let maxX = Math.max(...grades, 5);
  
  const returns = validItems.map(item => item.returns[horizon]);
  let minY = Math.min(...returns, -5);
  let maxY = Math.max(...returns, 5);
  
  const yDelta = maxY - minY || 1.0;
  minY -= yDelta * 0.1;
  maxY += yDelta * 0.1;

  const getX = (val: number) => {
    return margin.left + ((val - minX) / (maxX - minX)) * (width - margin.left - margin.right);
  };

  const getY = (val: number) => {
    return height - margin.bottom - ((val - minY) / (maxY - minY)) * (height - margin.top - margin.bottom);
  };

  const yTicks = [];
  for (let i = 0; i < 5; i++) {
    yTicks.push(minY + (i / 4) * (maxY - minY));
  }

  const xTicks = [];
  for (let val = Math.ceil(minX); val <= Math.floor(maxX); val++) {
    xTicks.push(val);
  }

  const points = validItems.map(item => ({ x: item.grade, y: item.returns[horizon] }));
  const n = points.length;
  const sumX = points.reduce((acc, p) => acc + p.x, 0);
  const sumY = points.reduce((acc, p) => acc + p.y, 0);
  const sumXY = points.reduce((acc, p) => acc + p.x * p.y, 0);
  const sumX2 = points.reduce((acc, p) => acc + p.x * p.x, 0);
  
  const denominator = n * sumX2 - sumX * sumX;
  const slope = denominator !== 0 ? (n * sumXY - sumX * sumY) / denominator : 0;
  const intercept = denominator !== 0 ? (sumY - slope * sumX) / n : 0;

  const trendX1 = minX;
  const trendY1 = slope * trendX1 + intercept;
  const trendX2 = maxX;
  const trendY2 = slope * trendX2 + intercept;

  return (
    <div className="w-full h-full relative">
      <svg 
        ref={containerRef}
        viewBox={`0 0 ${width} ${height}`} 
        className="w-full h-full select-none"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => {
          setHoveredPoint(null);
          setMousePos(null);
        }}
      >
        {/* Y Gridlines */}
        {yTicks.map((val, i) => {
          const y = getY(val);
          return (
            <g key={i} className="opacity-25">
              <line x1={margin.left} y1={y} x2={width - margin.right} y2={y} stroke="#475569" strokeWidth={1} />
              <text x={margin.left - 8} y={y + 3.5} fill="#94a3b8" fontSize={9} textAnchor="end" className="font-mono">
                {val.toFixed(1)}%
              </text>
            </g>
          );
        })}

        {/* X Gridlines */}
        {xTicks.map((val, i) => {
          const x = getX(val);
          return (
            <g key={i} className="opacity-25">
              <line x1={x} y1={margin.top} x2={x} y2={height - margin.bottom} stroke="#475569" strokeWidth={1} />
              <text x={x} y={height - margin.bottom + 14} fill="#94a3b8" fontSize={9} textAnchor="middle" className="font-mono">
                {val}
              </text>
            </g>
          );
        })}

        {/* Y-Axis Label */}
        <text 
          x={12} 
          y={height / 2} 
          transform={`rotate(-90 12 ${height / 2})`} 
          fill="#64748b" 
          fontSize={10} 
          textAnchor="middle"
          className="font-medium uppercase tracking-wider"
        >
          Subsequent return % ({horizon})
        </text>

        {/* X-Axis Label */}
        <text 
          x={width / 2} 
          y={height - 6} 
          fill="#64748b" 
          fontSize={10} 
          textAnchor="middle"
          className="font-medium uppercase tracking-wider"
        >
          Model Decision Grade / Target Weight
        </text>

        {/* Line of Best Fit */}
        {denominator !== 0 && (
          <line
            x1={getX(trendX1)}
            y1={getY(trendY1)}
            x2={getX(trendX2)}
            y2={getY(trendY2)}
            stroke="#a855f7"
            strokeWidth={2}
            strokeDasharray="4 4"
            className="opacity-70"
          />
        )}

        {/* Scatter Dots */}
        {validItems.map((item, i) => {
          const x = getX(item.grade);
          const y = getY(item.returns[horizon]);
          const isPositive = item.returns[horizon] >= 0;

          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r={5}
              fill={isPositive ? '#10b981' : '#f43f5e'}
              stroke="#0f172a"
              strokeWidth={1}
              className="opacity-80 hover:opacity-100 hover:scale-125 cursor-pointer transition-all duration-100"
              onMouseEnter={() => {
                setHoveredPoint(item);
              }}
              onMouseLeave={() => {
                setHoveredPoint(null);
              }}
            />
          );
        })}
      </svg>

      {/* Floating Hover Tooltip */}
      {hoveredPoint && mousePos && (
        <div 
          className="absolute bg-slate-950/95 border border-slate-700 p-2.5 rounded-lg shadow-2xl z-20 text-[10px] w-[180px] pointer-events-none transition-all duration-75 text-slate-200"
          style={{
            left: `${mousePos.x + 15 + 180 > mousePos.containerWidth ? mousePos.x - 195 : mousePos.x + 15}px`,
            top: `${mousePos.y + 15 + 100 > mousePos.containerHeight ? mousePos.y - 115 : mousePos.y + 15}px`
          }}
        >
          <div className="font-bold text-white mb-1 border-b border-slate-800 pb-1 flex justify-between">
            <span>{hoveredPoint.ticker}</span>
            <span>{hoveredPoint.date}</span>
          </div>
          <div className="space-y-0.5 text-slate-200">
            <div className="flex justify-between">
              <span className="text-slate-400">Model:</span>
              <span className="font-bold text-white font-mono">
                {(() => {
                  const run = runs.find(r => r.id === hoveredPoint.run_id);
                  return run ? formatModelName(run.config_file) : 'Unknown';
                })()}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Grade (X):</span>
              <span className="font-bold text-white font-mono">{hoveredPoint.grade} ({hoveredPoint.grade_label})</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Return (Y):</span>
              <span className={`font-bold font-mono ${hoveredPoint.returns[horizon] >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {hoveredPoint.returns[horizon] >= 0 ? '+' : ''}{hoveredPoint.returns[horizon].toFixed(2)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Custom SVG LineChart component ──────────────────────────────
interface LineChartProps {
  data: ChartPoint[];
  lines: ChartLine[];
}

function LineChart({ data, lines }: LineChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number; containerWidth: number; containerHeight: number } | null>(null);
  const containerRef = useRef<SVGSVGElement | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 400 });

  useEffect(() => {
    if (!containerRef.current) return;
    const resizeObserver = new ResizeObserver(() => {
      const parent = containerRef.current?.parentElement;
      if (parent) {
        setDimensions({
          width: parent.clientWidth,
          height: parent.clientHeight
        });
      }
    });
    const parent = containerRef.current.parentElement;
    if (parent) {
      resizeObserver.observe(parent);
      setDimensions({
        width: parent.clientWidth,
        height: parent.clientHeight
      });
    }
    return () => resizeObserver.disconnect();
  }, []);

  if (data.length === 0) return null;

  const { width, height } = dimensions;
  const margin = { top: 20, right: 20, bottom: 40, left: 50 };

  const activeKeys = lines.map(l => l.key);
  const allValues = data.flatMap(d => activeKeys.map(k => d[k]).filter(v => v !== undefined && v !== null && !isNaN(v)));
  
  let minY = Math.min(...allValues, 0);
  let maxY = Math.max(...allValues, 0);
  const delta = maxY - minY;
  const buffer = delta * 0.1 || 1.0;
  minY -= buffer;
  maxY += buffer;

  const getX = (index: number) => {
    if (data.length <= 1) return margin.left;
    return margin.left + (index / (data.length - 1)) * (width - margin.left - margin.right);
  };

  const getY = (val: number) => {
    return height - margin.bottom - ((val - minY) / (maxY - minY)) * (height - margin.top - margin.bottom);
  };

  const gridLinesY = [];
  const gridLineCount = 5;
  for (let i = 0; i < gridLineCount; i++) {
    gridLinesY.push(minY + (i / (gridLineCount - 1)) * (maxY - minY));
  }

  const gridLinesX = [];
  const gridXCount = Math.min(data.length, 5);
  for (let i = 0; i < gridXCount; i++) {
    gridLinesX.push(Math.floor((i / (gridXCount - 1)) * (data.length - 1)));
  }

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement, MouseEvent>) => {
    if (!containerRef.current) return;
    const svg = containerRef.current;
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    const chartWidth = width - margin.left - margin.right;
    const relativeX = mouseX - margin.left;
    const pct = Math.max(0, Math.min(1, relativeX / chartWidth));
    const idx = Math.round(pct * (data.length - 1));
    
    if (idx >= 0 && idx < data.length) {
      setHoverIndex(idx);
    }
    setMousePos({ x: mouseX, y: mouseY, containerWidth: rect.width, containerHeight: rect.height });
  };

  return (
    <div className="w-full h-full relative group">
      <svg
        ref={containerRef}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-full select-none"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => {
          setHoverIndex(null);
          setMousePos(null);
        }}
      >
        <defs>
          {lines.map(line => (
            <linearGradient key={line.id} id={`area-grad-${line.id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={line.color} stopOpacity="0.2" />
              <stop offset="100%" stopColor={line.color} stopOpacity="0.0" />
            </linearGradient>
          ))}
        </defs>

        {/* Y Gridlines */}
        {gridLinesY.map((val, i) => {
          const y = getY(val);
          return (
            <g key={i} className="opacity-20">
              <line x1={margin.left} y1={y} x2={width - margin.right} y2={y} stroke="#475569" strokeWidth={1} strokeDasharray="3 3" />
              <text x={margin.left - 8} y={y + 3.5} fill="#94a3b8" fontSize={9} textAnchor="end" className="font-mono">
                {lines[0]?.isPnL ? `$${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : `${val.toFixed(1)}%`}
              </text>
            </g>
          );
        })}

        {/* X Gridlines */}
        {gridLinesX.map((idx, i) => {
          const x = getX(idx);
          const dateStr = data[idx]?.date;
          return (
            <g key={i} className="opacity-20">
              <line x1={x} y1={margin.top} x2={x} y2={height - margin.bottom} stroke="#475569" strokeWidth={1} strokeDasharray="3 3" />
              <text x={x} y={height - margin.bottom + 14} fill="#94a3b8" fontSize={9} textAnchor="middle" className="font-mono">
                {dateStr ? dateStr.substring(5) : ''}
              </text>
            </g>
          );
        })}

        {/* Draw Area Paths */}
        {lines.map(line => {
          const pointsWithVals = data
            .map((d, index) => ({ x: getX(index), y: getY(d[line.key]), val: d[line.key] }))
            .filter(pt => pt.val !== undefined && pt.val !== null && !isNaN(pt.y));

          if (pointsWithVals.length === 0) return null;

          const first = pointsWithVals[0];
          const last = pointsWithVals[pointsWithVals.length - 1];
          const pathD = pointsWithVals.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
          const areaD = `${pathD} L ${last.x} ${height - margin.bottom} L ${first.x} ${height - margin.bottom} Z`;

          return (
            <path key={`area-${line.id}`} d={areaD} fill={`url(#area-grad-${line.id})`} />
          );
        })}

        {/* Draw Line Paths */}
        {lines.map(line => {
          const pointsWithVals = data
            .map((d, index) => ({ x: getX(index), y: getY(d[line.key]), val: d[line.key] }))
            .filter(pt => pt.val !== undefined && pt.val !== null && !isNaN(pt.y));

          if (pointsWithVals.length === 0) return null;

          const pathD = pointsWithVals.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

          return (
            <path
              key={`line-${line.id}`}
              d={pathD}
              fill="none"
              stroke={line.color}
              strokeWidth={line.dashed ? 1.5 : 2.5}
              strokeDasharray={line.dashed ? "4 4" : undefined}
              className="transition-all duration-300"
            />
          );
        })}

        {/* Hover elements */}
        {hoverIndex !== null && data[hoverIndex] && (
          <g>
            <line
              x1={getX(hoverIndex)}
              y1={margin.top}
              x2={getX(hoverIndex)}
              y2={height - margin.bottom}
              stroke="#64748b"
              strokeWidth={1.5}
              strokeDasharray="2 2"
              className="opacity-65"
            />
            {lines.map(line => {
              const val = data[hoverIndex][line.key];
              if (val === undefined || val === null || isNaN(val)) return null;
              return (
                <circle
                  key={`dot-${line.id}`}
                  cx={getX(hoverIndex)}
                  cy={getY(val)}
                  r={4.5}
                  fill={line.color}
                  stroke="#0f172a"
                  strokeWidth={1.5}
                />
              );
            })}
          </g>
        )}
      </svg>

      {/* Hover Tooltip Card */}
      {hoverIndex !== null && data[hoverIndex] && mousePos && (
        <div 
          className="absolute bg-slate-950/95 border border-slate-700 p-3.5 rounded-xl shadow-2xl z-20 text-[11px] w-[220px] pointer-events-none transition-all duration-75 text-slate-200"
          style={{
            left: `${mousePos.x + 15 + 220 > mousePos.containerWidth ? mousePos.x - 235 : mousePos.x + 15}px`,
            top: `${mousePos.y + 15 + 180 > mousePos.containerHeight ? mousePos.y - 195 : mousePos.y + 15}px`
          }}
        >
          <div className="font-bold text-white mb-2 border-b border-slate-800 pb-1.5 flex justify-between items-center">
            <span>Date: {data[hoverIndex].date}</span>
          </div>
          <div className="space-y-1 max-h-[160px] overflow-y-auto pr-1">
            {lines.map(line => {
              const val = data[hoverIndex][line.key];
              if (val === undefined || val === null || isNaN(val)) return null;
              return (
                <div key={line.key} className="flex justify-between items-center">
                  <div className="flex items-center space-x-1.5 min-w-0">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: line.color }} />
                    <span className="text-slate-200 font-medium truncate" title={line.label}>{line.label}</span>
                  </div>
                  <span className={`font-mono font-bold shrink-0 ${val >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {line.isPnL ? (
                      `${val >= 0 ? '+' : '-'}$${Math.abs(val).toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                    ) : (
                      `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
