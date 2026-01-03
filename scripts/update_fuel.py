import json
import cloudscraper # НОВО: Заобикаля защитите
from bs4 import BeautifulSoup
from datetime import datetime
import os
import time

# --- КОНФИГУРАЦИЯ ---
JSON_FILE = 'border_data.json' 
EXCHANGE_API = "https://api.frankfurter.app/latest?from=EUR"

# НОВИ URL адреси (директно към страниците с цени)
URLS = {
    "BG": {"url": "https://bg.fuelo.net/prices?lang=en", "currency": "EUR"}, 
    "GR": {"url": "https://gr.fuelo.net/prices?lang=en", "currency": "EUR"},
    "RO": {"url": "https://ro.fuelo.net/prices?lang=en", "currency": "RON"},
    "TR": {"url": "https://tr.fuelo.net/prices?lang=en", "currency": "TRY"},
    "RS": {"url": "https://rs.fuelo.net/prices?lang=en", "currency": "RSD"},
    "MK": {"url": "https://mk.fuelo.net/prices?lang=en", "currency": "MKD"}
}

FUEL_MAPPING = {
    "Benzin A95": "gasoline",
    "Unleaded 95": "gasoline",
    "Gasoline A95": "gasoline",
    "Diesel": "diesel",
    "LPG": "lpg",
    "Autogas": "lpg",
    "Methane": "cng"
}

def get_exchange_rates():
    """Взима актуалните валутни курсове спрямо EUR"""
    scraper = cloudscraper.create_scraper()
    try:
        response = scraper.get(EXCHANGE_API)
        data = response.json()
        print("Exchange rates loaded successfully.")
        return data.get('rates', {})
    except Exception as e:
        print(f"Error fetching exchange rates: {e}")
        return {}

def scrape_fuelo(country_code, url_info, rates):
    """Чегърта цените от Fuelo и ги обръща в EUR"""
    print(f"--- Processing {country_code} ---")
    scraper = cloudscraper.create_scraper() # Използваме cloudscraper
    
    try:
        response = scraper.get(url_info['url'])
        if response.status_code != 200:
            print(f"FAILED: Status code {response.status_code}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')
        prices = {}
        
        # Fuelo /prices page usually has cards or a table
        # Търсим всички елементи, които съдържат цени
        # Структурата често е <div>...<h4>Fuel Name</h4>...<span itemprop="price">...</span></div>
        
        # Опит 1: Търсене по meta тагове (най-сигурно)
        # Опит 2: Търсене в таблица
        rows = soup.find_all('tr')
        
        currency_code = url_info['currency']
        rate = 1.0
        
        if currency_code != "EUR":
            rate = rates.get(currency_code, 0)
            if rate == 0:
                print(f"Skipping: No rate for {currency_code}")
                return None

        found_any = False
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 2:
                # Изчистваме текста
                fuel_name_raw = cols[0].get_text(strip=True)
                price_raw = cols[1].get_text(strip=True)
                
                # Пример: "2.55 лв./л" -> взимаме "2.55"
                import re
                price_match = re.search(r"([0-9]+[.,][0-9]+)", price_raw)
                
                if price_match:
                    price_text = price_match.group(1).replace(',', '.')
                else:
                    continue

                # Проверяваме името
                for f_name, json_key in FUEL_MAPPING.items():
                    if f_name.lower() in fuel_name_raw.lower():
                        try:
                            price_local = float(price_text)
                            
                            if currency_code == "EUR":
                                price_eur = price_local
                            else:
                                price_eur = price_local / rate
                            
                            final_price = round(price_eur, 2)
                            prices[json_key] = final_price
                            print(f"  > Found {json_key}: {final_price} EUR (local: {price_local} {currency_code})")
                            found_any = True
                        except ValueError:
                            pass
                        break # Намерихме мапинг за този ред, спираме
        
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
                # Запазваме старите данни, ако скриптът се провали частично
                country['fuel_prices'] = new_prices
                updated_count += 1
            time.sleep(1) # Пауза да не претоварваме сайта
    
    if updated_count > 0:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"SUCCESS: Updated fuel prices for {updated_count} countries.")
    else:
        print("NO UPDATES: No data was changed.")

if __name__ == "__main__":
    main()
