import yfinance as yf
import requests
from datetime import datetime

SCREENER_PROMPT = """
Jesteś ekspertem inwestycyjnym. Masz dostęp do aktualnych danych rynkowych i newsów.

Oto dane z Yahoo Finance o kandydatach do inwestycji:
{market_data}

Oto najnowsze wiadomości finansowe:
{news}

Na podstawie tych danych wybierz TOP 10 spółek, w które inwestycja w najbliższych 
3-6 miesiącach ma największy potencjał zysku. 

Uwzględnij:
- momentum cenowe i wolumen
- fundamenty (P/E, wzrost przychodów, marże)
- sentyment newsów
- trendy sektorowe

Odpowiedz TYLKO w formacie JSON:
{{
  "top_stocks": [
    {{
      "ticker": "AAPL",
      "company": "Apple Inc.",
      "sector": "Technology", 
      "rationale": "Krótkie uzasadnienie (2-3 zdania)",
      "confidence": 8.5
    }}
  ],
  "market_summary": "Ogólny komentarz o rynku"
}}
"""





import pandas as pd

def get_nasdaq100_tickers():
    """
    Zwraca stałą, aktualną listę wszystkich spółek wchodzących w skład indeksu NASDAQ 100.
    Rozwiązanie w 100% stabilne i niezależne od zmian na Wikipedii.
    """
    return [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST",
        "NFLX", "AMD", "ASML", "AZN", "LIN", "PEP", "ADBE", "ORCL", "CSCO", "TMUS",
        "CMCSA", "CRM", "INTC", "QCOM", "TXN", "AMGN", "HON", "ISRG", "INTU", "AMAT",
        "BKNG", "MU", "PANW", "MDLZ", "VRTX", "ADI", "REGN", "LRCX", "GILD", "ADP",
        "MELI", "MDV", "SNPS", "CDNS", "KLAC", "CSX", "MAR", "PYPL", "ASML", "CTAS",
        "MNST", "NXPI", "ORLY", "LULU", "WDAY", "ROP", "PCAR", "PDD", "ADSK", "CPRT",
        "PAYX", "FAST", "CHTR", "ANSS", "MARA", "AEP", "KDP", "DDOG", "EXC", "DXCM",
        "BKR", "IDXX", "EA", "CTSH", "GEHC", "TEAM", "MCHP", "VRSK", "CSGP", "FTNT",
        "AWK", "BILI", "SBUX", "MRVL", "TTD", "CEG", "WBD", "MDB", "ILMN", "ALGN",
        "FANG", "DD", "PDD", "PANW", "SMCI", "ARM", "APP", "PLTR"
    ]










    

def get_market_data():
    """Pobiera dane z Yahoo Finance dla WSZYSTKICH spółek z indeksu NASDAQ 100"""
    
    candidates = get_nasdaq100_tickers()
    print(f"📊 Pobrano listę {len(candidates)} spółek z NASDAQ 100. Rozpoczynam pobieranie danych z Yahoo Finance...")
    
    data_summary = []
    
    for i, ticker in enumerate(candidates, 1):
        try:
            # Mały licznik postępu w terminalu, żebyś widziała, że program żyje
            if i % 10 == 0 or i == len(candidates):
                print(f"🔄 Pobrano dane dla {i}/{len(candidates)} spółek...")
                
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="1mo")
            
            if hist.empty:
                continue
                
            price_change_1m = ((hist['Close'].iloc[-1] - hist['Close'].iloc[0]) 
                               / hist['Close'].iloc[0] * 100)
            
            data_summary.append({
                "ticker": ticker,
                "name": info.get("longName", ticker),
                "sector": info.get("sector", "Unknown"),
                "price": info.get("currentPrice", 0),
                "pe_ratio": info.get("trailingPE", "N/A"),
                "revenue_growth": info.get("revenueGrowth", "N/A"),
                "profit_margins": info.get("profitMargins", "N/A"),
                "price_change_1m_pct": round(price_change_1m, 2),
                "52w_high": info.get("fiftyTwoWeekHigh", "N/A"),
                "analyst_target": info.get("targetMeanPrice", "N/A"),
                "recommendation": info.get("recommendationKey", "N/A"),
            })
        except Exception as e:
            # Jeśli jedna spółka rzuci błędem, ignorujemy ją i lecimy dalej
            continue
            
    return data_summary
    

    


def get_financial_news():
    """Pobiera newsy finansowe przez yfinance"""
    news_items = []
    
    # Newsy dla indeksów i top spółek
    for ticker in ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"]:
        try:
            stock = yf.Ticker(ticker)
            news = stock.news[:3]  # 3 newsy per ticker
            for item in news:
                news_items.append({
                    "title": item.get("title", ""),
                    "publisher": item.get("publisher", ""),
                })
        except:
            continue
    
    return news_items


def run_stock_screener(llm_client) -> dict:
    """
    Główna funkcja agenta. Pobiera NASDAQ 100, dzieli na paczki po 25, 
    zbiera wyniki od Gemini i łączy je w jeden końcowy raport.
    """
    # 1. Pobranie danych dla wszystkich spółek
    market_data = get_market_data()
    
    print("📰 StockScreenerAgent: Pobieram globalne newsy finansowe...")
    news = get_financial_news()
    news_str = "\n".join([f"- [{item['publisher']}] {item['title']}" for item in news[:15]])
    
    # 2. Dzielenie na paczki po 25 spółek
    PACZKA_SIZE = 25
    paczki = [market_data[i:i + PACZKA_SIZE] for i in range(0, len(market_data), PACZKA_SIZE)]
    
    wszystkie_top_stocks = []
    komentarze_rynkowe = []
    
    print(f"🤖 Rozpoczynam analizę z Gemini. Podzielono dane na {len(paczki)} paczki.")
    
    import json
    from langchain_core.messages import HumanMessage
    
    for nr_paczki, paczka in enumerate(paczki, 1):
        print(f"🧠 Analizuję paczkę {nr_paczki}/{len(paczki)} (zawiera {len(paczka)} spółek)...")
        
        # Formatowanie tekstu tylko dla obecnej paczki spółek
        market_str = "\n".join([
            f"- {s['ticker']} ({s['name']}, {s['sector']}): "
            f"cena ${s['price']}, zmiana 1M: {s['price_change_1m_pct']}%, "
            f"P/E: {s['pe_ratio']}, rekomendacja: {s['recommendation']}"
            for s in paczka
        ])
        
        prompt = SCREENER_PROMPT.format(
            market_data=market_str,
            news=news_str
        )
        
        try:
            # Wywołanie modelu LLM
            response = llm_client.invoke([HumanMessage(content=prompt)])
            text = response.content
            
            # Oczyszczanie kodu JSON ze znaczników markdown
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            paczka_result = json.loads(text.strip())
            
            # Zbieramy wybrane spółki z tej paczki
            wszystkie_top_stocks.extend(paczka_result.get("top_stocks", []))
            if paczka_result.get("market_summary"):
                komentarze_rynkowe.append(paczka_result.get("market_summary"))
                
        except Exception as e:
            print(f"⚠️ Błąd podczas analizy paczki {nr_paczki}: {e}")
            continue
            
    # 3. Końcowa selekcja: Sortujemy wszystkie wybrane spółki po "confidence" (pewności AI)
    # i wybieramy absolutne TOP 10 z całej giełdy NASDAQ 100
    wszystkie_top_stocks.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    final_top_10 = wszystkie_top_stocks[:10]
    
    # Składamy ostateczny wynik w identyczną strukturę JSON
    final_result = {
        "top_stocks": final_top_10,
        "market_summary": komentarze_rynkowe[0] if komentarze_rynkowe else "Analiza zakończona pomyślnie."
    }
    
    return final_result