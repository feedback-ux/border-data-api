import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

# --- КОНФИГУРАЦИЯ ---
# ПОПРАВКА: Вече сочи към главната директория, не към assets/
JSON_FILE = 'border_data.json' 
EXCHANGE_API = "https://api.frankfurter.app/latest?from=EUR"

# ... (Останалият код надолу е абсолютно същият) ...
# URL адреси за Fuelo (English version за по-лесно парсване)
URLS = {
    "BG": {"url": "https://bg.fuelo.net/gas-stations/by-country/bg?lang=en", "currency": "EUR"},
    "GR": {"url": "https://bg.fuelo.net/gas-stations/by-country/gr?lang=en", "currency": "EUR"},
    "RO": {"url": "https://bg.fuelo.net/gas-stations/by-country/ro?lang=en", "currency": "RON"},
    "TR": {"url": "https://bg.fuelo.net/gas-stations/by-country/tr?lang=en", "currency": "TRY"},
    "RS": {"url": "https://bg.fuelo.net/gas-stations/by-country/rs?lang=en", "currency": "RSD"},
    "MK": {"url": "https://bg.fuelo.net/gas-stations/by-country/mk?lang=en", "currency": "MKD"}
}

FUEL_MAPPING = {
    "Benzin A95": "gasoline",
    "Unleaded 95": "gasoline",
    "Diesel": "diesel",
    "Diesel Plus": "diesel_plus",
    "LPG": "lpg",
    "Autogas": "lpg",
    "Methane": "cng"
}

def get_exchange_rates():
    try:
        response = requests.get(EXCHANGE_API)
        data = response.json()
        return data.get('rates', {})
    except Exception as e:
        print(f"Error fetching exchange rates: {e}")
        return {}

def scrape_fuelo(country_code, url_info, rates):
    print(f"Scraping {country_code}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url_info['url'], headers=headers)
        if response.status_code != 200: return None

        soup = BeautifulSoup(response.content, 'html.parser')
        prices = {}
        rows = soup.find_all('tr')
        
        currency_code = url_info['currency']
        rate = 1.0
        if currency_code != "EUR":
            rate = rates.get(currency_code, 0)
            if rate == 0: return None

        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 2:
                fuel_name_raw = cols[0].get_text(strip=True)
                price_text = cols[1].get_text(strip=True).split(' ')[0]
                
                found_key = None
                for f_name, json_key in FUEL_MAPPING.items():
                    if f_name in fuel_name_raw:
                        found_key = json_key
                        break
                
                if found_key and found_key not in prices:
                    try:
                        price_local = float(price_text.replace(',', '.'))
                        if currency_code == "EUR":
                            price_eur = price_local
                        else:
                            price_eur = price_local / rate
                        prices[found_key] = round(price_eur, 2)
                    except ValueError: pass
        
        if prices:
            prices['last_updated'] = datetime.now().strftime("%Y-%m-%d")
            return prices
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
    
    if updated_count > 0:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Successfully updated fuel prices for {updated_count} countries.")
    else:
        print("No updates found.")

if __name__ == "__main__":
    main()
