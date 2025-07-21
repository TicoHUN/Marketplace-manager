import time
from typing import Any, Optional, Dict, Tuple
from collections import defaultdict
import asyncio
from logger_config import get_logger

logger = get_logger("cache")

class CacheEntry:
    """Represents a single cache entry with TTL"""
    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.created_at = time.time()
        self.ttl = ttl
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        return time.time() - self.created_at > self.ttl
    
    def get_age(self) -> float:
        """Get age of cache entry in seconds"""
        return time.time() - self.created_at

class SimpleCache:
    """Simple in-memory cache with TTL support"""
    
    def __init__(self, default_ttl: int = 300, max_size: int = 1000):
        self.cache: Dict[str, CacheEntry] = {}
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expired': 0
        }
        
        # Start cleanup task (only if event loop is running)
        try:
            asyncio.create_task(self._cleanup_expired())
        except RuntimeError:
            # Event loop not running, cleanup will be handled manually
            pass
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key not in self.cache:
            self.stats['misses'] += 1
            return None
        
        entry = self.cache[key]
        if entry.is_expired():
            del self.cache[key]
            self.stats['expired'] += 1
            self.stats['misses'] += 1
            return None
        
        self.stats['hits'] += 1
        return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache"""
        if ttl is None:
            ttl = self.default_ttl
        
        # Check if we need to evict entries
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        self.cache[key] = CacheEntry(value, ttl)
        logger.debug(f"Cached key: {key} with TTL: {ttl}")
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if key in self.cache:
            del self.cache[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()
        logger.info("Cache cleared")
    
    def _evict_oldest(self) -> None:
        """Evict oldest cache entry"""
        if not self.cache:
            return
        
        oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].created_at)
        del self.cache[oldest_key]
        self.stats['evictions'] += 1
        logger.debug(f"Evicted oldest cache entry: {oldest_key}")
    
    async def _cleanup_expired(self) -> None:
        """Background task to clean up expired entries"""
        while True:
            try:
                expired_keys = [
                    key for key, entry in self.cache.items() 
                    if entry.is_expired()
                ]
                
                for key in expired_keys:
                    del self.cache[key]
                    self.stats['expired'] += 1
                
                if expired_keys:
                    logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                
                # Run cleanup every 5 minutes
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")
                await asyncio.sleep(60)  # Retry after 1 minute on error
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hit_rate_percent': round(hit_rate, 2),
            'total_hits': self.stats['hits'],
            'total_misses': self.stats['misses'],
            'total_evictions': self.stats['evictions'],
            'total_expired': self.stats['expired']
        }

class CacheManager:
    """Manager for different cache instances"""
    
    def __init__(self):
        # Different caches for different data types
        self.user_listings_cache = SimpleCache(default_ttl=300, max_size=500)  # 5 minutes
        self.car_listings_cache = SimpleCache(default_ttl=1800, max_size=100)  # 30 minutes
        self.user_sales_cache = SimpleCache(default_ttl=600, max_size=300)     # 10 minutes
        self.active_deals_cache = SimpleCache(default_ttl=60, max_size=200)    # 1 minute
        
        logger.info("Cache manager initialized")
    
    def get_user_listings(self, user_id: int) -> Optional[Any]:
        """Get user listings from cache"""
        return self.user_listings_cache.get(f"user_listings_{user_id}")
    
    def set_user_listings(self, user_id: int, listings: Any) -> None:
        """Set user listings in cache"""
        self.user_listings_cache.set(f"user_listings_{user_id}", listings)
    
    def invalidate_user_listings(self, user_id: int) -> None:
        """Invalidate user listings cache"""
        self.user_listings_cache.delete(f"user_listings_{user_id}")
    
    def get_user_sales(self, user_id: int) -> Optional[int]:
        """Get user sales count from cache"""
        return self.user_sales_cache.get(f"user_sales_{user_id}")
    
    def set_user_sales(self, user_id: int, sales_count: int) -> None:
        """Set user sales count in cache"""
        self.user_sales_cache.set(f"user_sales_{user_id}", sales_count)
    
    def invalidate_user_sales(self, user_id: int) -> None:
        """Invalidate user sales cache"""
        self.user_sales_cache.delete(f"user_sales_{user_id}")
    
    def get_car_listings(self) -> Optional[Any]:
        """Get car listings from cache"""
        return self.car_listings_cache.get("all_car_listings")
    
    def set_car_listings(self, listings: Any) -> None:
        """Set car listings in cache"""
        self.car_listings_cache.set("all_car_listings", listings)
    
    def get_active_deal(self, channel_id: int) -> Optional[Any]:
        """Get active deal from cache"""
        return self.active_deals_cache.get(f"active_deal_{channel_id}")
    
    def set_active_deal(self, channel_id: int, deal: Any) -> None:
        """Set active deal in cache"""
        self.active_deals_cache.set(f"active_deal_{channel_id}", deal)
    
    def invalidate_active_deal(self, channel_id: int) -> None:
        """Invalidate active deal cache"""
        self.active_deals_cache.delete(f"active_deal_{channel_id}")
    
    def clear_all(self) -> None:
        """Clear all caches"""
        self.user_listings_cache.clear()
        self.car_listings_cache.clear()
        self.user_sales_cache.clear()
        self.active_deals_cache.clear()
        logger.info("All caches cleared")
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """Get statistics for all caches"""
        return {
            'user_listings': self.user_listings_cache.get_stats(),
            'car_listings': self.car_listings_cache.get_stats(),
            'user_sales': self.user_sales_cache.get_stats(),
            'active_deals': self.active_deals_cache.get_stats()
        }

# Global cache manager instance
cache_manager = CacheManager()

# Convenience functions
def get_cached_user_listings(user_id: int) -> Optional[Any]:
    """Get user listings from cache"""
    return cache_manager.get_user_listings(user_id)

def cache_user_listings(user_id: int, listings: Any) -> None:
    """Cache user listings"""
    cache_manager.set_user_listings(user_id, listings)

def invalidate_user_cache(user_id: int) -> None:
    """Invalidate all user-related caches"""
    cache_manager.invalidate_user_listings(user_id)
    cache_manager.invalidate_user_sales(user_id)