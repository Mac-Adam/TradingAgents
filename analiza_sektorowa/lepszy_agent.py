import os
import time
import datetime
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import re
from google import genai

# ================= CONFIGURATION =================
GEMINI_API_KEY = "key"

client = genai.Client(api_key=GEMINI_API_KEY)

# Słownik GICS: Używamy firm jako "przynęty" na algorytmy wyszukiwarek
gics_sub_industries = {
    "Semiconductors": ["Nvidia", "TSMC", "AMD"],
    "Automobile Manufacturers": ["Tesla", "Toyota", "Volkswagen"],
    "Aerospace & Defense": ["Lockheed Martin", "RTX", "Boeing"],
    "Pharmaceuticals": ["Eli Lilly", "Novo Nordisk"],
    "Renewable Electricity": ["NextEra Energy", "Brookfield Renewable"],
    "Systems Software": ["Microsoft", "Oracle"],
    "Copper": ["Freeport-McMoRan", "Southern Copper"],
    "Interactive Media & Services": ["Alphabet", "Meta"]
}
# =================================================

def get_google_news_rss(sub_industry, limit=3):
    """Pobiera wiadomości z Google News RSS (omija limity API i blokady botów)."""
    companies = gics_sub_industries.get(sub_industry, [])
    
    # Zapytanie np: (Nvidia OR TSMC OR AMD) AND financial
    query = "(" + " OR ".join(companies) + ") AND financial"
    encoded_query = urllib.parse.quote(query)
    
    # when:7d wymusza wiadomości z ostatnich 7 dni
    url = f"https://news.google.com/rss/search?q={encoded_query}+when:7d&hl=en-US&gl=US&ceid=US:en"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    articles_data = []
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Parsowanie pliku XML zwróconego przez Google
        root = ET.fromstring(response.content)
        
        # Przeszukiwanie tagów <item>
        for item in root.findall('.//item')[:limit]:
            title = item.find('title').text if item.find('title') is not None else ''
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
            
            # Google ukrywa podsumowanie artykułu w tagu description (zazwyczaj jako HTML)
            desc_html = item.find('description').text if item.find('description') is not None else ''
            # Czyszczenie z tagów HTML, by zostawić czysty tekst dla LLM
            snippet = re.sub(r'<[^>]+>', ' ', desc_html).strip()
            
            if title:
                full_text = f"DATE: {pub_date}\nTITLE: {title}\nSNIPPET: {snippet}"
                articles_data.append(full_text)
                
        return articles_data
    except Exception as e:
        print(f"Błąd pobierania RSS dla {sub_industry}: {e}")
        return []

def evaluate_single_article(sub_industry, article_text):
    """Przekazuje fragment artykułu do LLM w celu oceny inwestycyjnej."""
    prompt = f"""
    You are a strictly logical financial scoring agent. 
    Read the following news snippet regarding companies in the "{sub_industry}" sub-industry:
    
    {article_text}
    
    Your task:
    1. Score the short-term (1 week) investment potential on a scale from -2 to 2 
       (-2 is extremely negative, 0 is neutral, and +2 is extremely positive).
    2. Write exactly ONE short paragraph explaining the specific reasoning behind this score based on the text.
    
    You MUST format your output exactly like this:
    SCORE: [Your integer here]
    IMPACT: [Your paragraph here]
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=prompt,
        )
        text = response.text
        
        # Wyszukiwanie wzorców w odpowiedzi LLM
        score_match = re.search(r"SCORE:\s*([+-]?\d+)", text)
        impact_match = re.search(r"IMPACT:\s*(.*)", text, re.IGNORECASE | re.DOTALL)
        
        score = int(score_match.group(1)) if score_match else 0
        impact = impact_match.group(1).strip() if impact_match else "No explanation provided."
        
        # Zabezpieczenie limitów skali
        return max(-2, min(2, score)), impact
    except Exception as e:
        return 0, f"Error evaluating this article: {e}"

def save_industry_report(sub_industry, total_score, report_lines):
    """Zapisuje raport dla konkretnej sub-branży w dedykowanym folderze."""
    folder_name = "reports_data"
    os.makedirs(folder_name, exist_ok=True)
    
    date_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    clean_name = sub_industry.replace(" & ", "_and_").replace(" ", "_").lower()
    
    filename = os.path.join(folder_name, f"report_{clean_name}_{date_str}.txt")
    
    with open(filename, "w", encoding="utf-8") as file:
        file.write(f"RAPORT GICS: {sub_industry.upper()}\n")
        file.write(f"DATA WYGENEROWANIA: {date_str}\n")
        file.write(f"ŁĄCZNY WYNIK SENTYMENTU: {total_score}\n")
        file.write("="*60 + "\n\n")
        
        for line in report_lines:
            file.write(line + "\n")
            
    return filename

def final_company_selection(saved_files):
    """Agent Nadrzędny: Czyta wszystkie wygenerowane raporty i wybiera 3 najlepsze spółki."""
    print("\n" + "="*60)
    print(" AGENT NADRZĘDNY: OSTATECZNA SELEKCJA TOP 3 SPÓŁEK")
    print("="*60)
    print("⚙️ Ładowanie wygenerowanych raportów sektorowych do pamięci...")
    
    all_reports_text = ""
    for file_path in saved_files:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                # Dodajemy nagłówek pliku dla kontekstu
                all_reports_text += f"\n\n--- PLIK: {os.path.basename(file_path)} ---\n"
                all_reports_text += file.read()
        except Exception as e:
            print(f"Błąd podczas czytania raportu {file_path}: {e}")
            
    prompt = f"""
    Jesteś Głównym Agentem Inwestycyjnym (Chief Investment Officer).
    Poniżej znajdują się surowe raporty sektorowe wygenerowane przez Twoich podległych analityków.
    
    TWOJE ZADANIE:
    1. Przeczytaj wnikliwie WSZYSTKIE poniższe raporty. MASZ ZAKAZ używania jakiejkolwiek innej wiedzy spoza tego tekstu.
    2. Wybierz dokładnie 3 KONKRETNE SPÓŁKI (nazwy firm), które na podstawie tych raportów mają najlepsze perspektywy na wzrost w najbliższym tygodniu.
    3. Dla każdej wybranej spółki napisz krótki, precyzyjny akapit (max 3-4 zdania) uzasadniający ten wybór, powołując się na informacje z raportów.
    
    Wymagany format odpowiedzi:
    1. [Nazwa Spółki 1]
    - [Twój akapit uzasadniający]
    
    2. [Nazwa Spółki 2]
    - [Twój akapit uzasadniający]
    
    3. [Nazwa Spółki 3]
    - [Twój akapit uzasadniający]
    
    DANE DO ANALIZY:
    {all_reports_text}
    """
    
    print("🧠 Model LLM analizuje pełny zbiór danych w poszukiwaniu najlepszych okazji...")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"Błąd podczas generowania finałowego wyboru: {e}"

def analyze_all_sub_industries():
    """Główna pętla agenta. Zwraca ranking oraz listę zapisanych plików."""
    final_ranking = {}
    saved_files = [] # Nowa lista do śledzenia plików z obecnej sesji
    
    print("\n" + "="*60)
    print(" SKANOWANIE RYNKU: GOOGLE NEWS RSS + GEMINI")
    print("="*60)

    for sub_industry in gics_sub_industries.keys():
        print(f"\n⚙️ Analiza: {sub_industry.upper()}...")
        articles = get_google_news_rss(sub_industry)
        
        if not articles:
            print(f"   Brak wiadomości. Pomijam.")
            continue
            
        sub_score = 0
        sub_reports = []
        
        for i, article in enumerate(articles, 1):
            score, impact = evaluate_single_article(sub_industry, article)
            sub_score += score
            
            title_only = article.split('\n')[1].replace('TITLE: ', '')
            report_block = f"--- NEWS {i} ---\nTYTUŁ: {title_only}\nWYNIK: {score}\nANALIZA: {impact}\n"
            sub_reports.append(report_block)
            
            # ⏳ KROK 1: Zwiększamy przerwę między artykułami do 5 sekund
            print(f"   ...oczekiwanie 5s na bezpieczne zapytanie LLM...")
            time.sleep(5)
            
        print(f"   ✅ Zakończono ocenę. Łączny wynik: {sub_score}")
        saved_file = save_industry_report(sub_industry, sub_score, sub_reports)
        saved_files.append(saved_file) # Zapisujemy ścieżkę do pliku
        print(f"   📁 Raport wygenerowany: {saved_file}")
        
        final_ranking[sub_industry] = sub_score
        
        # ⏳ KROK 2: Dodajemy dłuższą przerwę (np. 8 sekund) między całymi sub-branżami
        print(f"   ⏳ Sektor zakończony. Odpoczynek dla API przed kolejną branżą (8s)...")
        time.sleep(8)
        
    return final_ranking, saved_files

if __name__ == "__main__":
    # Rozpakowujemy zwracane wartości (ranking oraz ścieżki do plików)
    market_results, generated_files = analyze_all_sub_industries()
    
    if not market_results:
        print("Nie zebrano żadnych danych.")
        exit()
        
    sorted_ranking = sorted(market_results.items(), key=lambda item: item[1], reverse=True)
    
    print("\n\n" + "★"*50)
    print(" PODSUMOWANIE RANKINGU (ZAPISANO W REPORTS_DATA) ")
    print("★"*50 + "\n")
    
    for rank, (sub_industry, score) in enumerate(sorted_ranking, 1):
        if score >= 2:
            status = "🚀 KUPUJ"
        elif score == 1:
            status = "📈 OPTYMIZM"
        elif score == 0:
            status = "⚖️ NEUTRALNY"
        elif score == -1:
            status = "📉 RYZYKO"
        else:
            status = "🚨 SPRZEDAJ"
            
        print(f"{rank}. {sub_industry.ljust(30)} | Wynik: {str(score).rjust(2)} | {status}")
    time.sleep(10)  # Krótka przerwa przed finałowym wyborem
    # KROK FINAŁOWY: Selekcja 3 najlepszych spółek przez Agenta Nadrzędnego
    final_picks_text = final_company_selection(generated_files)
    
    print("\n\n" + "🎯"*30)
    print(" OSTATECZNE REKOMENDACJE INWESTYCYJNE ")
    print("🎯"*30 + "\n")
    print(final_picks_text)
    print("\n" + "="*60)
    
    # Opcjonalnie: zapisanie tego finałowego wyboru również do pliku
    date_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    final_file = os.path.join("reports_data", f"FINAL_PICKS_{date_str}.txt")
    with open(final_file, "w", encoding="utf-8") as f:
        f.write("OSTATECZNE REKOMENDACJE INWESTYCYJNE (TOP 3)\n")
        f.write("="*50 + "\n")
        f.write(final_picks_text)
    print(f"✅ Zapisano rekomendacje w: {final_file}")