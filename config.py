"""
Configuration file for WooCommerce Dashboard
"""
from dotenv import load_dotenv
load_dotenv()
import os

# Debug: Print environment variables to check if they are loaded
print("CK:", os.getenv('WOOCOMMERCE_CONSUMER_KEY'))
print("CS:", os.getenv('WOOCOMMERCE_CONSUMER_SECRET'))

# WooCommerce API Configuration
WOOCOMMERCE_CONFIG = {
    'base_url': os.getenv('WOOCOMMERCE_BASE_URL', 'https://online.paideiainstitute.org'),
    'consumer_key': os.getenv('WOOCOMMERCE_CONSUMER_KEY'),
    'consumer_secret': os.getenv('WOOCOMMERCE_CONSUMER_SECRET')
}

# App Configuration
APP_CONFIG = {
    'page_title': 'WooCommerce Dashboard',
    'page_icon': '🛒',
    'layout': 'wide',
    'cache_ttl': 300,  # 5 minutes
    'items_per_page': 50,
    'api_timeout': 60,  # Increased from 10 to 60 seconds
    'api_delay': 0.05,  # Reduced delay between API calls (from 0.1 to 0.05)
    'api_per_page': 100  # WooCommerce API maximum is 100 orders per request
}

# Data file paths
DATA_FILES = {
    'orders_json': 'Woo.json'
} 