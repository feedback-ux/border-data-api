import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

# --- КОНФИГУРАЦИЯ ---
JSON_FILE = 'assets/border_data.json' # Пътят до твоя JSON файл
EXCHANGE_API = "https://api.frankfurter.app/latest?from=EUR"

# URL адреси за Fuelo (English version за по-лесно парсване)
URLS = {
    "BG": {"url": "https://bg.fuelo.net/gas-stations/by-country/bg?lang=en", "currency": "EUR"}, # Вече сме в Еврозоната
    "GR": {"url": "https://bg.fuelo.net/gas-stations/by-country/gr?lang=en", "currency": "EUR"},
    "RO": {"url": "https://bg.fuelo.net/gas-stations/by-country/ro?lang=en", "currency": "RON"},
    "TR": {"url": "https://bg.fuelo.net/gas-stations/by-country/tr?lang=en", "currency": "TRY"},
    "RS": {"url": "https://bg.fuelo.net/gas-stations/by-country/rs?lang=en", "currency": "RSD"},
    "MK": {"url": "https://bg.fuelo.net/gas-stations/by-country/mk?lang=en", "currency": "MKD"}
}

# Мапинг на имената на горивата (Fuelo Name -> Our JSON Key)
FUEL_MAPPING = {
    "Benzin A95": "gasoline",
    "Unleaded 95": "gasoline",
    "Diesel": "diesel",
    "Diesel Plus": "diesel_plus", # Опционално
    "LPG": "lpg",
    "Autogas": "lpg",
    "Methane": "cng"
}

def get_exchange_rates():
    """Взима актуалните валутни курсове спрямо EUR"""
    try:
        response = requests.get(EXCHANGE_API)
        data = response.json()
        return data.get('rates', {})
    except Exception as e:
        print(f"Error fetching exchange rates: {e}")
        return {}

def scrape_fuelo(country_code, url_info, rates):
    """Чегърта цените от Fuelo и ги обръща в EUR"""
    print(f"Scraping {country_code}...")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url_info['url'], headers=headers)
        if response.status_code != 200:
            print(f"Failed to load URL for {country_code}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')
        prices = {}
        
        # Fuelo обикновено има таблица с цени. Търсим редовете.
        # Този селектор може да се нуждае от актуализация ако Fuelo сменят дизайна
        rows = soup.find_all('tr')
        
        currency_code = url_info['currency']
        rate = 1.0
        
        # Ако валутата не е EUR, намираме курса
        if currency_code != "EUR":
            rate = rates.get(currency_code, 0)
            if rate == 0:
                print(f"Warning: No exchange rate found for {currency_code}. Skipping conversion.")
                return None

        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 2:
                fuel_name_raw = cols[0].get_text(strip=True)
                price_text = cols[1].get_text(strip=True).split(' ')[0] # Взимаме само числото "2.55 lv" -> "2.55"
                
                # Проверяваме дали това гориво ни трябва
                found_key = None
                for f_name, json_key in FUEL_MAPPING.items():
                    if f_name in fuel_name_raw:
                        found_key = json_key
                        break
                
                if found_key and found_key not in prices:
                    try:
                        price_local = float(price_text.replace(',', '.'))
                        # ПРЕВАЛУТИРАНЕ: Цена в местна валута / Курс = Цена в Евро
                        # Пример: 45 TRY / 30 (Rate) = 1.50 EUR
                        if currency_code == "EUR":
                            price_eur = price_local
                        else:
                            price_eur = price_local / rate
                            
                        prices[found_key] = round(price_eur, 2)
                    except ValueError:
                        pass
        
        if prices:
            prices['last_updated'] = datetime.now().strftime("%Y-%m-%d")
            return prices
        return None

    except Exception as e:
        print(f"Error scraping {country_code}: {e}")
        return None

def main():
    # 1. Зареждаме JSON файла
    if not os.path.exists(JSON_FILE):
        print(f"File {JSON_FILE} not found!")
        return

    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 2. Взимаме курсовете
    rates = get_exchange_rates()
    
    # 3. Обхождаме държавите и обновяваме цените
    updated_count = 0
    
    for country in data.get('countries', []):
        c_id = country.get('id')
        if c_id in URLS:
            new_prices = scrape_fuelo(c_id, URLS[c_id], rates)
            if new_prices:
                country['fuel_prices'] = new_prices
                updated_count += 1
    
    # 4. Записваме промените само ако има такива
    if updated_count > 0:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Successfully updated fuel prices for {updated_count} countries.")
    else:
        print("No updates found.")

if __name__ == "__main__":
    main()
