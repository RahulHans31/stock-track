import os
import json
import requests
import psycopg2 # A simple, lightweight library for Postgres

# --- 1. CONFIGURATION ---
PINCODES_TO_CHECK = ['132001', '110016']

# Get secrets from GitHub
DATABASE_URL = os.environ.get('DATABASE_URL')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# --- 2. DATABASE: FETCH PRODUCTS ---
def get_products_from_db():
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    # Fetch all columns for all products
    cursor.execute("SELECT name, url, product_id, store_type FROM products")
    products = cursor.fetchall()
    conn.close()
    
    # Convert list of tuples to list of dicts
    products_list = [
        {"name": row[0], "url": row[1], "productId": row[2], "storeType": row[3]}
        for row in products
    ]
    print(f"Found {len(products_list)} products in the database.")
    return products_list

# --- 3. TELEGRAM SENDER ---
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets not set. Skipping message.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    requests.post(url, json=payload)

# --- 4. CROMA CHECKER ---
def check_croma(product, pincode):
    url = 'https://api.croma.com/inventory/oms/v2/tms/details-pwa/'
    payload = {"promise": {"allocationRuleID": "SYSTEM", "checkInventory": "Y", "organizationCode": "CROMA", "sourcingClassification": "EC", "promiseLines": {"promiseLine": [{"fulfillmentType": "HDEL", "itemID": product["productId"], "lineId": "1", "requiredQty": "1", "shipToAddress": {"zipCode": pincode}, "extn": {"widerStoreFlag": "N"}}]}}}
    headers = {'accept': 'application/json', 'content-type': 'application/json', 'oms-apim-subscription-key': '1131858141634e2abe2efb2b3a2a2a5d', 'origin': 'https://www.croma.com', 'referer': 'https://www.croma.com/'}
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        res.raise_for_status() # Raise error if status is not 200
        data = res.json()
        if data.get("promise", {}).get("suggestedOption", {}).get("option", {}).get("promiseLines", {}).get("promiseLine"):
            return f'✅ *In Stock at Croma ({pincode})*\n[{product["name"]}]({product["url"]})'
    except Exception as e:
        print(f'Error checking Croma ({product["name"]}): {e}')
    return None

# --- 5. FLIPKART CHECKER (Your exact working code) ---
def check_flipkart(product, pincode):
    url = "https://2.rome.api.flipkart.com/api/3/product/serviceability"
    payload = {
        "requestContext": {"products": [{"productId": product["productId"]}]},
        "locationContext": {"pincode": pincode}
    }
    # Your exact headers
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "Origin": "https://www.flipkart.com",
        "Referer": "https://www.flipkart.com/",
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
        "X-User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36 FKUA/msite/0.0.3/msite/Mobile",
        "flipkart_secure": "true",
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        res.raise_for_status() # Raise error if status is not 200
        data = res.json()
        listing = data.get("RESPONSE", {}).get(product["productId"], {}).get("listingSummary", {})
        
        if listing.get("serviceable") is True and listing.get("available") is True:
            return f'✅ *In Stock at Flipkart ({pincode})*\n[{product["name"]}]({product["url"]})'
    except Exception as e:
        print(f'Error checking Flipkart ({product["name"]}): {e}')
    return None

# --- 6. MAIN SCRIPT ---
def main():
    print("Starting stock check...")
    try:
        products_to_track = get_products_from_db()
    except Exception as e:
        print(f"Failed to fetch products from database: {e}")
        send_telegram_message(f"❌ Your checker script failed to connect to the database.")
        return

    in_stock_messages = []
    
    # We don't need ThreadPoolExecutor for 4 products, this is simpler
    for product in products_to_track:
        for pincode in PINCODES_TO_CHECK:
            result = None
            if product["storeType"] == 'croma':
                result = check_croma(product, pincode)
            elif product["storeType"] == 'flipkart':
                result = check_flipkart(product, pincode)
            
            if result:
                in_stock_messages.append(result)

    if in_stock_messages:
        print(f"Found {len(in_stock_messages)} items in stock. Sending Telegram message.")
        final_message = "🔥 *Stock Alert!*\n\n" + "\n\n".join(in_stock_messages)
        send_telegram_message(final_message)
    else:
        print("All items out of stock. No message sent.")

if __name__ == "__main__":
    main()