"""
Configuration file for WooCommerce Dashboard
"""
from dotenv import load_dotenv
load_dotenv()
import os
import streamlit as st

# Debug: Print environment variables to check if they are loaded
print("CK:", os.getenv('WOOCOMMERCE_CONSUMER_KEY'))
print("CS:", os.getenv('WOOCOMMERCE_CONSUMER_SECRET'))
print("URL:", os.getenv('WOOCOMMERCE_BASE_URL'))

# Also show in Streamlit for debugging
st.sidebar.write("**Debug - Environment Variables:**")
st.sidebar.write(f"Consumer Key: {'Set' if os.getenv('WOOCOMMERCE_CONSUMER_KEY') else 'Not Set'}")
st.sidebar.write(f"Consumer Secret: {'Set' if os.getenv('WOOCOMMERCE_CONSUMER_SECRET') else 'Not Set'}")
st.sidebar.write(f"Base URL: {'Set' if os.getenv('WOOCOMMERCE_BASE_URL') else 'Not Set'}")

# Try to get secrets from Streamlit's secrets management first, then fall back to environment variables
def get_secret(key, default=None):
    """Get secret from Streamlit secrets or environment variables"""
    # Try Streamlit secrets first
    if hasattr(st, 'secrets') and st.secrets:
        value = st.secrets.get(key)
        if value:
            return value
    
    # Fall back to environment variables
    return os.getenv(key, default)

# WooCommerce API Configuration
WOOCOMMERCE_CONFIG = {
    'base_url': get_secret('WOOCOMMERCE_BASE_URL', 'https://online.paideiainstitute.org'),
    'consumer_key': get_secret('WOOCOMMERCE_CONSUMER_KEY'),
    'consumer_secret': get_secret('WOOCOMMERCE_CONSUMER_SECRET')
}

# Debug Streamlit secrets
st.sidebar.write("**Debug - Streamlit Secrets:**")
st.sidebar.write(f"Consumer Key: {'Set' if get_secret('WOOCOMMERCE_CONSUMER_KEY') else 'Not Set'}")
st.sidebar.write(f"Consumer Secret: {'Set' if get_secret('WOOCOMMERCE_CONSUMER_SECRET') else 'Not Set'}")
st.sidebar.write(f"Base URL: {'Set' if get_secret('WOOCOMMERCE_BASE_URL') else 'Not Set'}")

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