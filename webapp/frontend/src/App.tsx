import { useState, useEffect } from 'react'
import './App.css'

import type { Run } from './types';
import WalletView from './WalletView';

const API = 'http://localhost:8000';

function App() {
  const [runs, setRuns] = useState<Run[]>([])
  const [health, setHealth] = useState<string>("Checking...")
  const [selectedWallet, setSelectedWallet] = useState<Run | null>(null)

  const [configs, setConfigs] = useState<string[]>([])
  const [envs, setEnvs] = useState<string[]>([])

  const [walletName, setWalletName] = useState("My Portfolio")
  const [selectedConfig, setSelectedConfig] = useState("")
  const [selectedEnv, setSelectedEnv] = useState("")
  const [initialCash, setInitialCash] = useState(100000)

  const fetchRuns = () => {
    fetch(`${API}/api/runs`)
      .then(res => res.json())
      .then(data => setRuns(data))
      .catch(console.error)
  }

  useEffect(() => {
    fetch(`${API}/api/health`)
      .then(res => res.json())
      .then(data => setHealth(data.status === 'ok' ? 'Backend Connected' : 'Backend Error'))
      .catch(() => setHealth('Backend Disconnected'))

    fetch(`${API}/api/configs`)
      .then(res => res.json())
      .then(data => {
        setConfigs(data);
        if (data.length > 0) setSelectedConfig(data[0]);
      })
      .catch(console.error)

    fetch(`${API}/api/envs`)
      .then(res => res.json())
      .then(data => {
        setEnvs(data);
        if (data.length > 0) setSelectedEnv(data[0]);
      })
      .catch(console.error)

    fetchRuns();
  }, [])

  const handleStartRun = () => {
    if (!walletName || !selectedConfig || !selectedEnv) return;

    fetch(`${API}/api/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        wallet_name: walletName,
        config_file: selectedConfig,
        env_file: selectedEnv,
        initial_cash: initialCash,
      })
    })
      .then(res => res.json())
      .then(() => fetchRuns())
      .catch(console.error)
  }

  if (selectedWallet) {
    const isReal = selectedWallet.account_type === 'REAL';
    return (
      <div className={`min-h-screen text-foreground p-8 transition-colors duration-500 ${isReal ? 'bg-[#1a0505]' : 'bg-background'}`}>
        <WalletView
          wallet={selectedWallet}
          onBack={() => setSelectedWallet(null)}
          onDelete={() => {
            fetchRuns();
            setSelectedWallet(null);
          }}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground p-8">
      <div className="max-w-[95%] mx-auto space-y-8">

        {/* Header */}
        <div className="p-8 rounded-2xl bg-slate-900 border border-slate-700 shadow-xl flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-accent to-purple-400 bg-clip-text text-transparent pb-2 py-1 leading-normal mb-2">
              TradingAgents Wallet Manager
            </h1>
            <p className="text-lg text-slate-200">
              Welcome to the 24/7 autonomous trading swarm interface.
            </p>
          </div>
          <div className="flex items-center space-x-3 bg-black p-4 rounded-xl border border-slate-700">
            <div className={`w-3 h-3 rounded-full ${health === 'Backend Connected' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></div>
            <p className="text-white font-medium">{health}</p>
          </div>
        </div>

        {/* Dashboard Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

          {/* Initialize Wallet Panel */}
          <div className="md:col-span-1 p-6 rounded-xl bg-slate-900 border border-slate-700 shadow-lg hover:border-accent/50 transition-colors duration-300">
            <h2 className="text-xl font-semibold mb-6 border-b border-slate-700 pb-2 text-white">Initialize Wallet</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-200 mb-1 font-medium">Wallet Name</label>
                <input
                  type="text"
                  value={walletName}
                  onChange={e => setWalletName(e.target.value)}
                  className="w-full bg-black border border-slate-600 rounded-lg p-2 text-white outline-none focus:border-accent transition-colors"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-200 mb-1 font-medium">Configuration</label>
                <select
                  value={selectedConfig}
                  onChange={e => setSelectedConfig(e.target.value)}
                  className="w-full bg-black border border-slate-600 rounded-lg p-2 text-white outline-none focus:border-accent transition-colors"
                >
                  {configs.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-sm text-slate-200 mb-1 font-medium">Environment File</label>
                <select
                  value={selectedEnv}
                  onChange={e => setSelectedEnv(e.target.value)}
                  className="w-full bg-black border border-slate-600 rounded-lg p-2 text-white outline-none focus:border-accent transition-colors"
                >
                  {envs.map(e => <option key={e} value={e}>{e}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-sm text-slate-200 mb-1 font-medium">Initial Cash ($)</label>
                <input
                  type="number"
                  value={initialCash}
                  onChange={e => setInitialCash(parseFloat(e.target.value) || 0)}
                  className="w-full bg-black border border-slate-600 rounded-lg p-2 text-white outline-none focus:border-accent transition-colors"
                />
              </div>

              <button
                onClick={handleStartRun}
                className="mt-6 px-4 py-3 bg-accent hover:bg-accent/80 text-white rounded-lg transition-all duration-300 cursor-pointer w-full font-bold shadow-lg shadow-accent/20"
              >
                Create Wallet Manager
              </button>
            </div>
          </div>

          {/* Active Wallets Panel */}
          <div className="md:col-span-2 p-6 rounded-xl bg-slate-900 border border-slate-700 shadow-lg">
            <div className="flex justify-between items-center mb-6 border-b border-slate-700 pb-2">
              <h2 className="text-xl font-semibold text-white">Active Wallets</h2>
              <span className="bg-accent/30 px-3 py-1 rounded-full text-sm font-bold text-white">{runs.length} Total</span>
            </div>

            <div className="space-y-4 overflow-y-auto max-h-[500px] pr-2">
              {runs.length === 0 ? (
                <div className="text-center py-12 text-slate-300 font-medium">
                  No wallets found. Initialize a new wallet to see it here.
                </div>
              ) : (
                runs.map(run => (
                  <div
                    key={run.id}
                    onClick={() => setSelectedWallet(run)}
                    className="p-4 rounded-lg bg-slate-800 border border-slate-700 hover:bg-slate-700 transition-colors flex items-center justify-between cursor-pointer group"
                  >
                    <div className="flex items-center space-x-6">
                      <div className="text-2xl font-bold text-white max-w-[400px] truncate" title={run.wallet_name}>{run.wallet_name}</div>

                      <div className="flex flex-col space-y-1">
                        <div className="text-sm text-slate-300 flex items-center">
                          <span className="w-16 font-medium">Config:</span>
                          <span className="text-white">{run.config_file}</span>
                        </div>
                        <div className="text-sm text-slate-300 flex items-center">
                          <span className="w-16 font-medium">Env:</span>
                          <span className="text-white">{run.env_file}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col items-end space-y-2">
                      <div className="flex items-center space-x-3">
                        {run.account_type === 'REAL' ? (
                          <span className="px-3 py-1 bg-red-500/20 text-red-400 border border-red-500/30 rounded font-bold text-lg tracking-wider animate-pulse">
                            REAL
                          </span>
                        ) : run.account_type === 'PAPER' ? (
                          <span className="px-3 py-1 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded font-bold text-lg tracking-wider">
                            PAPER
                          </span>
                        ) : (
                          <span className="px-3 py-1 bg-slate-600 text-white border border-slate-500 rounded font-bold tracking-wider">
                            {run.account_type}
                          </span>
                        )}
                        <span className="text-sm px-2 py-1 bg-green-500/20 text-green-400 rounded-full flex items-center">
                          <span className="w-2 h-2 rounded-full bg-green-500 mr-2 animate-pulse"></span>
                          Running
                        </span>
                      </div>
                      <span className="text-xs text-slate-400 font-medium">
                        {new Date(run.created_at).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}

export default App
