#!/usr/bin/env python3
"""
StockScreener → TradingAgents pipeline
Najpierw wybiera 10 spółek, potem analizuje każdą przez TradingAgents.
"""

import os
import json
import time
import threading
from datetime import date
from dotenv import load_dotenv

load_dotenv()

# === KONFIGURACJA ===
LLM_PROVIDER  = "google"       # "openai" | "anthropic" | "google"
LLM_MODEL     = "gemini-2.5-flash"
DEEP_ANALYSIS = True           # czy uruchamiać pełny TradingAgents na TOP 3?
ANALYSIS_DATE = date.today().strftime("%Y-%m-%d")

# --- Rate limiting ---
# Google Gemini free tier: 15 req/min dla Flash, 2 req/min dla Pro
# OpenAI gpt-4o-mini:      500 req/min (praktycznie bez limitu)
# Anthropic Claude:        50 req/min
RATE_LIMITS = {
    "google":    {"rpm": 5, "min_delay": 4.5},   # 14/min z buforem bezpieczeństwa
    "openai":    {"rpm": 60, "min_delay": 1.0},
    "anthropic": {"rpm": 45, "min_delay": 1.5},
}

# ===========================

class RateLimiter:
    """
    Thread-safe rate limiter — pilnuje maksymalnie `rpm` wywołań na minutę
    oraz minimalnego odstępu `min_delay` sekund między wywołaniami.
    """

    def __init__(self, provider: str):
        limits = RATE_LIMITS.get(provider, {"rpm": 30, "min_delay": 2.0})
        self.rpm       = limits["rpm"]
        self.min_delay = limits["min_delay"]
        self._lock     = threading.Lock()
        self._calls    = []          # timestamps ostatnich wywołań
        self._last_call = 0.0

    def wait(self, label: str = ""):
        """Wywołaj przed każdym requestem do API."""
        with self._lock:
            now = time.monotonic()

            # 1) Minimalne opóźnienie między kolejnymi requestami
            elapsed_since_last = now - self._last_call
            if elapsed_since_last < self.min_delay:
                sleep_for = self.min_delay - elapsed_since_last
                print(f"   ⏳ Rate limit — czekam {sleep_for:.1f}s"
                      + (f" [{label}]" if label else ""))
                time.sleep(sleep_for)
                now = time.monotonic()

            # 2) Okno minutowe — usuń stare wpisy
            window_start = now - 60.0
            self._calls = [t for t in self._calls if t > window_start]

            # 3) Jeśli okno pełne — czekaj aż najstarszy wpis „wygaśnie"
            if len(self._calls) >= self.rpm:
                oldest = self._calls[0]
                wait_until = oldest + 60.0
                sleep_for  = wait_until - now + 0.5  # +0.5 s bufor
                print(f"   ⏳ Okno RPM pełne ({self.rpm}/min) — czekam "
                      f"{sleep_for:.1f}s" + (f" [{label}]" if label else ""))
                time.sleep(max(sleep_for, 0))
                now = time.monotonic()
                self._calls = [t for t in self._calls if t > now - 60.0]

            self._calls.append(now)
            self._last_call = now


def build_llm(provider: str, model: str):
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=0.3)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=0.3)
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, temperature=0.3)
    else:
        raise ValueError(f"Nieznany provider: {provider}")


def run_screener_with_retry(llm, rate_limiter, max_retries: int = 3) -> dict:
    """
    Uruchamia screener z automatycznym retry przy błędzie 429 (too many requests).
    """
    from tradingagents.agents.analysts.stock_screener_agent import run_stock_screener

    for attempt in range(1, max_retries + 1):
        try:
            rate_limiter.wait(label="screener")
            return run_stock_screener(llm)
        except Exception as e:
            err = str(e).lower()
            is_rate_error = any(x in err for x in
                                ["429", "rate", "quota", "resource exhausted",
                                 "too many requests"])
            if is_rate_error and attempt < max_retries:
                wait_time = 60 * attempt   # 60s, 120s, 180s ...
                print(f"   ⚠️  Błąd limitu API (próba {attempt}/{max_retries}). "
                      f"Czekam {wait_time}s przed ponowną próbą...")
                time.sleep(wait_time)
            else:
                raise


def run_deep_analysis_with_retry(ta, ticker: str, analysis_date: str,
                                  rate_limiter, max_retries: int = 3):
    """
    Uruchamia pełną analizę TradingAgents z retry przy rate limit.
    """
    for attempt in range(1, max_retries + 1):
        try:
            rate_limiter.wait(label=ticker)
            return ta.propagate(ticker, analysis_date)
        except Exception as e:
            err = str(e).lower()
            is_rate_error = any(x in err for x in
                                ["429", "rate", "quota", "resource exhausted",
                                 "too many requests"])
            if is_rate_error and attempt < max_retries:
                wait_time = 60 * attempt
                print(f"   ⚠️  Rate limit dla {ticker} (próba {attempt}/{max_retries}). "
                      f"Czekam {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise


def main():
    print("=" * 60)
    print("🚀 TradingAgents Stock Screener")
    print(f"📅 Data:     {ANALYSIS_DATE}")
    print(f"🤖 Provider: {LLM_PROVIDER} / {LLM_MODEL}")
    limits = RATE_LIMITS.get(LLM_PROVIDER, {})
    print(f"⚡ Rate limit: {limits.get('rpm', '?')} req/min, "
          f"min. odstęp: {limits.get('min_delay', '?')}s")
    print("=" * 60)

    rate_limiter = RateLimiter(LLM_PROVIDER)
    llm = build_llm(LLM_PROVIDER, LLM_MODEL)

    # ── 1. Screener ───────────────────────────────────────────────
    print("\n🔍 Uruchamiam Stock Screener...")
    screening_result = run_screener_with_retry(llm, rate_limiter)

    # ── 2. Wyświetl wyniki ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 TOP 10 SPÓŁEK DO INWESTYCJI")
    print("=" * 60)
    print(f"\n💬 {screening_result.get('market_summary', '')}\n")

    top_stocks = screening_result.get("top_stocks", [])

    for i, stock in enumerate(top_stocks, 1):
        ticker    = stock.get("ticker", "?")
        company   = stock.get("company", "")[:30]
        sector    = stock.get("sector", "")[:15]
        rationale = stock.get("rationale", "")
        confidence = stock.get("confidence", "?")
        print(f"{i:2}. {ticker:<6} | {company:<30} | {sector:<15} | "
              f"Pewność: {confidence}/10")
        print(f"     💡 {rationale}")
        print()

    # ── 3. Zapisz wyniki screenera ────────────────────────────────
    output_file = f"screening_{ANALYSIS_DATE}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(screening_result, f, ensure_ascii=False, indent=2)
    print(f"✅ Wyniki screenera zapisane: {output_file}")

    # ── 4. Głęboka analiza TOP 3 przez TradingAgents ──────────────
    if DEEP_ANALYSIS and top_stocks:
        print("\n" + "=" * 60)
        print("🔬 GŁĘBOKA ANALIZA (TradingAgents) dla TOP 3")
        print("   (każda analiza to wiele wywołań LLM — rate limiter aktywny)")
        print("=" * 60)

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"]   = LLM_PROVIDER
        config["deep_think_llm"] = LLM_MODEL
        config["quick_think_llm"] = LLM_MODEL

        ta = TradingAgentsGraph(debug=False, config=config)

        deep_results = []

        for stock in top_stocks[:3]:
            ticker = stock["ticker"]
            print(f"\n📈 Analizuję {ticker} ({stock.get('company', '')})...")

            try:
                _, decision = run_deep_analysis_with_retry(
                    ta, ticker, ANALYSIS_DATE, rate_limiter
                )
                print(f"   ✅ Decyzja: {decision}")
                deep_results.append({"ticker": ticker, "decision": str(decision)})
            except Exception as e:
                print(f"   ❌ Błąd dla {ticker}: {e}")
                deep_results.append({"ticker": ticker, "decision": f"ERROR: {e}"})

        # Zapisz wyniki głębokiej analizy
        deep_file = f"deep_analysis_{ANALYSIS_DATE}.json"
        with open(deep_file, "w", encoding="utf-8") as f:
            json.dump(deep_results, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Wyniki głębokiej analizy zapisane: {deep_file}")

    print("\n🏁 Gotowe!")


if __name__ == "__main__":
    main()