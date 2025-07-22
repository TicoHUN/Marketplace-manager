
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_mysql import recognize_car_model, record_car_listing

def process_car_listing(car_name: str, listing_type: str, user_id: int, message_id: int = None):
    """Process a car listing for recognition and statistics tracking"""
    if not car_name:
        return
    
    # Try to recognize the car model
    car_model_id = recognize_car_model(car_name)
    
    if car_model_id:
        # Record the listing for statistics
        record_car_listing(car_model_id, listing_type, user_id, message_id)
        print(f"Recognized and recorded car listing: {car_name} (ID: {car_model_id}) - {listing_type}")
    else:
        print(f"Could not recognize car model: {car_name}")
