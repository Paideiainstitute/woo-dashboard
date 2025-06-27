import streamlit as st
import pandas as pd
import plotly.express as px
import json
import requests
import base64
import time
import os
from datetime import datetime
from collections import defaultdict, Counter
from config import WOOCOMMERCE_CONFIG, APP_CONFIG, DATA_FILES

# Try to import streamlit-authenticator, fallback to simple auth if it fails
try:
    import streamlit_authenticator as stauth
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    st.warning("streamlit-authenticator not available, using simple authentication")

# Page configuration
st.set_page_config(
    page_title=APP_CONFIG['page_title'],
    page_icon=APP_CONFIG['page_icon'],
    layout=APP_CONFIG['layout']
)

# Authentication setup - using simple authentication for reliability
if not st.session_state.get('authenticated', False):
    st.title("🔐 WooCommerce Dashboard Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == "Paideia" and password == "Admin":
            st.success("Login successful!")
            st.session_state.authenticated = True
            st.rerun()  # Rerun to show the dashboard
        else:
            st.error("Invalid username or password")
            st.stop()
    st.stop()  # Only stops if not authenticated

# Check if API keys are configured (after authentication)
if not WOOCOMMERCE_CONFIG['consumer_key'] or not WOOCOMMERCE_CONFIG['consumer_secret']:
    st.error("""
    **API Keys Not Configured**
    
    Please set the following environment variables:
    - `WOOCOMMERCE_CONSUMER_KEY`
    - `WOOCOMMERCE_CONSUMER_SECRET`
    
    For local development, create a `.env` file with:
    ```
    WOOCOMMERCE_CONSUMER_KEY=your_consumer_key_here
    WOOCOMMERCE_CONSUMER_SECRET=your_consumer_secret_here
    ```
    
    For Streamlit Cloud, add these in the app's Secrets section.
    """)
    st.stop()

# If authenticated and API keys are configured, show the dashboard
st.success("Welcome Paideia!")

@st.cache_data(ttl=APP_CONFIG['cache_ttl'])  # Cache for 5 minutes
def load_orders():
    """Load orders from JSON file with caching"""
    try:
        with open(DATA_FILES['orders_json'], "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        return []

def get_latest_order_date(orders):
    """Get the most recent order date from existing orders"""
    if not orders:
        return None
    
    latest_date = None
    for order in orders:
        date_str = order.get('date_created')
        if not date_str:
            continue
        try:
            if 'T' in date_str:
                date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
            else:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            
            if latest_date is None or date_obj > latest_date:
                latest_date = date_obj
        except Exception:
            continue
    
    return latest_date

def merge_orders(existing_orders, new_orders):
    """Merge new orders with existing orders, keeping the most recent version of each order"""
    # Create a dictionary of existing orders by ID for quick lookup
    existing_dict = {order['id']: order for order in existing_orders}
    
    # Update with new orders (newer orders will overwrite older ones)
    for new_order in new_orders:
        existing_dict[new_order['id']] = new_order
    
    # Convert back to list and sort by date (newest first)
    merged_orders = list(existing_dict.values())
    merged_orders.sort(key=lambda x: x.get('date_created', ''), reverse=True)
    
    return merged_orders

def fetch_orders_from_api(incremental=True):
    """Fetch orders from WooCommerce API with incremental update support"""
    import math
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    api_url = f"{WOOCOMMERCE_CONFIG['base_url']}/wp-json/wc/v3/orders"
    credentials = f"{WOOCOMMERCE_CONFIG['consumer_key']}:{WOOCOMMERCE_CONFIG['consumer_secret']}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json",
        "User-Agent": "curl/8.7.1"
    }
    
    # Load existing orders for incremental update
    existing_orders = []
    if incremental:
        try:
            with open(DATA_FILES['orders_json'], "r") as f:
                existing_orders = json.load(f)
        except FileNotFoundError:
            pass
    
    # Get the latest order date for incremental fetching
    latest_date = get_latest_order_date(existing_orders)
    
    # Configure retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    all_new_orders = []
    page = 1
    per_page = APP_CONFIG.get('api_per_page', 100)
    total_orders_est = None
    start_time = time.time()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    count_text = st.empty()
    timing_text = st.empty()
    
    try:
        while True:
            if incremental and latest_date:
                status_text.text(f"Fetching new orders since {latest_date.strftime('%Y-%m-%d %H:%M')} (Page {page})...")
            else:
                status_text.text(f"Fetching all orders (Page {page})...")
            
            params = {
                "per_page": per_page,
                "page": page,
                "orderby": "date",
                "order": "desc"
            }
            
            # Add date filter for incremental updates
            if incremental and latest_date:
                params["after"] = latest_date.strftime("%Y-%m-%dT%H:%M:%S")
            
            try:
                response = session.get(api_url, headers=headers, params=params, timeout=APP_CONFIG['api_timeout'])
            except requests.exceptions.Timeout:
                return False, f"Request timed out after {APP_CONFIG['api_timeout']} seconds. The server is taking too long to respond."
            except requests.exceptions.ConnectionError:
                return False, "Connection error. Please check your internet connection and try again."
            except requests.exceptions.RequestException as e:
                return False, f"Network error: {str(e)}"
            
            if response.status_code == 200:
                # Try to get total count from headers (if available)
                if total_orders_est is None:
                    total_header = response.headers.get('X-WP-Total')
                    if total_header:
                        try:
                            total_orders_est = int(total_header)
                        except Exception:
                            total_orders_est = None
                
                orders = response.json()
                if not orders:
                    break
                
                all_new_orders.extend(orders)
                
                # Progress info with timing estimates
                fetched = len(all_new_orders)
                elapsed = time.time() - start_time
                
                if total_orders_est:
                    percent = min(fetched / total_orders_est, 1.0)
                    progress_bar.progress(percent)
                    count_text.text(f"Fetched {fetched:,} new orders (Page {page})")
                    
                    # Estimate remaining time
                    if fetched > 0 and elapsed > 0:
                        rate = fetched / elapsed
                        remaining = total_orders_est - fetched
                        eta_seconds = remaining / rate if rate > 0 else 0
                        eta_minutes = eta_seconds / 60
                        timing_text.text(f"Rate: {rate:.1f} orders/sec | Elapsed: {elapsed:.0f}s | ETA: {eta_minutes:.1f} minutes")
                else:
                    progress = min(page / 50, 1.0)
                    progress_bar.progress(progress)
                    count_text.text(f"Fetched {fetched:,} new orders (Page {page})")
                    
                    if fetched > 0 and elapsed > 0:
                        rate = fetched / elapsed
                        timing_text.text(f"Rate: {rate:.1f} orders/sec | Elapsed: {elapsed:.0f}s")
                
                if len(orders) < per_page:
                    break
                page += 1
                time.sleep(APP_CONFIG['api_delay'])
            else:
                return False, f"API Error: Status code {response.status_code} - {response.text[:200]}"
        
        # Merge and save data
        status_text.text("Merging and saving data...")
        with st.spinner("Merging and saving data..."):
            if all_new_orders or existing_orders:
                # Merge new orders with existing ones
                if incremental and existing_orders:
                    merged_orders = merge_orders(existing_orders, all_new_orders)
                    total_orders = len(merged_orders)
                    new_count = len(all_new_orders)
                else:
                    merged_orders = all_new_orders
                    total_orders = len(merged_orders)
                    new_count = total_orders
                
                with open(DATA_FILES['orders_json'], "w") as f:
                    json.dump(merged_orders, f, indent=2)
                
                progress_bar.empty()
                status_text.empty()
                count_text.empty()
                timing_text.empty()
                elapsed = time.time() - start_time
                
                if incremental and new_count > 0:
                    st.success(f"Updated {new_count:,} new orders. Total: {total_orders:,} orders in {elapsed:.1f} seconds.")
                    return True, f"Updated {new_count:,} new orders. Total: {total_orders:,} orders in {elapsed:.1f} seconds."
                elif incremental:
                    st.success(f"No new orders found. Total: {total_orders:,} orders.")
                    return True, f"No new orders found. Total: {total_orders:,} orders."
                else:
                    st.success(f"Successfully updated {total_orders:,} orders in {elapsed:.1f} seconds.")
                    return True, f"Successfully updated {total_orders:,} orders in {elapsed:.1f} seconds."
            else:
                progress_bar.empty()
                status_text.empty()
                count_text.empty()
                timing_text.empty()
                return False, "No orders found"
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        count_text.empty()
        timing_text.empty()
        return False, f"Error: {str(e)}"

def calculate_stats(orders):
    """Calculate statistics from orders"""
    if not orders:
        return {}
    
    completed_orders = [o for o in orders if o.get('status') == 'completed']
    refunded_orders = [o for o in orders if o.get('status') == 'refunded']
    
    # Validate order data
    valid_orders = []
    for order in orders:
        if isinstance(order, dict) and 'total' in order:
            try:
                float(order['total'])
                valid_orders.append(order)
            except (ValueError, TypeError):
                continue
    
    stats = {
        'total_orders': len(valid_orders),
        'total_revenue': sum(float(order['total']) for order in completed_orders if order in valid_orders),
        'refunded_amount': sum(float(order['total']) for order in refunded_orders if order in valid_orders),
        'completed_orders': len(completed_orders),
        'refunded_orders': len(refunded_orders),
        'customer_count': len(set(order.get('customer_id', 0) for order in valid_orders)),
        'revenue_by_product': defaultdict(float),
        'status_breakdown': Counter(order.get('status', 'unknown') for order in valid_orders)
    }
    
    # Calculate average order value
    if completed_orders:
        stats['avg_order_value'] = stats['total_revenue'] / len(completed_orders)
    else:
        stats['avg_order_value'] = 0
    
    # Product analysis
    for order in completed_orders:
        if order in valid_orders:
            for item in order.get('line_items', []):
                if isinstance(item, dict) and 'name' in item and 'total' in item:
                    try:
                        product_name = item['name']
                        product_revenue = float(item['total'])
                        stats['revenue_by_product'][product_name] += product_revenue
                    except (ValueError, TypeError):
                        continue
    
    return stats

def get_fiscal_year(date):
    """Return the fiscal year for a given date (September 1 - August 31)."""
    # Fiscal year starts September 1
    if date.month >= 9:
        return date.year + 1
    else:
        return date.year

def filter_orders_fiscal_year(orders, fiscal_year):
    """Filter orders to those in the given fiscal year (September 1 - August 31)."""
    filtered = []
    for order in orders:
        date_str = order.get('date_created')
        if not date_str:
            continue
        try:
            if 'T' in date_str:
                date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
            else:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            if get_fiscal_year(date_obj) == fiscal_year:
                filtered.append(order)
        except Exception:
            continue
    return filtered

def aggregate_product_fiscal_year(orders):
    """Aggregate revenue and order count per product for the given orders, separating individual/group and new/recurring orders."""
    product_revenue = defaultdict(float)
    product_order_count = defaultdict(int)
    product_individual_revenue = defaultdict(float)
    product_group_revenue = defaultdict(float)
    product_individual_count = defaultdict(int)
    product_group_count = defaultdict(int)
    
    # New vs recurring tracking
    product_new_revenue = defaultdict(float)
    product_recurring_revenue = defaultdict(float)
    product_new_count = defaultdict(int)
    product_recurring_count = defaultdict(int)
    
    for order in orders:
        if order.get('status') != 'completed':
            continue
        
        products_in_order = set()
        order_total = float(order.get('total', 0))
        created_via = order.get('created_via', 'checkout')
        is_recurring = created_via == 'subscription'
        
        for item in order.get('line_items', []):
            if isinstance(item, dict) and 'name' in item and 'total' in item:
                try:
                    product_name = item['name']
                    product_revenue[product_name] += float(item['total'])
                    products_in_order.add(product_name)
                except Exception:
                    continue
        
        # Determine if this is an individual or group order based on total amount
        is_group_order = order_total > 200  # Adjust this threshold as needed
        
        for pname in products_in_order:
            product_order_count[pname] += 1
            
            # Individual vs Group tracking
            if is_group_order:
                product_group_revenue[pname] += float(order.get('total', 0))
                product_group_count[pname] += 1
            else:
                product_individual_revenue[pname] += float(order.get('total', 0))
                product_individual_count[pname] += 1
            
            # New vs Recurring tracking
            if is_recurring:
                product_recurring_revenue[pname] += float(order.get('total', 0))
                product_recurring_count[pname] += 1
            else:
                product_new_revenue[pname] += float(order.get('total', 0))
                product_new_count[pname] += 1
    
    return (product_revenue, product_order_count, 
            product_individual_revenue, product_group_revenue,
            product_individual_count, product_group_count,
            product_new_revenue, product_recurring_revenue,
            product_new_count, product_recurring_count)

def analyze_course_orders(orders, course_name):
    """Analyze orders for a specific course with detailed breakdowns using actual product data"""
    course_orders = []
    
    for order in orders:
        if order.get('status') != 'completed':
            continue
        
        # Check if this order contains the specific course
        order_contains_course = False
        for item in order.get('line_items', []):
            if isinstance(item, dict) and 'name' in item:
                # Check if course name appears in the product name
                if course_name.lower() in item['name'].lower():
                    order_contains_course = True
                    break
        
        if order_contains_course:
            course_orders.append(order)
    
    if not course_orders:
        return None
    
    # Analyze the course orders
    total_orders = len(course_orders)
    total_revenue = sum(float(order.get('total', 0)) for order in course_orders)
    
    # New vs Recurring
    new_orders = [o for o in course_orders if o.get('created_via') != 'subscription']
    recurring_orders = [o for o in course_orders if o.get('created_via') == 'subscription']
    new_revenue = sum(float(order.get('total', 0)) for order in new_orders)
    recurring_revenue = sum(float(order.get('total', 0)) for order in recurring_orders)
    
    # Individual vs Group and detailed breakdowns
    individual_orders = []
    group_orders = []
    individual_monthly = []
    individual_annual = []
    group_by_seats = {}
    
    for order in course_orders:
        for item in order.get('line_items', []):
            if isinstance(item, dict) and 'name' in item:
                item_name = item['name']
                
                # Check if this item is for the course we're analyzing
                if course_name.lower() in item_name.lower():
                    # Determine if individual or group based on product name
                    if 'individual' in item_name.lower():
                        individual_orders.append(order)
                        
                        # Determine monthly vs annual based on payment term or product name
                        payment_term = None
                        for meta in item.get('meta_data', []):
                            if meta.get('key') == 'payment-term':
                                payment_term = meta.get('value', '').lower()
                                break
                        
                        if payment_term == 'monthly' or 'monthly' in item_name.lower():
                            individual_monthly.append(order)
                        elif payment_term == 'annual' or 'annual' in item_name.lower():
                            individual_annual.append(order)
                    
                    elif 'group' in item_name.lower() or 'seats' in item_name.lower():
                        group_orders.append(order)
                        
                        # Extract seat count from product name
                        import re
                        seat_match = re.search(r'(\d+)\s*seats?', item_name.lower())
                        if seat_match:
                            seats = int(seat_match.group(1))
                        else:
                            # Fallback: estimate seats based on total
                            order_total = float(order.get('total', 0))
                            if order_total <= 300:
                                seats = 2
                            elif order_total <= 500:
                                seats = 4
                            elif order_total <= 700:
                                seats = 6
                            elif order_total <= 900:
                                seats = 8
                            else:
                                seats = 10
                        
                        if seats not in group_by_seats:
                            group_by_seats[seats] = []
                        group_by_seats[seats].append(order)
    
    # Remove duplicates from lists (same order might have multiple line items)
    # Use order IDs to remove duplicates since dictionaries aren't hashable
    individual_order_ids = list(set(order['id'] for order in individual_orders))
    group_order_ids = list(set(order['id'] for order in group_orders))
    individual_monthly_ids = list(set(order['id'] for order in individual_monthly))
    individual_annual_ids = list(set(order['id'] for order in individual_annual))
    
    # Get the actual orders back using the unique IDs
    individual_orders = [order for order in course_orders if order['id'] in individual_order_ids]
    group_orders = [order for order in course_orders if order['id'] in group_order_ids]
    individual_monthly = [order for order in course_orders if order['id'] in individual_monthly_ids]
    individual_annual = [order for order in course_orders if order['id'] in individual_annual_ids]
    
    return {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'new_orders': len(new_orders),
        'new_revenue': new_revenue,
        'recurring_orders': len(recurring_orders),
        'recurring_revenue': recurring_revenue,
        'individual_orders': len(individual_orders),
        'individual_monthly': len(individual_monthly),
        'individual_annual': len(individual_annual),
        'individual_revenue': sum(float(o.get('total', 0)) for o in individual_orders),
        'group_orders': len(group_orders),
        'group_by_seats': group_by_seats,
        'group_revenue': sum(float(o.get('total', 0)) for o in group_orders)
    }

def main():
    # Header
    st.title("🛒 WooCommerce Dashboard")
    
    # Sidebar
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox(
        "Choose a page",
        ["Dashboard", "Monthly Sales", "Users", "Refresh Data"]
    )
    
    # Refresh options
    st.sidebar.subheader("🔄 Data Refresh")
    incremental_refresh = st.sidebar.checkbox("Incremental Update (faster)", value=True, 
                                             help="Only fetch new orders since last update")
    
    # Refresh data button in sidebar
    if st.sidebar.button("🔄 Refresh Data", type="primary"):
        with st.spinner("Fetching latest orders..."):
            success, message = fetch_orders_from_api(incremental=incremental_refresh)
            if success:
                st.sidebar.success(message)
                st.cache_data.clear()  # Clear cache to reload data
            else:
                st.sidebar.error(message)
    
    # Load data
    orders = load_orders()
    
    if not orders:
        st.error("No orders found. Please refresh the data or check if Woo.json exists.")
        return
    
    stats = calculate_stats(orders)
    
    if page == "Dashboard":
        show_dashboard(orders, stats)
    elif page == "Monthly Sales":
        show_monthly_sales(orders)
    elif page == "Users":
        show_users(orders)
    elif page == "Refresh Data":
        show_refresh_page()

def show_dashboard(orders, stats):
    """Main dashboard view with course-by-course breakdown"""
    
    # Key metrics at the top
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("💰 Total Revenue", f"${stats['total_revenue']:,.2f}")
    
    with col2:
        st.metric("✅ Completed Orders", f"{stats['completed_orders']:,}")
    
    with col3:
        st.metric("📊 Avg Order Value", f"${stats['avg_order_value']:.2f}")
    
    with col4:
        st.metric("👥 Total Customers", f"{stats['customer_count']:,}")
    
    # Date range info - show fiscal year period instead of entire data range
    today = datetime.today()
    current_fy = get_fiscal_year(today)
    
    # Calculate fiscal year start and end dates
    if today.month >= 9:
        # Current fiscal year started in September of previous year
        fy_start = datetime(today.year - 1, 9, 1)
        fy_end = datetime(today.year, 8, 31)
    else:
        # Current fiscal year started in September of current year
        fy_start = datetime(today.year, 9, 1)
        fy_end = datetime(today.year + 1, 8, 31)
    
    st.info(f"📅 Fiscal Year {current_fy} Period: {fy_start.strftime('%Y-%m-%d')} to {fy_end.strftime('%Y-%m-%d')} (September 1 - August 31)")
    
    # Fiscal year summary
    fy_orders = filter_orders_fiscal_year(orders, current_fy)
    
    # Define your courses
    courses = ["Living Latin", "Elementa", "Modern Greek for Classicists"]
    
    for course in courses:
        st.write("---")
        st.subheader(f"📚 {course}")
        
        course_data = analyze_course_orders(fy_orders, course)
        
        if course_data:
            # Course summary metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📦 Total Orders", f"{course_data['total_orders']:,}")
            with col2:
                st.metric("💰 Total Revenue", f"${course_data['total_revenue']:,.2f}")
            with col3:
                st.metric("🆕 New Sales", f"${course_data['new_revenue']:,.2f}")
            with col4:
                st.metric("🔄 Recurring", f"${course_data['recurring_revenue']:,.2f}")
            
            # Individual Orders Breakdown
            st.write("**👤 Individual Orders**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Individual", f"{course_data['individual_orders']:,}")
            with col2:
                st.metric("Monthly", f"{course_data['individual_monthly']:,}")
            with col3:
                st.metric("Annual", f"{course_data['individual_annual']:,}")
            
            # Individual revenue breakdown
            individual_new_revenue = 0
            individual_recurring_revenue = 0
            
            for order in fy_orders:
                if order.get('status') != 'completed':
                    continue
                for item in order.get('line_items', []):
                    if isinstance(item, dict) and 'name' in item:
                        item_name = item['name']
                        if (course.lower() in item_name.lower() and 
                            'individual' in item_name.lower()):
                            item_revenue = float(item.get('total', 0))
                            if order.get('created_via') == 'subscription':
                                individual_recurring_revenue += item_revenue
                            else:
                                individual_new_revenue += item_revenue
            
            st.write(f"*Individual Revenue: ${individual_new_revenue:,.2f} Initial / ${individual_recurring_revenue:,.2f} Recurring*")
            
            # Group Orders Breakdown
            st.write("**👥 Group Orders**")
            st.metric("Total Group", f"{course_data['group_orders']:,}")
            
            # Group orders by seat count
            if course_data['group_by_seats']:
                col1, col2 = st.columns([1, 2])
                with col1:
                    for seats, orders_list in sorted(course_data['group_by_seats'].items()):
                        st.write(f"{seats} seats - {len(orders_list)}")
                
                with col2:
                    # Group revenue breakdown
                    group_new_revenue = 0
                    group_recurring_revenue = 0
                    
                    for order in fy_orders:
                        if order.get('status') != 'completed':
                            continue
                        for item in order.get('line_items', []):
                            if isinstance(item, dict) and 'name' in item:
                                item_name = item['name']
                                if (course.lower() in item_name.lower() and 
                                    ('group' in item_name.lower() or 'seats' in item_name.lower())):
                                    item_revenue = float(item.get('total', 0))
                                    if order.get('created_via') == 'subscription':
                                        group_recurring_revenue += item_revenue
                                    else:
                                        group_new_revenue += item_revenue
                    
                    st.write(f"*Group Revenue: ${group_new_revenue:,.2f} Initial / ${group_recurring_revenue:,.2f} Recurring*")
            
            # Course total revenue breakdown
            st.write(f"**💰 Total Revenue: ${course_data['new_revenue']:,.2f} Initial / ${course_data['recurring_revenue']:,.2f} Recurring**")
            
        else:
            st.write(f"No orders found for {course} in this fiscal year.")
    
    # Two columns layout for recent orders and status breakdown
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Recent orders
        st.subheader("📋 Recent Orders")
        recent_orders = sorted(orders, key=lambda x: x['date_created'], reverse=True)[:10]
        
        if recent_orders:
            recent_data = []
            for order in recent_orders:
                recent_data.append({
                    'Order #': order['id'],
                    'Customer': f"{order['billing']['first_name']} {order['billing']['last_name']}",
                    'Date': order['date_created'][:10],
                    'Total': f"${order['total']}",
                    'Status': order['status']
                })
            
            df_recent = pd.DataFrame(recent_data)
            st.dataframe(df_recent, use_container_width=True)
        else:
            st.write("No recent orders found.")
    
    with col2:
        # Order status breakdown
        st.subheader("📊 Order Status")
        if stats['status_breakdown']:
            status_data = pd.DataFrame([
                {'Status': status, 'Count': count}
                for status, count in stats['status_breakdown'].items()
            ])
            
            fig = px.pie(status_data, values='Count', names='Status', 
                        title="Order Status Distribution")
            st.plotly_chart(fig, use_container_width=True)

def show_monthly_sales(orders):
    """Monthly sales view showing total revenue by product and month."""
    st.subheader("Total Revenue by Product and Month")
    
    # Filter for all completed orders (not just new sales)
    all_orders = [order for order in orders if order.get('status') == 'completed']
    if not all_orders:
        st.write("No sales found.")
        return
    
    # Gather all unique product names and months
    product_names = set()
    months = set()
    product_course_map = {}
    courses = ["Living Latin", "Elementa", "Modern Greek for Classicists"]
    
    # Exclude demo/beta/test products and specific unwanted products
    exclude_keywords = [
        "demo product", "ll test", "this is a course title",
        "elementa digital student textbook - 1 - 10 seats",
        "elementa digital student textbook - 100 seats",
        "elementa digital student textbook - 25 seats",
        "elementa digital student textbook - 50 seats",
        "elementa digital student textbook - individual",
        "elementa digital student textbook - individual - annual",
        "elementa presentations - 100 seats",
        "elementa presentations - individual",
        "aequora",
        "aequora - 1 - 10 seats",
        "aequora - 25 seats",
        "living latin (beta) - 2 seats",
        "living latin (beta) - 6 seats",
        "living latin - individual chinese version",
        "living latin - individual",
        "living latin in rome - 1 - 10 seats",
        "living latin in rome - 100 seats",
        "living latin in rome - 25 seats",
        "living latin in rome - 50 seats",
        "elementa - 1 - 10 seats",
        "elementa - 100 seats",
        "demo product 2 - 1 - 10 seats",
        "ll test - 1 - 10 seats",
        "this is a course title - 1 - 10 seats",
        "this is a course title - 25 seats"
    ]
    exclude_keywords = [
        ' '.join(e.lower().split()) for e in exclude_keywords
    ]
    
    # Build a mapping of product name to course
    for order in all_orders:
        date_str = order.get('date_created')
        if 'T' in date_str:
            order_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
        else:
            order_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        month_key = order_date.strftime("%Y-%m")
        months.add(month_key)
        for item in order.get('line_items', []):
            if isinstance(item, dict) and 'name' in item:
                name = item['name'].strip()
                # Exclude demo/beta/test products
                if ' '.join(name.lower().split()) in exclude_keywords:
                    continue
                product_names.add(name)
                for course in courses:
                    if course.lower() in name.lower():
                        product_course_map[name] = course
                        break
                else:
                    product_course_map[name] = "Other"
    
    # Deduplicate product names (case/whitespace insensitive)
    normalized_names = {}
    for name in product_names:
        norm = ' '.join(name.lower().split())
        if norm not in normalized_names:
            normalized_names[norm] = name
    product_names = list(normalized_names.values())
    
    # Sort months and product names (grouped by course)
    months = sorted(months)
    product_names = sorted(product_names, key=lambda n: (courses.index(product_course_map.get(n, "Other")) if product_course_map.get(n, "Other") in courses else 99, n))
    
    # Build the pivot table: rows=product names, columns=months, values=revenue
    data = {"Product": product_names}
    for month in months:
        data[month] = [0 for _ in product_names]
    
    # Fill the table
    product_month_revenue = {(name, month): 0 for name in product_names for month in months}
    for order in all_orders:
        date_str = order.get('date_created')
        if 'T' in date_str:
            order_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
        else:
            order_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        month_key = order_date.strftime("%Y-%m")
        for item in order.get('line_items', []):
            if isinstance(item, dict) and 'name' in item:
                name = item['name'].strip()
                if ' '.join(name.lower().split()) in exclude_keywords:
                    continue
                norm = ' '.join(name.lower().split())
                if norm in normalized_names:
                    name = normalized_names[norm]
                revenue = float(item.get('total', 0))
                if (name, month_key) in product_month_revenue:
                    product_month_revenue[(name, month_key)] += revenue
    
    # Fill data for DataFrame
    for i, name in enumerate(product_names):
        for month in months:
            data[month][i] = product_month_revenue[(name, month)]
    
    # Remove the Course column from the DataFrame
    df_pivot = pd.DataFrame(data)
    
    # Add a Total row at the bottom
    total_row = {"Product": "Total"}
    for month in months:
        total_row[month] = df_pivot[month].sum()
    # Append the total row
    df_pivot_with_total = pd.concat([df_pivot, pd.DataFrame([total_row])], ignore_index=True)
    
    # Only show the table with the total row
    st.dataframe(
        df_pivot_with_total,
        use_container_width=True,
        column_order=["Product"] + months,
        hide_index=True,
        column_config={"Product": {"frozen": True}}
    )
    st.caption("Rows: Product names. Columns: Months. Values: Revenue for all completed orders. Demo/beta/test products excluded. Total row at bottom.")

    # Add a second table for new order counts
    st.subheader("📊 Monthly New Order Counts")
    
    # Build the order count table: rows=product names, columns=months, values=order count
    count_data = {"Product": product_names}
    for month in months:
        count_data[month] = [0 for _ in product_names]
    
    # Fill the order count table (only new orders, not recurring)
    product_month_count = {(name, month): 0 for name in product_names for month in months}
    for order in all_orders:
        # Only count new orders (not recurring/subscription orders)
        if order.get('created_via') == 'subscription':
            continue
            
        date_str = order.get('date_created')
        if 'T' in date_str:
            order_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
        else:
            order_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        month_key = order_date.strftime("%Y-%m")
        
        for item in order.get('line_items', []):
            if isinstance(item, dict) and 'name' in item:
                name = item['name'].strip()
                if ' '.join(name.lower().split()) in exclude_keywords:
                    continue
                norm = ' '.join(name.lower().split())
                if norm in normalized_names:
                    name = normalized_names[norm]
                if (name, month_key) in product_month_count:
                    product_month_count[(name, month_key)] += 1
    
    # Fill count data for DataFrame
    for i, name in enumerate(product_names):
        for month in months:
            count_data[month][i] = product_month_count[(name, month)]
    
    # Create DataFrame for order counts
    df_count = pd.DataFrame(count_data)
    
    # Add a Total row at the bottom for counts
    count_total_row = {"Product": "Total"}
    for month in months:
        count_total_row[month] = df_count[month].sum()
    # Append the total row
    df_count_with_total = pd.concat([df_count, pd.DataFrame([count_total_row])], ignore_index=True)
    
    # Show the order count table
    st.dataframe(
        df_count_with_total,
        use_container_width=True,
        column_order=["Product"] + months,
        hide_index=True,
        column_config={"Product": {"frozen": True}}
    )
    st.caption("Rows: Product names. Columns: Months. Values: Count of new orders (excluding recurring/subscription orders). Demo/beta/test products excluded. Total row at bottom.")

def show_refresh_page():
    """Refresh data page"""
    st.subheader("🔄 Refresh Data")
    
    st.write("""
    This page allows you to fetch the latest orders from your WooCommerce store.
    
    **What happens when you refresh:**
    - Fetches all orders from WooCommerce API
    - Updates the local Woo.json file
    - Clears the cache to show fresh data
    - Shows progress during the fetch
    
    **Note:** The refresh process respects API rate limits and may take a few seconds.
    """)
    
    if st.button("🔄 Start Data Refresh", type="primary"):
        with st.spinner("Fetching latest orders..."):
            success, message = fetch_orders_from_api()
            if success:
                st.success(message)
                st.cache_data.clear()  # Clear cache to reload data
                st.rerun()  # Refresh the page to show new data
            else:
                st.error(message)

def show_users(orders):
    """Users view showing longest subscriptions and lifetime value"""
    st.subheader("👥 Users Analysis")
    
    # Filter for completed orders
    completed_orders = [o for o in orders if o.get('status') == 'completed']
    if not completed_orders:
        st.write("No completed orders found.")
        return
    
    # Define the same product exclusions as monthly tables
    exclude_keywords = [
        "demo product", "ll test", "this is a course title",
        "elementa digital student textbook - 1 - 10 seats",
        "elementa digital student textbook - 100 seats",
        "elementa digital student textbook - 25 seats",
        "elementa digital student textbook - 50 seats",
        "elementa digital student textbook - individual",
        "elementa digital student textbook - individual - annual",
        "elementa presentations - 100 seats",
        "elementa presentations - individual",
        "aequora",
        "aequora - 1 - 10 seats",
        "aequora - 25 seats",
        "living latin (beta) - 2 seats",
        "living latin (beta) - 6 seats",
        "living latin - individual chinese version",
        "living latin - individual",
        "living latin in rome - 1 - 10 seats",
        "living latin in rome - 100 seats",
        "living latin in rome - 25 seats",
        "living latin in rome - 50 seats",
        "elementa - 1 - 10 seats",
        "elementa - 100 seats",
        "demo product 2 - 1 - 10 seats",
        "ll test - 1 - 10 seats",
        "this is a course title - 1 - 10 seats",
        "this is a course title - 25 seats"
    ]
    exclude_keywords = [' '.join(e.lower().split()) for e in exclude_keywords]
    
    # Analyze users
    user_data = {}
    
    for order in completed_orders:
        customer_id = order.get('customer_id')
        if not customer_id:
            continue
            
        # Check if order contains any of our included products
        has_included_product = False
        for item in order.get('line_items', []):
            if isinstance(item, dict) and 'name' in item:
                name = item['name'].strip()
                if ' '.join(name.lower().split()) not in exclude_keywords:
                    has_included_product = True
                    break
        
        if not has_included_product:
            continue
            
        # Initialize user data if not exists
        if customer_id not in user_data:
            user_data[customer_id] = {
                'name': f"{order.get('billing', {}).get('first_name', '')} {order.get('billing', {}).get('last_name', '')}".strip(),
                'email': order.get('billing', {}).get('email', ''),
                'first_order_date': order.get('date_created'),
                'last_order_date': order.get('date_created'),
                'total_revenue': 0,
                'order_count': 0,
                'subscription_orders': 0,
                'new_orders': 0,
                'products_purchased': set()
            }
        
        # Update user data
        user = user_data[customer_id]
        user['total_revenue'] += float(order.get('total', 0))
        user['order_count'] += 1
        
        # Track subscription vs new orders
        if order.get('created_via') == 'subscription':
            user['subscription_orders'] += 1
        else:
            user['new_orders'] += 1
        
        # Update dates
        order_date = order.get('date_created')
        if order_date < user['first_order_date']:
            user['first_order_date'] = order_date
        if order_date > user['last_order_date']:
            user['last_order_date'] = order_date
        
        # Track products
        for item in order.get('line_items', []):
            if isinstance(item, dict) and 'name' in item:
                name = item['name'].strip()
                if ' '.join(name.lower().split()) not in exclude_keywords:
                    user['products_purchased'].add(name)
    
    if not user_data:
        st.write("No users found with included products.")
        return
    
    # Calculate subscription duration and convert sets to lists
    for user_id, user in user_data.items():
        # Calculate subscription duration in months
        try:
            if 'T' in user['first_order_date']:
                first_date = datetime.strptime(user['first_order_date'], "%Y-%m-%dT%H:%M:%S")
                last_date = datetime.strptime(user['last_order_date'], "%Y-%m-%dT%H:%M:%S")
            else:
                first_date = datetime.strptime(user['first_order_date'], "%Y-%m-%d %H:%M:%S")
                last_date = datetime.strptime(user['last_order_date'], "%Y-%m-%d %H:%M:%S")
            
            months_diff = (last_date.year - first_date.year) * 12 + (last_date.month - first_date.month)
            user['subscription_months'] = max(0, months_diff)
        except:
            user['subscription_months'] = 0
        
        # Convert set to list for display
        user['products_purchased'] = list(user['products_purchased'])
    
    # Calculate average lifetime value
    total_revenue = sum(user['total_revenue'] for user in user_data.values())
    total_users = len(user_data)
    avg_lifetime_value = total_revenue / total_users if total_users > 0 else 0
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("👥 Total Users", f"{total_users:,}")
    with col2:
        st.metric("💰 Total Revenue", f"${total_revenue:,.2f}")
    with col3:
        st.metric("📊 Avg Lifetime Value", f"${avg_lifetime_value:,.2f}")
    with col4:
        st.metric("🔄 Avg Orders/User", f"{sum(user['order_count'] for user in user_data.values()) / total_users:.1f}")
    
    # Users with longest subscriptions
    st.subheader("🏆 Users with Longest Subscriptions")
    
    # Sort by subscription months (descending)
    sorted_users = sorted(user_data.items(), key=lambda x: x[1]['subscription_months'], reverse=True)
    
    # Create DataFrame for longest subscriptions
    longest_sub_data = []
    for user_id, user in sorted_users[:20]:  # Top 20
        longest_sub_data.append({
            'Customer': user['name'] or f"User {user_id}",
            'Email': user['email'],
            'Months': user['subscription_months'],
            'Total Revenue': f"${user['total_revenue']:,.2f}",
            'Orders': user['order_count'],
            'Subscription Orders': user['subscription_orders'],
            'New Orders': user['new_orders'],
            'Products': ', '.join(user['products_purchased']) if user['products_purchased'] else 'None'
        })
    
    if longest_sub_data:
        df_longest = pd.DataFrame(longest_sub_data)
        st.dataframe(df_longest, use_container_width=False, width=1200)
    else:
        st.write("No users with subscription data found.")
    
    # Highest lifetime value users
    st.subheader("💰 Users with Highest Lifetime Value")
    
    # Sort by total revenue (descending)
    sorted_by_value = sorted(user_data.items(), key=lambda x: x[1]['total_revenue'], reverse=True)
    
    # Create DataFrame for highest value users
    highest_value_data = []
    for user_id, user in sorted_by_value[:20]:  # Top 20
        highest_value_data.append({
            'Customer': user['name'] or f"User {user_id}",
            'Email': user['email'],
            'Lifetime Value': f"${user['total_revenue']:,.2f}",
            'Months': user['subscription_months'],
            'Orders': user['order_count'],
            'Subscription Orders': user['subscription_orders'],
            'New Orders': user['new_orders'],
            'Products': ', '.join(user['products_purchased']) if user['products_purchased'] else 'None'
        })
    
    if highest_value_data:
        df_value = pd.DataFrame(highest_value_data)
        st.dataframe(df_value, use_container_width=False, width=1200)
    else:
        st.write("No users with revenue data found.")

# Call main function at the end after all functions are defined
main() 