
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import asyncio
from contextlib import contextmanager

# Try to import mysql.connector, fallback if not available
try:
    import mysql.connector
    from mysql.connector import pooling, Error as MySQLError
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    # Create mock classes for testing
    class MockConnection:
        def cursor(self, dictionary=False):
            return MockCursor()
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass
    
    class MockCursor:
        def execute(self, query, params=None): pass
        def fetchone(self): return None
        def fetchall(self): return []
        def close(self): pass
    
    class mysql:
        connector = type('connector', (), {
            'connect': lambda **kwargs: MockConnection(),
            'Error': Exception
        })()
    
    class pooling:
        class MySQLConnectionPool:
            def __init__(self, **kwargs):
                pass
            def get_connection(self):
                return MockConnection()
    
    MySQLError = Exception

# Import new configuration and logging
try:
    from config import config
    from logger_config import get_logger
    logger = get_logger("database")
except ImportError:
    # Fallback for backward compatibility
    class config:
        MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
        MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
        MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
        MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'bot_database')
        MYSQL_PORT = int(os.environ.get('MYSQL_PORT', '3306'))
        DB_POOL_SIZE = 10
        DB_POOL_RESET_SESSION = True
    
    class logger:
        @staticmethod
        def info(msg): print(f"INFO: {msg}")
        @staticmethod
        def error(msg, exc_info=False): print(f"ERROR: {msg}")
        @staticmethod
        def warning(msg): print(f"WARNING: {msg}")
        @staticmethod
        def debug(msg): print(f"DEBUG: {msg}")

# Global connection pool
connection_pool = None

# Add regex for ingame ID validation
import re

INGAME_ID_PATTERN = re.compile(r'^[A-Z]{2}\d{6}$')  # For validation (full string match)
INGAME_ID_EXTRACT_PATTERN = re.compile(r'[A-Z]{2}\d{6}')  # For extraction (anywhere in text)

def validate_ingame_id_format(ingame_id: str) -> bool:
    """Validate ingame ID format (2 letters + 6 numbers)"""
    if not ingame_id:
        return False
    return bool(INGAME_ID_PATTERN.match(ingame_id.upper()))

def init_connection_pool():
    """Initialize the MySQL connection pool"""
    global connection_pool

    if not config.MYSQL_PASSWORD:
        raise ValueError("MYSQL_PASSWORD environment variable not set")

    try:
        # Create connection pool configuration
        pool_config = {
            'user': config.MYSQL_USER,
            'password': config.MYSQL_PASSWORD,
            'host': config.MYSQL_HOST,
            'port': config.MYSQL_PORT,
            'database': config.MYSQL_DATABASE,
            'pool_name': 'bot_pool',
            'pool_size': config.DB_POOL_SIZE,
            'pool_reset_session': config.DB_POOL_RESET_SESSION,
            'autocommit': False,
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci'
        }

        connection_pool = pooling.MySQLConnectionPool(**pool_config)
        logger.info("MySQL connection pool initialized successfully")
    except MySQLError as e:
        logger.error(f"MySQL error initializing connection pool: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error initializing MySQL connection pool: {e}", exc_info=True)
        raise

def get_db_connection():
    """Get a MySQL database connection from the pool"""
    global connection_pool
    if connection_pool is None:
        init_connection_pool()

    try:
        conn = connection_pool.get_connection()
        if conn:
            return conn
        else:
            raise Exception("Unable to get connection from pool")
    except MySQLError as e:
        logger.error(f"MySQL error getting connection from pool: {e}")
        # Fallback to direct connection
        try:
            conn = mysql.connector.connect(
                host=config.MYSQL_HOST,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DATABASE,
                port=config.MYSQL_PORT,
                autocommit=False,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci'
            )
            logger.warning("Using direct connection as fallback")
            return conn
        except MySQLError as fallback_error:
            logger.error(f"Fallback connection also failed: {fallback_error}", exc_info=True)
            raise
    except Exception as e:
        logger.error(f"Unexpected error getting connection from pool: {e}", exc_info=True)
        raise

def release_db_connection(conn):
    """Release the database connection back to the pool"""
    if conn:
        try:
            conn.close()
        except Exception as e:
            logger.error(f"Error releasing connection: {e}")

@contextmanager
def get_db_cursor():
    """Context manager for database operations"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        yield cursor, conn
        conn.commit()
    except MySQLError as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error in operation: {e}", exc_info=True)
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Unexpected error in database operation: {e}", exc_info=True)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_db_connection(conn)

def execute_query(query, params=None, fetch=None):
    """Execute a query with proper connection management"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute(query, params)

            if fetch == 'one':
                result = cursor.fetchone()
            elif fetch == 'all':
                result = cursor.fetchall()
            else:
                result = None

            return result
    except Exception as e:
        logger.error(f"Error executing query: {query[:100]}... - {e}", exc_info=True)
        raise

def init_database():
    """Initialize the MySQL database with all required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # User listings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_listings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                car_name TEXT NOT NULL,
                listing_type VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Sales data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales_data (
                user_id BIGINT PRIMARY KEY,
                sales INT DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        ''')

        # Active deals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_deals (
                channel_id BIGINT PRIMARY KEY,
                seller_id BIGINT NOT NULL,
                buyer_id BIGINT NOT NULL,
                car_name TEXT NOT NULL,
                listing_message_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Deal confirmations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deal_confirmations (
                channel_id BIGINT PRIMARY KEY,
                buyer_confirmed BOOLEAN DEFAULT FALSE,
                seller_confirmed BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        ''')

        # Active auctions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_auctions (
                auction_id VARCHAR(255) PRIMARY KEY,
                thread_id BIGINT NOT NULL,
                car_name TEXT NOT NULL,
                starting_bid INT NOT NULL,
                highest_bid INT NOT NULL,
                highest_bidder BIGINT,
                seller_id BIGINT NOT NULL,
                end_time TEXT NOT NULL,
                status VARCHAR(50) DEFAULT 'active',
                duration_hours INT,
                duration_minutes INT,
                is_test BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Ended auctions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ended_auctions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                auction_id VARCHAR(255) NOT NULL,
                car_name TEXT NOT NULL,
                seller_id BIGINT NOT NULL,
                seller_username TEXT,
                final_bid INT NOT NULL,
                winner_id BIGINT NOT NULL,
                winner_username TEXT,
                result TEXT NOT NULL,
                timestamp TEXT,
                is_test BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Active giveaways table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_giveaways (
                giveaway_id VARCHAR(255) PRIMARY KEY,
                message_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                car_name TEXT NOT NULL,
                host_id BIGINT NOT NULL,
                end_time TEXT NOT NULL,
                duration_hours INT NOT NULL,
                participants JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Pending listings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_listings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                listing_type VARCHAR(50) NOT NULL,
                listing_data JSON NOT NULL,
                channel_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Support tickets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                help_needed TEXT NOT NULL,
                status VARCHAR(50) DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Report tickets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS report_tickets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                reporter_id BIGINT NOT NULL,
                reported_username TEXT NOT NULL,
                reason TEXT NOT NULL,
                channel_id BIGINT NOT NULL,
                status VARCHAR(50) DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Car models table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS car_models (
                id INT AUTO_INCREMENT PRIMARY KEY,
                model_name VARCHAR(255) NOT NULL UNIQUE,
                aliases JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Car listing statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS car_listing_stats (
                id INT AUTO_INCREMENT PRIMARY KEY,
                car_model_id INT NOT NULL,
                listing_type VARCHAR(50) NOT NULL,
                user_id BIGINT NOT NULL,
                message_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (car_model_id) REFERENCES car_models (id)
            )
        ''')

        # Car listings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS car_listings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                car_name VARCHAR(255) NOT NULL,
                short_codes TEXT,
                list_count INT DEFAULT 0,
                UNIQUE KEY unique_car_name (car_name)
            )
        ''')

        # Car price logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS car_price_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                car_name VARCHAR(255) NOT NULL,
                price_text TEXT NOT NULL,
                price_numeric INT,
                user_id BIGINT NOT NULL,
                username VARCHAR(255) NOT NULL,
                message_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # User ingame IDs table - SECURITY SYSTEM
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_ingame_ids (
                discord_id BIGINT PRIMARY KEY,
                ingame_id VARCHAR(10) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        print("MySQL database initialized successfully")

    except Exception as e:
        conn.rollback()
        print(f"Error initializing database: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

# User Listings Functions
def add_user_listing(user_id: int, message_id: int, car_name: str, listing_type: str = 'sell'):
    """Add a user listing to the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO user_listings (user_id, message_id, car_name, listing_type)
            VALUES (%s, %s, %s, %s)
        ''', (user_id, message_id, car_name, listing_type))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def get_user_listings(user_id: int) -> List[Dict]:
    """Get all listings for a user"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''
            SELECT * FROM user_listings WHERE user_id = %s
        ''', (user_id,))
        listings = cursor.fetchall()
        return listings
    finally:
        cursor.close()
        conn.close()

def get_all_user_listings() -> Dict[int, List[Dict]]:
    """Get all user listings in the format expected by the old system"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM user_listings')
        all_listings = cursor.fetchall()

        user_listings = {}
        for listing in all_listings:
            user_id = listing['user_id']
            if user_id not in user_listings:
                user_listings[user_id] = []
            user_listings[user_id].append({
                'message_id': listing['message_id'],
                'car_name': listing['car_name']
            })

        return user_listings
    finally:
        cursor.close()
        conn.close()

def remove_user_listing(user_id: int, message_id: int):
    """Remove a specific listing"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            DELETE FROM user_listings WHERE user_id = %s AND message_id = %s
        ''', (user_id, message_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def clear_all_user_listings():
    """Clear all user listings"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM user_listings')
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

# Sales Data Functions
def record_sale(seller_id: int) -> int:
    """Record a successful sale for a seller and return new count"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if user exists
        cursor.execute('SELECT sales FROM sales_data WHERE user_id = %s', (seller_id,))
        result = cursor.fetchone()

        if result:
            new_count = result['sales'] + 1
            cursor.execute('''
                UPDATE sales_data SET sales = %s, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            ''', (new_count, seller_id))
        else:
            new_count = 1
            cursor.execute('''
                INSERT INTO sales_data (user_id, sales)
                VALUES (%s, %s)
            ''', (seller_id, new_count))

        conn.commit()
        return new_count
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        release_db_connection(conn)

def get_sales_data() -> Dict[str, Dict]:
    """Get all sales data in the format expected by the old system"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM sales_data')
        sales = cursor.fetchall()

        sales_data = {}
        for sale in sales:
            sales_data[str(sale['user_id'])] = {
                'sales': sale['sales']
            }

        return sales_data
    finally:
        cursor.close()
        conn.close()

def get_user_sales(user_id: int) -> int:
    """Get sales count for a specific user"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT sales FROM sales_data WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        return result['sales'] if result else 0
    finally:
        cursor.close()
        release_db_connection(conn)

# Active Deals Functions
def add_active_deal(channel_id: int, seller_id: int, buyer_id: int, car_name: str, listing_message_id: int = None):
    """Add an active deal"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO active_deals 
            (channel_id, seller_id, buyer_id, car_name, listing_message_id)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                seller_id = VALUES(seller_id),
                buyer_id = VALUES(buyer_id),
                car_name = VALUES(car_name),
                listing_message_id = VALUES(listing_message_id)
        ''', (channel_id, seller_id, buyer_id, car_name, listing_message_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def get_active_deal(channel_id: int) -> Optional[Dict]:
    """Get active deal information"""
    try:
        result = execute_query(
            'SELECT * FROM active_deals WHERE channel_id = %s', 
            (channel_id,), 
            fetch='one'
        )
        return result if result else None
    except Exception as e:
        print(f"Error getting active deal: {e}")
        return None

def get_all_active_deals() -> Dict[int, Dict]:
    """Get all active deals in the format expected by the old system"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM active_deals')
        deals = cursor.fetchall()

        active_deals = {}
        for deal in deals:
            active_deals[deal['channel_id']] = {
                'seller_id': deal['seller_id'],
                'buyer_id': deal['buyer_id'],
                'car_name': deal['car_name'],
                'listing_message_id': deal['listing_message_id']
            }

        return active_deals
    finally:
        cursor.close()
        conn.close()

def remove_active_deal(channel_id: int):
    """Remove an active deal"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM active_deals WHERE channel_id = %s', (channel_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

# Deal Confirmations Functions
def get_deal_confirmation(channel_id: int) -> Optional[Dict]:
    """Get deal confirmation status"""
    try:
        result = execute_query(
            'SELECT * FROM deal_confirmations WHERE channel_id = %s', 
            (channel_id,), 
            fetch='one'
        )
        return result if result else None
    except Exception as e:
        print(f"Error getting deal confirmation: {e}")
        return None

def add_deal_confirmation(channel_id: int):
    """Add new deal confirmation entry only if it doesn't exist"""
    try:
        existing = get_deal_confirmation(channel_id)
        if existing:
            print(f"Deal confirmation already exists for channel {channel_id}")
            return existing

        execute_query('''
            INSERT INTO deal_confirmations (channel_id, buyer_confirmed, seller_confirmed)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            buyer_confirmed = VALUES(buyer_confirmed),
            seller_confirmed = VALUES(seller_confirmed)
        ''', (channel_id, False, False))
        
        return {"buyer_confirmed": False, "seller_confirmed": False}
    except Exception as e:
        print(f"Error adding deal confirmation: {e}")
        return None

def update_deal_confirmation(channel_id: int, buyer_confirmed: bool = None, seller_confirmed: bool = None):
    """Update deal confirmation status"""
    try:
        if buyer_confirmed is not None:
            execute_query('''
                UPDATE deal_confirmations 
                SET buyer_confirmed = %s, updated_at = CURRENT_TIMESTAMP
                WHERE channel_id = %s
            ''', (buyer_confirmed, channel_id))

        if seller_confirmed is not None:
            execute_query('''
                UPDATE deal_confirmations 
                SET seller_confirmed = %s, updated_at = CURRENT_TIMESTAMP
                WHERE channel_id = %s
            ''', (seller_confirmed, channel_id))
    except Exception as e:
        print(f"Error updating deal confirmation: {e}")

def get_all_deal_confirmations() -> Dict[int, Dict]:
    """Get all deal confirmations in the format expected by the old system"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM deal_confirmations')
        confirmations = cursor.fetchall()

        deal_confirmations = {}
        for confirmation in confirmations:
            deal_confirmations[confirmation['channel_id']] = {
                'buyer_confirmed': confirmation['buyer_confirmed'],
                'seller_confirmed': confirmation['seller_confirmed']
            }

        return deal_confirmations
    finally:
        cursor.close()
        conn.close()

def remove_deal_confirmation(channel_id: int):
    """Remove deal confirmation entry"""
    try:
        execute_query('DELETE FROM deal_confirmations WHERE channel_id = %s', (channel_id,))
    except Exception as e:
        print(f"Error removing deal confirmation: {e}")

def is_deal_confirmation_complete(channel_id: int) -> bool:
    """Check if both parties have confirmed the deal"""
    try:
        confirmations = get_deal_confirmation(channel_id)
        if confirmations:
            return confirmations["buyer_confirmed"] and confirmations["seller_confirmed"]
        return False
    except Exception as e:
        print(f"Error checking deal confirmation completion: {e}")
        return False

def add_deal_confirmation(channel_id: int, buyer_confirmed: bool = False, seller_confirmed: bool = False):
    """Add a new deal confirmation entry"""
    try:
        execute_query(
            'INSERT INTO deal_confirmations (channel_id, buyer_confirmed, seller_confirmed) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE buyer_confirmed = VALUES(buyer_confirmed), seller_confirmed = VALUES(seller_confirmed)',
            (channel_id, buyer_confirmed, seller_confirmed)
        )
    except Exception as e:
        print(f"Error adding deal confirmation: {e}")
        raise e

def get_all_deal_confirmations():
    """Get all deal confirmations"""
    try:
        results = execute_query('SELECT channel_id, buyer_confirmed, seller_confirmed FROM deal_confirmations')
        confirmations = {}
        for row in results:
            confirmations[row[0]] = {
                "buyer_confirmed": row[1],
                "seller_confirmed": row[2]
            }
        return confirmations
    except Exception as e:
        print(f"Error getting all deal confirmations: {e}")
        return {}

# Auction Functions
def add_active_auction(auction_data: Dict):
    """Add an active auction"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO active_auctions 
            (auction_id, thread_id, car_name, starting_bid, highest_bid, highest_bidder,
             seller_id, end_time, status, duration_hours, duration_minutes, is_test)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                thread_id = VALUES(thread_id),
                car_name = VALUES(car_name),
                starting_bid = VALUES(starting_bid),
                highest_bid = VALUES(highest_bid),
                highest_bidder = VALUES(highest_bidder),
                seller_id = VALUES(seller_id),
                end_time = VALUES(end_time),
                status = VALUES(status),
                duration_hours = VALUES(duration_hours),
                duration_minutes = VALUES(duration_minutes),
                is_test = VALUES(is_test)
        ''', (
            auction_data['auction_id'],
            auction_data['thread_id'],
            auction_data['car_name'],
            auction_data['starting_bid'],
            auction_data['highest_bid'],
            auction_data.get('highest_bidder'),
            auction_data['seller_id'],
            auction_data['end_time'],
            auction_data.get('status', 'active'),
            auction_data.get('duration_hours'),
            auction_data.get('duration_minutes'),
            auction_data.get('is_test', False)
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def get_active_auction(auction_id: str) -> Optional[Dict]:
    """Get an active auction by ID"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM active_auctions WHERE auction_id = %s', (auction_id,))
        result = cursor.fetchone()
        return result if result else None
    finally:
        cursor.close()
        conn.close()

def get_all_active_auctions() -> Dict[str, Dict]:
    """Get all active auctions in the format expected by the old system"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM active_auctions')
        auctions = cursor.fetchall()

        active_auctions = {}
        for auction in auctions:
            active_auctions[auction['auction_id']] = auction

        return active_auctions
    finally:
        cursor.close()
        conn.close()

def update_auction_bid(auction_id: str, highest_bid: int, highest_bidder: int):
    """Update auction bid information"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE active_auctions 
            SET highest_bid = %s, highest_bidder = %s
            WHERE auction_id = %s
        ''', (highest_bid, highest_bidder, auction_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def update_auction_status(auction_id: str, status: str):
    """Update auction status"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE active_auctions 
            SET status = %s
            WHERE auction_id = %s
        ''', (status, auction_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def remove_active_auction(auction_id: str):
    """Remove an active auction"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM active_auctions WHERE auction_id = %s', (auction_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def add_ended_auction(auction_data: Dict):
    """Add an ended auction to the log"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        winner_id = auction_data['winner']['user_id']
        if winner_id is None:
            winner_id = 0

        cursor.execute('''
            INSERT INTO ended_auctions 
            (auction_id, car_name, seller_id, seller_username, final_bid, winner_id, 
             winner_username, result, timestamp, is_test)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            auction_data['auction_id'],
            auction_data['car_name'],
            auction_data['auction_creator']['user_id'],
            auction_data['auction_creator']['username'],
            auction_data['final_bid'],
            winner_id,
            auction_data['winner']['username'],
            auction_data['result'],
            auction_data.get('timestamp'),
            auction_data.get('is_test', False)
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def get_all_ended_auctions() -> List[Dict]:
    """Get all ended auctions"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM ended_auctions ORDER BY created_at DESC')
        auctions = cursor.fetchall()

        ended_auctions = []
        for auction in auctions:
            auction_data = {
                'auction_id': auction['auction_id'],
                'car_name': auction['car_name'],
                'auction_creator': {
                    'user_id': auction['seller_id'],
                    'username': auction['seller_username']
                },
                'final_bid': auction['final_bid'],
                'winner': {
                    'user_id': auction['winner_id'],
                    'username': auction['winner_username']
                },
                'result': auction['result'],
                'timestamp': auction['timestamp'],
                'is_test': auction['is_test']
            }
            ended_auctions.append(auction_data)

        return ended_auctions
    finally:
        cursor.close()
        conn.close()

# Giveaway Functions
def add_active_giveaway(giveaway_data: Dict):
    """Add an active giveaway"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO active_giveaways 
            (giveaway_id, message_id, channel_id, car_name, host_id, end_time, duration_hours, participants)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                message_id = VALUES(message_id),
                channel_id = VALUES(channel_id),
                car_name = VALUES(car_name),
                host_id = VALUES(host_id),
                end_time = VALUES(end_time),
                duration_hours = VALUES(duration_hours),
                participants = VALUES(participants)
        ''', (
            giveaway_data['giveaway_id'],
            giveaway_data['message_id'],
            giveaway_data['channel_id'],
            giveaway_data['car_name'],
            giveaway_data['host_id'],
            giveaway_data['end_time'],
            giveaway_data['duration_hours'],
            json.dumps(giveaway_data.get('participants', []))
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def get_active_giveaway(giveaway_id: str) -> Optional[Dict]:
    """Get an active giveaway by ID"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM active_giveaways WHERE giveaway_id = %s', (giveaway_id,))
        result = cursor.fetchone()

        if result:
            participants = result['participants']
            if isinstance(participants, str):
                result['participants'] = json.loads(participants)
            elif isinstance(participants, list):
                result['participants'] = participants
            else:
                result['participants'] = []
            return result
        return None
    finally:
        cursor.close()
        conn.close()

def get_all_active_giveaways() -> Dict[str, Dict]:
    """Get all active giveaways in the format expected by the old system"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM active_giveaways')
        giveaways = cursor.fetchall()

        active_giveaways = {}
        for giveaway in giveaways:
            participants = giveaway['participants']
            if isinstance(participants, str):
                giveaway['participants'] = json.loads(participants)
            elif isinstance(participants, list):
                giveaway['participants'] = participants
            else:
                giveaway['participants'] = []
            active_giveaways[giveaway['giveaway_id']] = giveaway

        return active_giveaways
    finally:
        cursor.close()
        conn.close()

def update_giveaway_participants(giveaway_id: str, participants: List[int]):
    """Update giveaway participants"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE active_giveaways 
            SET participants = %s
            WHERE giveaway_id = %s
        ''', (json.dumps(participants), giveaway_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def remove_active_giveaway(giveaway_id: str):
    """Remove an active giveaway"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM active_giveaways WHERE giveaway_id = %s', (giveaway_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

# Pending Listings Functions
def add_pending_listing(user_id: int, listing_type: str, listing_data: Dict, channel_id: int):
    """Add a pending listing"""
    clean_data = listing_data.copy()
    if 'timeout_task' in clean_data:
        del clean_data['timeout_task']

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            DELETE FROM pending_listings 
            WHERE user_id = %s AND listing_type = %s
        ''', (user_id, listing_type))

        cursor.execute('''
            INSERT INTO pending_listings 
            (user_id, listing_type, listing_data, channel_id)
            VALUES (%s, %s, %s, %s)
        ''', (user_id, listing_type, json.dumps(clean_data), channel_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        release_db_connection(conn)

def get_pending_listing(user_id: int, listing_type: str) -> Optional[Dict]:
    """Get a pending listing"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''
                        SELECT * FROM pending_listings 
            WHERE user_id = %s AND listing_type = %s
        ''', (user_id, listing_type))
        result = cursor.fetchone()

        if result:
            listing_data = result['listing_data']
            if isinstance(listing_data, str):
                listing_data = json.loads(listing_data)
            return listing_data
        return None
    finally:
        cursor.close()
        release_db_connection(conn)

def remove_pending_listing(user_id: int, listing_type: str):
    """Remove a pending listing"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            DELETE FROM pending_listings 
            WHERE user_id = %s AND listing_type = %s
        ''', (user_id, listing_type))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def get_all_pending_listings(listing_type: str = None) -> Dict[int, Dict]:
    """Get all pending listings of a specific type, or all if no type specified"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if listing_type:
            cursor.execute('''
                SELECT * FROM pending_listings WHERE listing_type = %s
            ''', (listing_type,))
        else:
            cursor.execute('SELECT * FROM pending_listings')

        listings = cursor.fetchall()

        pending_listings = {}
        for listing in listings:
            user_id = listing['user_id']
            if user_id not in pending_listings:
                pending_listings[user_id] = {}
            pending_listings[user_id][listing['listing_type']] = json.loads(listing['listing_data'])

        return pending_listings
    finally:
        cursor.close()
        conn.close()

# Support and Report Functions
def add_support_ticket(user_id: int, channel_id: int, help_needed: str):
    """Add a support ticket"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO support_tickets (user_id, channel_id, help_needed)
            VALUES (%s, %s, %s)
        ''', (user_id, channel_id, help_needed))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def add_report_ticket(reporter_id: int, reported_username: str, reason: str, channel_id: int):
    """Add a report ticket"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO report_tickets (reporter_id, reported_username, reason, channel_id)
            VALUES (%s, %s, %s, %s)
        ''', (reporter_id, reported_username, reason, channel_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def close_support_ticket(channel_id: int):
    """Close a support ticket"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE support_tickets SET status = 'closed'
            WHERE channel_id = %s
        ''', (channel_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def close_report_ticket(channel_id: int):
    """Close a report ticket"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE report_tickets SET status = 'closed'
            WHERE channel_id = %s
        ''', (channel_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

# Car Recognition Functions
def load_car_models():
    """Load initial car models into the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) as count FROM car_models')
        result = cursor.fetchone()
        count = result[0] if result else 0

        if count == 0:
            car_data = [
                ("BMW M5 F90", ["F90", "M5 F90", "BMW F90", "M5"]),
                ("BMW M3 F80", ["F80", "M3 F80", "BMW F80", "M3"]),
                ("BMW M4 F82", ["F82", "M4 F82", "BMW F82", "M4"]),
                ("BMW M2 F87", ["F87", "M2 F87", "BMW F87", "M2"]),
                ("Audi RS6 C8", ["RS6", "C8", "RS6 C8", "Audi C8"]),
                ("Audi RS4 B9", ["RS4", "B9", "RS4 B9", "Audi B9"]),
                ("Audi RS3 8Y", ["RS3", "8Y", "RS3 8Y", "Audi 8Y"]),
                ("Mercedes C63 AMG W205", ["C63", "W205", "C63 W205", "AMG C63"]),
                ("Mercedes E63 AMG W213", ["E63", "W213", "E63 W213", "AMG E63"]),
                ("Mercedes A45 AMG W177", ["A45", "W177", "A45 W177", "AMG A45"]),
                ("Porsche 911 GT3 992", ["GT3", "992", "911 GT3", "992 GT3"]),
                ("Porsche 911 Turbo S 992", ["Turbo S", "992 Turbo", "911 Turbo S"]),
                ("Porsche Cayman GT4", ["GT4", "Cayman GT4", "718 GT4"]),
                ("McLaren 720S", ["720S", "McLaren 720"]),
                ("McLaren P1", ["P1", "McLaren P1"]),
                ("Ferrari 488 GTB", ["488", "488 GTB", "Ferrari 488"]),
                ("Ferrari F8 Tributo", ["F8", "F8 Tributo", "Ferrari F8"]),
                ("Lamborghini Huracan", ["Huracan", "Lambo Huracan"]),
                ("Lamborghini Aventador", ["Aventador", "Lambo Aventador"]),
                ("Nissan GT-R R35", ["GTR", "R35", "GT-R", "Nissan GTR"]),
                ("Toyota Supra A90", ["Supra", "A90", "Toyota A90"]),
                ("Honda Civic Type R FK8", ["Type R", "FK8", "Civic Type R"]),
                ("Subaru WRX STI", ["STI", "WRX", "Subaru STI"]),
                ("Mitsubishi Lancer Evolution", ["Evo", "Evolution", "Lancer Evo"]),
                ("Ford Mustang Shelby GT500", ["GT500", "Shelby", "Mustang GT500"]),
                ("Chevrolet Corvette C8", ["Corvette", "C8", "Vette"]),
                ("Dodge Challenger SRT Hellcat", ["Hellcat", "Challenger Hellcat"]),
                ("Tesla Model S Plaid", ["Model S", "Plaid", "Tesla S"]),
                ("Bugatti Chiron", ["Chiron", "Bugatti Chiron"]),
                ("Koenigsegg Regera", ["Regera", "Koenigsegg Regera"]),
            ]

            for model_name, aliases in car_data:
                cursor.execute('''
                    INSERT INTO car_models (model_name, aliases)
                    VALUES (%s, %s)
                ''', (model_name, json.dumps(aliases)))

            conn.commit()
            print(f"Loaded {len(car_data)} car models into database")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def recognize_car_model(car_input: str) -> Optional[int]:
    """Recognize a car model from user input and return the model ID"""
    if not car_input:
        return None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, model_name, aliases FROM car_models')
        car_models = cursor.fetchall()

        car_input_clean = car_input.strip().upper()

        for car in car_models:
            if car['model_name'].upper() == car_input_clean:
                return car['id']

        for car in car_models:
            model_name_upper = car['model_name'].upper()
            aliases = json.loads(car['aliases'])

            if car_input_clean in model_name_upper:
                return car['id']

            for alias in aliases:
                if alias.upper() == car_input_clean:
                    return car['id']
                if alias.upper() in car_input_clean or car_input_clean in alias.upper():
                    return car['id']

        return None
    finally:
        cursor.close()
        conn.close()

def record_car_listing(car_model_id: int, listing_type: str, user_id: int, message_id: int = None):
    """Record a car listing for statistics tracking"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO car_listing_stats (car_model_id, listing_type, user_id, message_id)
            VALUES (%s, %s, %s, %s)
        ''', (car_model_id, listing_type, user_id, message_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def get_car_listing_stats(car_model_id: int = None, listing_type: str = None) -> List[Dict]:
    """Get car listing statistics"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = '''
            SELECT cm.model_name, cls.listing_type, COUNT(*) as count
            FROM car_listing_stats cls
            JOIN car_models cm ON cls.car_model_id = cm.id
        '''
        params = []

        conditions = []
        if car_model_id:
            conditions.append('cls.car_model_id = %s')
            params.append(car_model_id)
        if listing_type:
            conditions.append('cls.listing_type = %s')
            params.append(listing_type)

        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)

        query += ' GROUP BY cm.model_name, cls.listing_type ORDER BY count DESC'

        cursor.execute(query, params)
        results = cursor.fetchall()
        return results
    finally:
        cursor.close()
        conn.close()

def count_car_models():
    """Count the number of car models stored in the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) as count FROM car_models')
        result = cursor.fetchone()
        return result[0] if result else 0
    finally:
        cursor.close()
        conn.close()

def get_all_car_listings():
    """Get all car listings from the car_listings table"""
    if not MYSQL_AVAILABLE:
        logger.warning("MySQL not available, returning empty car listings")
        return []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT * FROM car_listings ORDER BY car_name')
            results = cursor.fetchall()
            return results
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Error getting car listings: {e}", exc_info=True)
        return []

def resolve_car_shortcode(input_name):
    """Resolve a car shortcode to its full display name"""
    if not input_name or not input_name.strip():
        return input_name, input_name, []

    input_clean = input_name.strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT car_name, short_codes FROM car_listings WHERE short_codes IS NOT NULL AND short_codes != %s', ('',))
        results = cursor.fetchall()

        matches = []
        for row in results:
            car_name = row['car_name']
            short_codes = row['short_codes'] or ''

            if short_codes:
                codes_list = [code.strip() for code in short_codes.split(',')]
                for code in codes_list:
                    if code.lower() == input_clean.lower():
                        matches.append(car_name)
                        break

        if len(matches) == 1:
            return matches[0], input_clean, matches
        elif len(matches) > 1:
            return input_clean, input_clean, matches
        else:
            cursor.execute('SELECT car_name FROM car_listings WHERE LOWER(car_name) LIKE %s', (f'%{input_clean.lower()}%',))
            partial_matches = cursor.fetchall()

            if partial_matches:
                partial_match_names = [row['car_name'] for row in partial_matches]
                if len(partial_match_names) == 1:
                    return partial_match_names[0], input_clean, partial_match_names
                else:
                    return input_clean, input_clean, partial_match_names

            return input_clean, input_clean, []
    finally:
        cursor.close()
        conn.close()

def populate_car_listings():
    """Populate the car_listings table with the provided car list"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) as count FROM car_listings')
        result = cursor.fetchone()
        count = result[0] if result else 0

        if count == 0:
            car_names = [
                "BMW M2 Competition",
                "BMW M3 E36",
                "BMW M3 G80",
                "BMW M3 Touring",
                "BMW M4 CSL",
                "BMW M4 F82",
                "BMW M4 G82",
                "BMW M5 CS",
                "BMW M5 F10",
                "BMW M5 F90",
                "BMW M6 Gran Coupe",
                "BMW M8 Competition",
                "BMW M8 Gran Coupé",
                "BMW X6 M",
                "BMW X7",
                "Bugatti Chiron",
                "Bugatti Veyron",
                "Chevrolet C10",
                "Chevrolet Camaro SS",
                "Chevrolet Camaro ZL1",
                "Chevrolet Corvette C6",
                "Chevrolet Corvette C7",
                "Chevrolet Corvette C7 Z06",
                "Chevrolet Corvette C8",
                "Dodge Challenger Hellcat",
                "Dodge Challenger Redeye",
                "Dodge Challenger Widebody",
                "Dodge Viper VX",
                "Ferrari 458 Italia",
                "Ferrari 812 Superfast",
                "Ferrari Enzo",
                "Ferrari F12 Berlinetta",
                "Ferrari F40",
                "Ferrari F8 Tributo",
                "Ferrari Portofino",
                "Ford F-150 Raptor",
                "Ford GT",
                "Ford Mustang Cobra R",
                "Ford Mustang Fox Body",
                "Ford Mustang GT",
                "Ford Mustang GT500",
                "Honda NSX",
                "Koenigsegg Agera RS",
                "Koenigsegg Jesko",
                "Lamborghini Aventador SVJ",
                "Lamborghini Huracán Evo",
                "Lamborghini Huracán Performante",
                "Lexus LFA",
                "McLaren 600LT",
                "McLaren P1",
                "McLaren Senna",
                "Mercedes AMG GT",
                "Mercedes AMG GT Black Series",
                "Mercedes AMG GT 4-Door",
                "Mercedes SL 63",
                "Mercedes-Benz C 63 AMG",
                "Mercedes-Benz C 63 AMG Black Series",
                "Mercedes-Benz C 63 AMG Coupé",
                "Mercedes-Benz C 63 AMG Sedan",
                "Mercedes-Benz CLK GTR",
                "Mercedes-Benz CLS",
                "Mercedes-Benz E 63 AMG W212",
                "Mercedes-Benz E 63 AMG W213",
                "Mercedes-Benz G 500 4x4²",
                "Mercedes-Benz G 63 AMG",
                "Mercedes-Benz GLE Coupe",
                "Mercedes-Benz S 500",
                "Mercedes-Benz S 63 AMG Coupé",
                "Mercedes-Benz S-Class W222",
                "Mercedes-Benz S-Class W223",
                "Mercedes-Benz SLS AMG Black Series",
                "Nissan 370Z",
                "Nissan GT-R Nismo",
                "Nissan GT-R R35",
                "Nissan Silvia S15",
                "Nissan Skyline GT-R R33",
                "Nissan Skyline GT-R R34",
                "Pagani Zonda R",
                "Porsche 911 Carrera",
                "Porsche 911 GT2 RS",
                "Porsche 911 GT3",
                "Porsche 911 GT3 RS",
                "Porsche 911 Targa",
                "Porsche 911 Turbo S",
                "Porsche Cayman GT4",
                "Porsche Panamera",
                "Porsche Taycan",
                "Rolls-Royce Cullinan",
                "Rolls-Royce Dawn",
                "Subaru BRZ",
                "Subaru Impreza WRX STI Blobeye",
                "Subaru WRX STI",
                "Toyota Chaser",
                "Toyota GT86",
                "Toyota Supra MK4",
                "Volkswagen Passat B8",
                "Audi A5 Sportback",
                "Audi Q7",
                "Audi Q8",
                "Audi R8",
                "Audi R8 Spyder",
                "Audi RS 3 Sedan",
                "Audi RS 4 Avant",
                "Audi RS 6 Avant",
                "Audi RS 7 Sportback",
                "Audi RS Q8",
                "Audi S3 Sedan",
                "Audi TT RS",
                "Acura NSX",
                "DeLorean DMC-12"
            ]

            for car_name in car_names:
                cursor.execute('''
                    INSERT INTO car_listings (car_name, short_codes, list_count)
                    VALUES (%s, %s, %s)
                ''', (car_name, '', 0))

            conn.commit()
            print(f"Successfully inserted {len(car_names)} cars into car_listings table")
        else:
            print(f"Car listings table already contains {count} entries")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def populate_car_shortcodes():
    """Populate shortcodes for existing cars in car_listings table"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        shortcode_mappings = {
            "BMW M2 Competition": "M2, M2 Comp, F87",
            "BMW M3 E36": "M3, E36, M3 E36",
            "BMW M3 G80": "M3, G80, M3 G80",
            "BMW M3 Touring": "M3, G81, M3 Touring",
            "BMW M4 CSL": "M4, CSL, G82 CSL",
            "BMW M4 F82": "M4, F82, M4 F82",
            "BMW M4 G82": "M4, G82, M4 G82",
            "BMW M5 CS": "M5, CS, F90 CS",
            "BMW M5 F10": "M5, F10, M5 F10",
            "BMW M5 F90": "M5, F90, M5 F90",
            "BMW M6 Gran Coupe": "M6, F06, Gran Coupe",
            "BMW M8 Competition": "M8, G15, M8 Comp",
            "BMW M8 Gran Coupé": "M8, G16, Gran Coupe",
            "BMW X6 M": "X6M, E71, X6 M",
            "BMW X7": "X7, G07, X7",
            "Audi A5 Sportback": "A5, B9, A5 Sportback",
            "Audi Q7": "Q7, 4M, Q7",
            "Audi Q8": "Q8, 4M, Q8",
            "Audi R8": "R8, 4S, R8",
            "Audi R8 Spyder": "R8, 4S, R8 Spyder",
            "Audi RS 3 Sedan": "RS3, 8Y, RS3 Sedan",
            "Audi RS 4 Avant": "RS4, B9, RS4 Avant",
            "Audi RS 6 Avant": "RS6, C8, RS6 Avant",
            "Audi RS 7 Sportback": "RS7, C8, RS7",
            "Audi RS Q8": "RSQ8, 4M, RS Q8",
            "Audi S3 Sedan": "S3, 8Y, S3 Sedan",
            "Audi TT RS": "TTRS, 8S, TT RS",
            "Mercedes AMG GT": "AMG GT, C190, GT",
            "Mercedes AMG GT Black Series": "GT BS, C190, Black Series",
            "Mercedes AMG GT 4-Door": "GT 63, X290, GT 4-Door",
            "Mercedes SL 63": "SL63, R232, SL 63",
            "Mercedes-Benz C 63 AMG": "C63, W205, C63 AMG",
            "Mercedes-Benz C 63 AMG Black Series": "C63 BS, W204, Black Series",
            "Mercedes-Benz C 63 AMG Coupé": "C63, C205, C63 Coupe",
            "Mercedes-Benz C 63 AMG Sedan": "C63, W205, C63 Sedan",
            "Mercedes-Benz CLK GTR": "CLK GTR, C297, CLK GTR",
            "Mercedes-Benz CLS": "CLS, C257, CLS",
            "Mercedes-Benz E 63 AMG W212": "E63, W212, E63 W212",
            "Mercedes-Benz E 63 AMG W213": "E63, W213, E63 W213",
            "Mercedes-Benz G 500 4x4²": "G500, W463, 4x4",
            "Mercedes-Benz G 63 AMG": "G63, W463, G63 AMG",
            "Mercedes-Benz GLE Coupe": "GLE, C167, GLE Coupe",
            "Mercedes-Benz S 500": "S500, W223, S500",
            "Mercedes-Benz S 63 AMG Coupé": "S63, C217, S63 Coupe",
            "Mercedes-Benz S-Class W222": "S Class, W222, S Class W222",
            "Mercedes-Benz S-Class W223": "S Class, W223, S Class W223",
            "Mercedes-Benz SLS AMG Black Series": "SLS, C197, SLS BS",
            "Porsche 911 Carrera": "911, 992, Carrera",
            "Porsche 911 GT2 RS": "GT2RS, 991, GT2 RS",
            "Porsche 911 GT3": "GT3, 992, GT3",
            "Porsche 911 GT3 RS": "GT3RS, 992, GT3 RS",
            "Porsche 911 Targa": "911, 992, Targa",
            "Porsche 911 Turbo S": "Turbo S, 992, 911 Turbo",
            "Porsche Cayman GT4": "GT4, 718, Cayman GT4",
            "Porsche Panamera": "Panamera, G2, Panamera",
            "Porsche Taycan": "Taycan, J1, Taycan",
            "Ferrari 458 Italia": "458, 458 Italia, F142",
            "Ferrari 812 Superfast": "812, 812 Superfast, F12M",
            "Ferrari Enzo": "Enzo, F60, Enzo",
            "Ferrari F12 Berlinetta": "F12, F12 Berlinetta, F152",
            "Ferrari F40": "F40, F40, F120",
            "Ferrari F8 Tributo": "F8, F8 Tributo, F142M",
            "Ferrari Portofino": "Portofino, F164, Portofino",
            "Lamborghini Aventador SVJ": "Aventador, SVJ, LP770",
            "Lamborghini Huracán Evo": "Huracan, Evo, LP640",
            "Lamborghini Huracán Performante": "Huracan, Performante, LP640",
            "McLaren 600LT": "600LT, 600LT, P13",
            "McLaren P1": "P1, P1, P12",
            "McLaren Senna": "Senna, P15, Senna",
            "Nissan 370Z": "370Z, Z34, 370Z",
            "Nissan GT-R Nismo": "GTR, R35, GT-R Nismo",
            "Nissan GT-R R35": "GTR, R35, GT-R",
            "Nissan Silvia S15": "S15, S15, Silvia",
            "Nissan Skyline GT-R R33": "R33, R33, Skyline",
            "Nissan Skyline GT-R R34": "R34, R34, Skyline",
            "Ford F-150 Raptor": "Raptor, F150, F-150",
            "Ford GT": "Ford GT, GT40, GT",
            "Ford Mustang Cobra R": "Cobra R, SVT, Mustang",
            "Ford Mustang Fox Body": "Fox Body, SN95, Mustang",
            "Ford Mustang GT": "Mustang GT, S550, Mustang",
            "Ford Mustang GT500": "GT500, Shelby, S550",
            "Chevrolet C10": "C10, C10, Pickup",
            "Chevrolet Camaro SS": "Camaro SS, SS, Camaro",
            "Chevrolet Camaro ZL1": "ZL1, Camaro ZL1, Camaro",
            "Chevrolet Corvette C6": "C6, Corvette C6, Vette C6",
            "Chevrolet Corvette C7": "C7, Corvette C7, Vette C7",
            "Chevrolet Corvette C7 Z06": "Z06, C7 Z06, Corvette Z06",
            "Chevrolet Corvette C8": "C8, Corvette C8, Vette C8",
            "Dodge Challenger Hellcat": "Hellcat, SRT, Challenger",
            "Dodge Challenger Redeye": "Redeye, SRT, Challenger",
            "Dodge Challenger Widebody": "Widebody, SRT, Challenger",
            "Dodge Viper VX": "Viper, VX, SRT",
            "Toyota Chaser": "Chaser, JZX100, Chaser",
            "Toyota GT86": "GT86, ZN6, 86",
            "Toyota Supra MK4": "Supra, MK4, A80",
            "Subaru BRZ": "BRZ, ZC6, BRZ",
            "Subaru Impreza WRX STI Blobeye": "STI, GDB, Blobeye",
            "Subaru WRX STI": "STI, VA, WRX",
            "Honda NSX": "NSX, NA1, NSX",
            "Acura NSX": "NSX, NC1, NSX",
            "Bugatti Chiron": "Chiron, Chiron, W16",
            "Bugatti Veyron": "Veyron, Veyron, W16",
            "Koenigsegg Agera RS": "Agera, RS, Agera",
            "Koenigsegg Jesko": "Jesko, Jesko, Track",
            "Lexus LFA": "LFA, LFA, V10",
            "Pagani Zonda R": "Zonda, R, Zonda",
            "Rolls-Royce Cullinan": "Cullinan, Cullinan, SUV",
            "Rolls-Royce Dawn": "Dawn, Dawn, Convertible",
            "Volkswagen Passat B8": "Passat, B8, Passat",
            "DeLorean DMC-12": "DeLorean, DMC, Back to Future"
        }

        updated_count = 0
        for car_name, shortcodes in shortcode_mappings.items():
            cursor.execute('''
                UPDATE car_listings 
                SET short_codes = %s 
                WHERE car_name = %s AND (short_codes IS NULL OR short_codes = %s)
            ''', (shortcodes, car_name, ''))
            if cursor.rowcount > 0:
                updated_count += 1

        conn.commit()
        if updated_count > 0:
            print(f"Updated {updated_count} cars with shortcodes")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def delete_car_listing(car_name: str):
    """Delete a car from the car_listings table"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM car_listings WHERE car_name = %s', (car_name,))
        deleted_count = cursor.rowcount
        conn.commit()

        if deleted_count > 0:
            print(f"Successfully deleted '{car_name}' from car_listings table")
        else:
            print(f"Car '{car_name}' not found in car_listings table")

        return deleted_count > 0
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

# Car Price Logging Functions
def log_car_price(car_name: str, price_text: str, user_id: int, username: str, message_id: int = None):
    """Log a car price from a sell listing"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        price_numeric = extract_numeric_price(price_text)

        cursor.execute('''
            INSERT INTO car_price_logs (car_name, price_text, price_numeric, user_id, username, message_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (car_name, price_text, price_numeric, user_id, username, message_id))
        conn.commit()
        print(f"Logged price for {car_name}: {price_text} (User: {username})")
    except Exception as e:
        conn.rollback()
        print(f"Error logging car price: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def extract_numeric_price(price_text: str) -> int:
    """Extract numeric price from price text"""
    import re
    if not price_text:
        return None

    price_clean = re.sub(r'[^\d,.]', '', price_text)
    price_clean = price_clean.replace(',', '')

    try:
        if '.' in price_clean:
            return int(float(price_clean))
        else:
            return int(price_clean)
    except (ValueError, TypeError):
        return None

def get_car_price_logs(car_name: str = None, limit: int = 100) -> List[Dict]:
    """Get car price logs, optionally filtered by car name"""
    if not MYSQL_AVAILABLE:
        logger.warning("MySQL not available, returning empty price logs")
        return []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            if car_name:
                cursor.execute('''
                    SELECT * FROM car_price_logs 
                    WHERE car_name = %s 
                    ORDER BY created_at DESC 
                    LIMIT %s
                ''', (car_name, limit))
            else:
                cursor.execute('''
                    SELECT * FROM car_price_logs 
                    ORDER BY created_at DESC 
                    LIMIT %s
                ''', (limit,))

            results = cursor.fetchall()
            return results
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Error getting car price logs: {e}", exc_info=True)
        return []

def get_car_price_stats(car_name: str = None) -> List[Dict]:
    """Get price statistics for cars"""
    if not MYSQL_AVAILABLE:
        logger.warning("MySQL not available, returning empty price stats")
        return []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            if car_name:
                cursor.execute('''
                    SELECT 
                        car_name,
                        COUNT(*) as listing_count,
                        AVG(price_numeric) as avg_price,
                        MIN(price_numeric) as min_price,
                        MAX(price_numeric) as max_price
                    FROM car_price_logs 
                    WHERE car_name = %s AND price_numeric IS NOT NULL
                    GROUP BY car_name
                ''', (car_name,))
            else:
                cursor.execute('''
                    SELECT 
                        car_name,
                        COUNT(*) as listing_count,
                        AVG(price_numeric) as avg_price,
                        MIN(price_numeric) as min_price,
                        MAX(price_numeric) as max_price
                    FROM car_price_logs 
                    WHERE price_numeric IS NOT NULL
                    GROUP BY car_name
                    ORDER BY listing_count DESC
                ''')

            results = cursor.fetchall()
            return results
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Error getting car price stats: {e}", exc_info=True)
        return []

def get_recent_price_logs(limit: int = 50) -> List[Dict]:
    """Get recent price logs across all cars"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''
            SELECT * FROM car_price_logs 
            ORDER BY created_at DESC 
            LIMIT %s
        ''', (limit,))

        results = cursor.fetchall()
        return results
    finally:
        cursor.close()
        conn.close()

# =============================================================================
# INGAME ID SECURITY SYSTEM FUNCTIONS
# =============================================================================

def add_user_ingame_id(discord_id: int, ingame_id: str) -> bool:
    """Add a user's ingame ID to the database"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute('''
                INSERT INTO user_ingame_ids (discord_id, ingame_id)
                VALUES (%s, %s)
            ''', (discord_id, ingame_id.upper()))
            logger.info(f"Added ingame ID {ingame_id} for user {discord_id}")
            return True
    except MySQLError as e:
        if e.errno == 1062:  # Duplicate entry error
            logger.warning(f"Attempted to add duplicate ingame ID {ingame_id} or discord ID {discord_id}")
            return False
        else:
            logger.error(f"MySQL error adding ingame ID: {e}", exc_info=True)
            return False
    except Exception as e:
        logger.error(f"Error adding ingame ID: {e}", exc_info=True)
        return False

def get_user_ingame_id(discord_id: int) -> Optional[str]:
    """Get a user's ingame ID by Discord ID"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute('''
                SELECT ingame_id FROM user_ingame_ids 
                WHERE discord_id = %s
            ''', (discord_id,))
            result = cursor.fetchone()
            return result['ingame_id'] if result else None
    except Exception as e:
        logger.error(f"Error getting ingame ID for user {discord_id}: {e}", exc_info=True)
        return None

def get_discord_by_ingame_id(ingame_id: str) -> Optional[int]:
    """Get Discord ID by ingame ID"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute('''
                SELECT discord_id FROM user_ingame_ids 
                WHERE ingame_id = %s
            ''', (ingame_id.upper(),))
            result = cursor.fetchone()
            return result['discord_id'] if result else None
    except Exception as e:
        logger.error(f"Error getting Discord ID for ingame ID {ingame_id}: {e}", exc_info=True)
        return None

def update_user_ingame_id(discord_id: int, new_ingame_id: str) -> bool:
    """Update a user's ingame ID"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute('''
                UPDATE user_ingame_ids 
                SET ingame_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE discord_id = %s
            ''', (new_ingame_id.upper(), discord_id))
            
            if cursor.rowcount > 0:
                logger.info(f"Updated ingame ID to {new_ingame_id} for user {discord_id}")
                return True
            else:
                logger.warning(f"No ingame ID found to update for user {discord_id}")
                return False
    except MySQLError as e:
        if e.errno == 1062:  # Duplicate entry error
            logger.warning(f"Attempted to update to duplicate ingame ID {new_ingame_id}")
            return False
        else:
            logger.error(f"MySQL error updating ingame ID: {e}", exc_info=True)
            return False
    except Exception as e:
        logger.error(f"Error updating ingame ID: {e}", exc_info=True)
        return False

def ingame_id_exists(ingame_id: str) -> bool:
    """Check if an ingame ID already exists in the database"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute('''
                SELECT COUNT(*) as count FROM user_ingame_ids 
                WHERE ingame_id = %s
            ''', (ingame_id.upper(),))
            result = cursor.fetchone()
            return result['count'] > 0 if result else False
    except Exception as e:
        logger.error(f"Error checking ingame ID existence: {e}", exc_info=True)
        return False

def delete_user_ingame_id(discord_id: int) -> bool:
    """Delete a user's ingame ID"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute('''
                DELETE FROM user_ingame_ids 
                WHERE discord_id = %s
            ''', (discord_id,))
            
            if cursor.rowcount > 0:
                logger.info(f"Deleted ingame ID for user {discord_id}")
                return True
            else:
                logger.warning(f"No ingame ID found to delete for user {discord_id}")
                return False
    except Exception as e:
        logger.error(f"Error deleting ingame ID: {e}", exc_info=True)
        return False

def get_all_ingame_ids() -> List[Dict[str, Any]]:
    """Get all ingame ID mappings (admin function)"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute('''
                SELECT discord_id, ingame_id, created_at, updated_at 
                FROM user_ingame_ids 
                ORDER BY created_at DESC
            ''')
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting all ingame IDs: {e}", exc_info=True)
        return []

def extract_ingame_ids_from_text(text: str) -> List[str]:
    """Extract all potential ingame IDs from text"""
    if not text:
        return []
    
    # Find all matches using the extraction pattern (no anchors)
    matches = INGAME_ID_EXTRACT_PATTERN.findall(text.upper())
    return list(set(matches))  # Remove duplicates

if __name__ == "__main__":
    init_connection_pool()
    populate_car_listings()
    populate_car_shortcodes()
