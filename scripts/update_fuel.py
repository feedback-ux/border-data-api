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

# Връщаме TR към началната страница, защото потвърди, че ползва кутии
URLS = {
    "BG": "https://bg.fuelo.net/?lang=en",
    "GR": "https://gr.fuelo.net/?lang=en",
    "RO": "https://ro.fuelo.net/?lang=en",
    "TR": "https://tr.fuelo.net/?lang=en", # Върнато към tr.fuelo.net
    "RS": "https://rs.fuelo.net/?lang=en",
    "MK": "https://mk.fuelo.net/?lang=en"
}

# Мапинг на горивата
FUEL_MAPPING = {
    "Benzin A95": "gasoline", "Unleaded 95": "gasoline", "Gasoline A95": "gasoline", "A95": "gasoline",
    "Бензин A95": "gasoline", "Бензин": "gasoline", "Kurşunsuz 95": "gasoline",
    
    "Diesel Premium": "diesel_plus", "Дизел Премиум": "diesel_plus", "MaxxMotion": "diesel_plus",
    "Diesel": "diesel", "Дизел": "diesel", "Motorin": "diesel",
    
    "LPG": "lpg", "Autogas": "lpg", "Gas": "lpg", "Пропан Бутан": "lpg", "Газ": "lpg", "Otogaz": "lpg",
    "Methane": "cng", "CNG": "cng", "Метан": "cng"
}

def get_exchange_rates():
    """Взима курсове от API и добавя твърди стойности за липсващите"""
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

    # Fallback курсове (актуализирани)
    if 'RSD' not in rates: rates['RSD'] = 117.0
    if 'MKD' not in rates: rates['MKD'] = 61.5
    if 'TRY' not in rates: rates['TRY'] = 37.0 # Актуален курс ~37
    if 'BGN' not in rates: rates['BGN'] = 1.95583
    if 'RON' not in rates: rates['RON'] = 4.97
    
    return rates

def detect_currency_and_rate(text_raw, country_code, rates):
    """Опитва се да познае валутата, включително символа ₺"""
    text = text_raw.lower()
    
    # 1. Проверка по символи/код
    if '€' in text or 'eur' in text: return 'EUR', 1.0
    if '₺' in text or 'try' in text or 'tl' in text: return 'TRY', rates.get('TRY', 37.0) # Тук е ключът!
    if 'ron' in text or 'lei' in text: return 'RON', rates.get('RON', 4.97)
    if 'rsd' in text or 'din' in text: return 'RSD', rates.get('RSD', 117.0)
    if 'mkd' in text or 'den' in text: return 'MKD', rates.get('MKD', 61.5)
    if 'lv' in text or 'лв' in text or 'bgn' in text: return 'BGN', rates.get('BGN', 1.95583)
    
    # 2. Fallback по държава
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

        # ВАЖНО: Форсираме UTF-8, за да разчете правилно ₺
        response.encoding = 'utf-8' 

        soup = BeautifulSoup(response.text, 'html.parser')
        prices = {}
        found_any = False

        # --- СТРАТЕГИЯ 1: Търсене на КУТИИ (Cards) ---
        boxes = soup.find_all('div', class_=lambda x: x and 'box' in x.split())
        for box in boxes:
            h2 = box.find('h2')
            h3 = box.find('h3')
            if h2 and h3:
                name_raw = h2.get_text(strip=True)
                price_raw = h3.get_text(strip=True) # Тук вече трябва да видим "52,67 ₺" правилно
                
                # Търсим числото
                match = re.search(r"([0-9]+[.,][0-9]+)", price_raw)
                if match:
                    val_text = match.group(1).replace(',', '.')
                    curr, rate = detect_currency_and_rate(price_raw, country_code, rates)
                    
                    for k, v in FUEL_MAPPING.items():
                        if k.lower() in name_raw.lower():
                            if v not in prices:
                                try:
                                    price_eur = float(val_text) / rate if curr != 'EUR' else float(val_text)
                                    prices[v] = round(price_eur, 2)
                                    print(f"  > [BOX] {v}: {prices[v]} EUR (raw: {val_text} {curr})")
                                    found_any = True
                                except: pass
                            break

        # --- СТРАТЕГИЯ 2: Търсене на ТАБЛИЦА (Fallback) ---
        if not found_any:
            rows = soup.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    name_raw = cols[0].get_text(strip=True)
                    price_raw = cols[1].get_text(strip=True)
                    
                    match = re.search(r"([0-9]+[.,][0-9]+)", price_raw)
                    if match:
                        val_text = match.group(1).replace(',', '.')
                        curr, rate = detect_currency_and_rate(price_raw, country_code, rates)
                        
                        for k, v in FUEL_MAPPING.items():
                            if k.lower() in name_raw.lower():
                                if v not in prices: 
                                    try:
                                        price_eur = float(val_text) / rate if curr != 'EUR' else float(val_text)
                                        prices[v] = round(price_eur, 2)
                                        print(f"  > [TABLE] {v}: {prices[v]} EUR (raw: {val_text} {curr})")
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
