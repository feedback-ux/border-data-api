import json
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
import os
import time
import re

# --- КОНФИГУРАЦИЯ ---
JSON_FILE = 'border_data.json'
EXCHANGE_API = "https://api.frankfurter.app/latest?from=EUR"

# Всички държави ползват началните страници (където са кутиите)
URLS = {
    "BG": "https://bg.fuelo.net/?lang=en",
    "GR": "https://gr.fuelo.net/?lang=en",
    "RO": "https://ro.fuelo.net/?lang=en",
    "TR": "https://tr.fuelo.net/?lang=en",
    "RS": "https://rs.fuelo.net/?lang=en",
    "MK": "https://mk.fuelo.net/?lang=en"
}

# Мапинг на горивата
FUEL_MAPPING = {
    "Benzin A95": "gasoline", "Unleaded 95": "gasoline", "Gasoline A95": "gasoline", "A95": "gasoline",
    "Diesel": "diesel", "Diesel Premium": "diesel_plus",
    "LPG": "lpg", "Autogas": "lpg", "Gas": "lpg",
    "Methane": "cng", "CNG": "cng"
}

def get_exchange_rates():
    """Взима курсове от API (само за RON, TRY, RSD, MKD -> към EUR)"""
    scraper = cloudscraper.create_scraper()
    rates = {}
    try:
        response = scraper.get(EXCHANGE_API)
        if response.status_code == 200:
            data = response.json()
            rates = data.get('rates', {})
            print("Exchange rates loaded from API.")
    except Exception:
        pass

    # Fallback само за валутите, които не са EUR
    if 'RSD' not in rates: rates['RSD'] = 117.0
    if 'MKD' not in rates: rates['MKD'] = 61.5
    if 'TRY' not in rates: rates['TRY'] = 36.0 
    if 'RON' not in rates: rates['RON'] = 4.97
    
    return rates

def detect_currency_and_rate(text_raw, country_code, rates):
    """Опитва се да познае валутата. ЗА БЪЛГАРИЯ ВЕЧЕ Е САМО ЕВРО."""
    text = text_raw.lower()
    
    # Ако видим знак за евро или пише EUR -> 1:1
    if '€' in text or 'eur' in text: return 'EUR', 1.0
    
    # Другите валути
    if 'ron' in text or 'lei' in text: return 'RON', rates.get('RON', 4.97)
    if 'try' in text or 'tl' in text: return 'TRY', rates.get('TRY', 36.0)
    if 'rsd' in text or 'din' in text: return 'RSD', rates.get('RSD', 117.0)
    if 'mkd' in text or 'den' in text: return 'MKD', rates.get('MKD', 61.5)
    
    # Fallback по държава (За BG вече е EUR по подразбиране)
    defaults = {'BG': 'EUR', 'GR': 'EUR', 'RO': 'RON', 'TR': 'TRY', 'RS': 'RSD', 'MK': 'MKD'}
    curr = defaults.get(country_code, 'EUR')
    return curr, rates.get(curr, 1.0)

def scrape_fuelo(country_code, url, rates):
    print(f"--- Processing {country_code} ---")
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(url)
        if response.status_code != 200:
            print(f"FAILED: Status code {response.status_code}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')
        prices = {}
        found_any = False

        # --- Търсене на КУТИИ (Cards) ---
        # Търсим div с class="box" (както е в твоя HTML)
        boxes = soup.find_all('div', class_=lambda x: x and 'box' in x.split())
        
        for box in boxes:
            h2 = box.find('h2') # Име: Unleaded 95
            h3 = box.find('h3') # Цена: 1,25 €
            
            if h2 and h3:
                name_raw = h2.get_text(strip=True)
                price_raw = h3.get_text(strip=True)
                
                # Търсим числото (1,25)
                match = re.search(r"([0-9]+[.,][0-9]+)", price_raw)
                if match:
                    val_text = match.group(1).replace(',', '.')
                    
                    # Определяме валута (вече без лев)
                    curr, rate = detect_currency_and_rate(price_raw, country_code, rates)
                    
                    for k, v in FUEL_MAPPING.items():
                        if k.lower() in name_raw.lower():
                            try:
                                # Пресмятане
                                price_eur = float(val_text) / rate if curr != 'EUR' else float(val_text)
                                prices[v] = round(price_eur, 2)
                                print(f"  > Found {v}: {prices[v]} EUR (raw: {val_text} {curr})")
                                found_any = True
                            except: pass
                            break

        if found_any:
            prices['last_updated'] = datetime.now().strftime("%Y-%m-%d")
            return prices
        else:
            print(f"WARNING: No fuel prices found for {country_code}")
            return None

    except Exception as e:
        print(f"Error scraping {country_code}: {e}")
        return None

def main():
    if not os.path.exists(JSON_FILE):
        print(f"File {JSON_FILE} not found!")
        return

    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rates = get_exchange_rates()
    updated_count = 0
    
    for country in data.get('countries', []):
        c_id = country.get('id')
        if c_id in URLS:
            new_prices = scrape_fuelo(c_id, URLS[c_id], rates)
            if new_prices:
                country['fuel_prices'] = new_prices
                updated_count += 1
            time.sleep(1)
    
    if updated_count > 0:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"SUCCESS: Updated fuel prices for {updated_count} countries.")
    else:
        print("NO UPDATES: No data was changed.")

if __name__ == "__main__":
    main()
