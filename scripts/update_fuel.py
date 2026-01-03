import json
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
import os
import time
import re
import random

# --- КОНФИГУРАЦИЯ ---
JSON_FILE = 'border_data.json'
EXCHANGE_API = "https://api.frankfurter.app/latest?from=EUR"

# URL адреси
URLS = {
    "BG": ["https://bg.fuelo.net/?lang=en"],
    "GR": ["https://gr.fuelo.net/?lang=en"],
    "RO": ["https://ro.fuelo.net/?lang=en"],
    "TR": ["https://tr.fuelo.net/?lang=en"],
    "RS": ["https://rs.fuelo.net/?lang=en"],
    "MK": ["https://mk.fuelo.net/?lang=en"]
}

FUEL_MAPPING = {
    "Benzin A95": "gasoline", "Unleaded 95": "gasoline", "Gasoline A95": "gasoline", "A95": "gasoline",
    "Бензин A95": "gasoline", "Бензин": "gasoline", "Kurşunsuz 95": "gasoline",
    "Diesel Premium": "diesel_plus", "Дизел Премиум": "diesel_plus", "MaxxMotion": "diesel_plus", "Extra": "diesel_plus",
    "Diesel": "diesel", "Дизел": "diesel", "Motorin": "diesel",
    "LPG": "lpg", "Autogas": "lpg", "Gas": "lpg", "Пропан Бутан": "lpg", "Газ": "lpg", "Otogaz": "lpg",
    "Methane": "cng", "CNG": "cng", "Метан": "cng"
}

def get_exchange_rates():
    scraper = cloudscraper.create_scraper()
    rates = {}
    try:
        response = scraper.get(EXCHANGE_API)
        if response.status_code == 200:
            rates = response.json().get('rates', {})
            print("Exchange rates loaded from API.")
    except Exception: pass

    # Fallback
    if 'RSD' not in rates: rates['RSD'] = 117.0
    if 'MKD' not in rates: rates['MKD'] = 61.5
    if 'TRY' not in rates: rates['TRY'] = 37.0 
    if 'BGN' not in rates: rates['BGN'] = 1.95583
    if 'RON' not in rates: rates['RON'] = 4.97
    return rates

def detect_currency_and_rate(text_raw, country_code, rates):
    text = text_raw.lower()
    if '€' in text or 'eur' in text: return 'EUR', 1.0
    if '₺' in text or 'try' in text or 'tl' in text: return 'TRY', rates.get('TRY', 37.0)
    if 'ron' in text or 'lei' in text: return 'RON', rates.get('RON', 4.97)
    if 'rsd' in text or 'din' in text: return 'RSD', rates.get('RSD', 117.0)
    if 'mkd' in text or 'den' in text: return 'MKD', rates.get('MKD', 61.5)
    if 'lv' in text or 'лв' in text or 'bgn' in text: return 'BGN', rates.get('BGN', 1.95583)
    
    defaults = {'BG': 'EUR', 'GR': 'EUR', 'RO': 'RON', 'TR': 'TRY', 'RS': 'RSD', 'MK': 'MKD'}
    curr = defaults.get(country_code, 'EUR')
    return curr, rates.get(curr, 1.0)

def scrape_url_with_retry(url, country_code, rates):
    # Създаваме scraper с настройки като истински браузър
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    # Опитваме 3 пъти
    for attempt in range(1, 4):
        try:
            print(f"  Attempt {attempt}/3: {url} ...")
            response = scraper.get(url)
            
            if response.status_code != 200:
                print(f"    > HTTP Error {response.status_code}")
                time.sleep(3)
                continue
            
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            prices = {}
            found_any = False

            # 1. Търсене на Кутии
            boxes = soup.find_all('div', class_=lambda x: x and 'box' in x.split())
            for box in boxes:
                h2 = box.find('h2')
                h3 = box.find('h3')
                if h2 and h3:
                    name_raw = h2.get_text(strip=True)
                    price_raw = h3.get_text(strip=True)
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
                                        found_any = True
                                    except: pass
                                break

            # 2. Търсене на Таблица
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
                                            found_any = True
                                        except: pass
                                    break
            
            if found_any:
                return prices
            else:
                # ДЕБЪГ: Принтираме заглавието на страницата, за да разберем защо няма данни
                page_title = soup.title.string.strip() if soup.title else "No Title"
                print(f"    > No prices found. Page title: '{page_title}'")
                time.sleep(random.uniform(2, 4)) # Пауза преди ретрай

        except Exception as e:
            print(f"    > Error: {e}")
            time.sleep(3)
    
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
            print(f"--- Processing {c_id} ---")
            
            # Взимаме първия URL (махнахме счупените backup-и)
            url = URLS[c_id][0]
            new_prices = scrape_url_with_retry(url, c_id, rates)
            
            if new_prices:
                new_prices['last_updated'] = datetime.now().strftime("%Y-%m-%d")
                country['fuel_prices'] = new_prices
                print(f"  > SUCCESS: Found {len(new_prices)} fuel types.")
                updated_count += 1
            else:
                print(f"  WARNING: Failed to fetch prices for {c_id}")
            
            time.sleep(random.uniform(3, 6))

    if updated_count > 0:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"GLOBAL SUCCESS: Updated fuel prices for {updated_count} countries.")
    else:
        print("NO UPDATES: No data was changed.")

if __name__ == "__main__":
    main()
