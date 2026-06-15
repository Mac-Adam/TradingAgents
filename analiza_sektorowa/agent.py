
import os
import datetime
from datetime import timedelta
import requests
from google import genai

# ================= CONFIGURATION =================
GEMINI_API_KEY = "key"
NEWS_API_KEY = "dec768f716dc40778f0c15d9695e3431"


client = genai.Client(api_key=GEMINI_API_KEY)

# Dictionary of sectors and their blue-chip companies
sector_companies = {
    "technology": ["Apple", "Microsoft", "Nvidia", "Alphabet", "Meta"],
    "wind energy": ["Vestas", "Orsted", "Siemens Energy", "GE Vernova", "Iberdrola"],
    "mining and metals": ["BHP", "Rio Tinto", "Freeport-McMoRan", "Vale", "Glencore"],
    "healthcare": ["Eli Lilly", "Novo Nordisk", "Johnson & Johnson", "UnitedHealth", "Merck"],
    "financials": ["JPMorgan Chase", "Visa", "Mastercard", "Bank of America", "Berkshire Hathaway"],
    "energy": ["ExxonMobil", "Chevron", "Shell", "TotalEnergies", "BP"],
    "automotive": ["Tesla", "Toyota", "BYD", "Volkswagen", "Stellantis"],
    "aerospace and defense": ["Lockheed Martin", "RTX (Raytheon)", "Boeing", "Airbus", "General Dynamics"],
    "consumer discretionary": ["Amazon", "Home Depot", "LVMH", "McDonald's", "Nike"],
    "telecommunications": ["AT&T", "Verizon", "T-Mobile", "Comcast", "China Mobile"]
}
# =================================================

def get_sector_news(sector):
    """Fetches the latest news headlines from ONLY the last 7 days."""
    
    # Obliczanie daty: dokładnie 7 dni temu
    today = datetime.datetime.now()
    seven_days_ago = today - timedelta(days=7)
    date_from = seven_days_ago.strftime('%Y-%m-%d')
    
    print(f"[API] Searching for news from {date_from} to today...")
    
    # Dodany parametr 'from={date_from}'
    url = f"https://newsapi.org/v2/everything?q={sector}&language=en&from={date_from}&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        articles = data.get("articles", [])[:5]
        news_list = [f"{art['title']} - {art['description']}" for art in articles]
        
        return news_list
    except Exception as e:
        print(f"Error fetching news: {e}")
        return ["No official news available for the past 7 days."]

def generate_decision_report(sector, news_list):
    """Evaluates 7-day news to predict SHORT-TERM market sentiment."""
    news_text = "\n".join([f"- {n}" for n in news_list])
    
    # Nowy, agresywniejszy prompt ukierunkowany na przyszłość
    prompt = f"""
    You are the Chief Analytical Agent (Macro-Analyst) focusing on SHORT-TERM trading.
    Your task is to evaluate the immediate future of the following economic sector: "{sector}".
    
    Analyze the latest global news strictly from the past 7 days:
    {news_text}
    
    Write a concise decision report (max 3 paragraphs) structured as follows:
    1. Immediate Impact: Summarize what these recent events mean for the sector right now.
    2. Short-Term Forecast: Based on these events, predict what is most likely to happen in this sector in the next 1-4 weeks. Will there be volatility, growth, or a pullback?
    3. Sentiment: Is the extreme short-term sentiment positive, negative, or neutral?
    
    At the very end of the report, provide a clear recommendation (YES or NO) 
    on whether lower-level agents should immediately begin analyzing specific companies for short-term entry points.
    Format the final line exactly like this: "RECOMMENDATION: YES" or "RECOMMENDATION: NO".
    """
    
    print(f"\n[Macro Agent is forecasting the short-term future for {sector}...]\n")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"Gemini Model Error: {e}"

def save_to_file(sector, content):
    """Saves the generated report to a text file."""
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    clean_sector = sector.replace(" ", "_").lower()
    filename = f"report_{clean_sector}_{now}.txt"
    
    with open(filename, "w", encoding="utf-8") as file:
        file.write(f"SHORT-TERM MACRO REPORT: {sector.upper()}\n")
        file.write("="*50 + "\n")
        file.write(content + "\n")
        file.write("="*50 + "\n")
        
    print(f"\n✅ Report successfully saved to: {filename}")

if __name__ == "__main__":
    target_sector = "telecommunications"
    
    print(f"1. Fetching official news for: {target_sector}...")
    latest_news = get_sector_news(target_sector)
    
    if latest_news and latest_news[0] != "No official news available for the past 7 days.":
        report = generate_decision_report(target_sector, latest_news)
        
        print("="*50)
        print(report)
        print("="*50)
        
        save_to_file(target_sector, report)
        
        if "RECOMMENDATION: YES" in report.upper():
            companies_to_analyze = sector_companies.get(target_sector, [])
            print("\n🚀 Macro Agent approved the sector for SHORT-TERM potential!")
            print(f"Next step: Trigger Micro-Agents for: {companies_to_analyze}")
        else:
            print("\n🛑 Macro Agent rejected the sector. No short-term play detected.")
    else:
        print("Nie pobrano wystarczających danych do analizy.")