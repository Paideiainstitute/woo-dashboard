# WooCommerce Streamlit Dashboard

A modern, interactive dashboard for WooCommerce order data built with Streamlit.

## Features

- **📊 Real-time Dashboard**: View key metrics, recent orders, and charts
- **📋 Order Management**: Browse, filter, and search all orders with pagination
- **📈 Analytics**: Customer analysis and product performance
- **🔄 Data Refresh**: One-click refresh from WooCommerce API
- **⚡ Fast & Responsive**: Built with Streamlit for smooth interactions
- **🔒 Secure**: Environment variable support for API credentials

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment variables** (recommended for security):
   ```bash
   # Copy the example and fill in your values
   cp env_example.txt .env
   # Edit .env with your actual WooCommerce API credentials
   ```

3. **Activate the virtual environment**:
   ```bash
   source venv/bin/activate
   ```

4. **Run the Streamlit app**:
   ```bash
   streamlit run streamlit_app.py
   ```

5. **Open your browser** to the URL shown (usually `http://localhost:8501`)

## Security Best Practices

⚠️ **Important**: The app currently has hardcoded API credentials as fallbacks. For production use:

1. **Use environment variables**:
   ```bash
   export WOOCOMMERCE_BASE_URL="https://your-store.com"
   export WOOCOMMERCE_CONSUMER_KEY="ck_your_key_here"
   export WOOCOMMERCE_CONSUMER_SECRET="cs_your_secret_here"
   ```

2. **Or create a .env file**:
   ```bash
   cp env_example.txt .env
   # Edit .env with your credentials
   ```

3. **Never commit API credentials** to version control

## Navigation

The dashboard has four main sections:

### 🏠 Dashboard
- Key metrics (revenue, orders, customers)
- Recent orders table
- Order status breakdown chart
- Top products by revenue

### 📋 Orders
- Complete order list with filtering and pagination
- Search by customer name or email
- Filter by order status
- Sort by date (newest first)
- 50 orders per page by default

### 📊 Analytics
- Top customers by revenue
- Customer order analysis
- Product performance insights

### 🔄 Refresh Data
- Fetch latest orders from WooCommerce API
- Progress tracking during refresh
- Automatic cache clearing

## Configuration

The app uses a centralized configuration system:

- **config.py**: Main configuration file
- **Environment variables**: For API credentials (recommended)
- **Hardcoded fallbacks**: For development (not recommended for production)

### Customizing Settings

Edit `config.py` to modify:
- Cache duration (default: 5 minutes)
- Items per page (default: 50)
- API timeout (default: 10 seconds)
- API delay between calls (default: 0.1 seconds)

## Troubleshooting

- **No data showing**: Click "Refresh Data" to fetch from API
- **Slow loading**: Data is cached for 5 minutes, refresh to get latest
- **API errors**: Check your WooCommerce API keys and permissions
- **Memory issues**: Reduce `items_per_page` in config.py for large datasets

## Performance Improvements

The app includes several performance optimizations:
- **Caching**: 5-minute cache for order data
- **Pagination**: 50 orders per page to handle large datasets
- **Error handling**: Graceful handling of malformed data
- **Progress indicators**: Visual feedback during data operations

## Next Steps

This Streamlit version is much more reliable and easier to maintain than the Flask version. You can now:

1. Use this as your primary dashboard
2. Add more analytics features easily
3. Deploy to Streamlit Cloud for web access
4. Customize the styling and layout
5. Add more security features

The Flask version can be kept as a backup, but Streamlit is definitely the better choice for this type of data dashboard! 