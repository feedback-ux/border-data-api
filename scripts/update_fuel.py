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

# URL адреси - използваме началните страници, където са кутиите с цени
URLS = {
    # За България вече взимаме EUR директно от сайта (според HTML-а ти)
    "BG": {"url": "https://bg.fuelo.net/?lang=en", "currency": "EUR"},
    "GR": {"url": "https://gr.fuelo.net/?lang=en", "currency": "EUR"},
    "RO": {"url": "https://ro.fuelo.net/?lang=en", "currency": "RON"},
    "TR": {"url": "https://tr.fuelo.net/?lang=en", "currency": "TRY"},
    "RS": {"url": "https://rs.fuelo.net/?lang=en", "currency": "RSD"},
    "MK": {"url": "https://mk.fuelo.net/?lang=en", "currency": "MKD"}
}

FUEL_MAPPING = {
    "Benzin A95": "gasoline",
    "Unleaded 95": "gasoline",
    "Gasoline A95": "gasoline",
    "A95": "gasoline",
    "Diesel": "diesel",
    "Diesel Premium": "diesel_plus",
    "LPG": "lpg",
    "Autogas": "lpg",
    "Methane": "cng",
    "CNG": "cng"
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
        else:
            print(f"API Error: {response.status_code}")
    except Exception as e:
        print(f"Error fetching exchange rates: {e}")

    # Fallback курсове
    if 'RSD' not in rates: rates['RSD'] = 117.2
    if 'MKD' not in rates: rates['MKD'] = 61.6
    if 'TRY' not in rates: rates['TRY'] = 35.0 # Приблизително, API-то трябва да го хване
    
    return rates

def scrape_fuelo(country_code, url_info, rates):
    print(f"--- Processing {country_code} ---")
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(url_info['url'])
        if response.status_code != 200:
            print(f"FAILED: Status code {response.status_code}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')
        prices = {}
        
        # Търсим всички кутии с класове "box"
        boxes = soup.find_all('div', class_=lambda x: x and 'box' in x.split())
        
        currency_code = url_info['currency']
        rate = 1.0
        
        if currency_code != "EUR":
            rate = rates.get(currency_code, 0)
            if rate == 0:
                print(f"Skipping: No rate for {currency_code}")
                return None

        found_any = False
        
        for box in boxes:
            # 1. Търсим името на горивото (h2)
            h2 = box.find('h2')
            if not h2: continue
            fuel_name_raw = h2.get_text(strip=True)
            
            # 2. Търсим цената (h3 -> span)
            h3 = box.find('h3')
            if not h3: continue
            price_raw = h3.get_text(strip=True) # "1,25 € +0.00€"

            # 3. Извличаме числото (първото срещнато число с десетична запетая/точка)
            price_match = re.search(r"([0-9]+[.,][0-9]+)", price_raw)
            if not price_match: continue
            
            price_text = price_match.group(1).replace(',', '.')

            # 4. Проверяваме кое гориво е това
            for f_name, json_key in FUEL_MAPPING.items():
                if f_name.lower() in fuel_name_raw.lower():
                    try:
                        price_local = float(price_text)
                        
                        # Превалутиране
                        if currency_code == "EUR":
                            price_eur = price_local
                        else:
                            price_eur = price_local / rate
                        
                        final_price = round(price_eur, 2)
                        
                        # Записваме (само ако го няма или обновяваме)
                        prices[json_key] = final_price
                        print(f"  > Found {json_key}: {final_price} EUR (local: {price_local} {currency_code})")
                        found_any = True
                    except ValueError:
                        pass
                    break # Спираме търсенето на име за тази кутия

        if found_any:
            prices['last_updated'] = datetime.now().strftime("%Y-%m-%d")
            return prices
        else:
            print(f"WARNING: No fuel prices found in HTML for {country_code}")
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
            time.sleep(1) # Пауза между заявките
    
    if updated_count > 0:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"SUCCESS: Updated fuel prices for {updated_count} countries.")
    else:
        print("NO UPDATES: No data was changed.")

if __name__ == "__main__":
    main()
