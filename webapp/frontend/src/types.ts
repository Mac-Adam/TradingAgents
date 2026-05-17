export interface Run {
  id: string;
  wallet_name: string;
  config_file: string;
  env_file: string;
  account_type: string;
  status: string;
  created_at: string;
}

export interface TaskRecord {
  id: string;
  run_id: string;
  ticker: string;
  status: string; // queued | running | completed | failed
  created_at: string;
  scheduled_at: string | null;
  recurrence: string | null; // e.g. "daily:21:00"
  report_path: string | null;
  error: string | null;
  decision: string | null;
  stats?: any | null;
  task_type: string;
}

export interface DecisionRecord {
  id: string;
  run_id: string;
  task_id: string;
  ticker: string;
  action: string; // Buy / Sell / Hold / Overweight / Underweight
  rationale: string;
  full_report_path: string | null;
  timestamp: string;
  stats?: any | null;
  task_type: string; // analysis | execution
}
