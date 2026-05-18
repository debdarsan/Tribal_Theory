from datetime import datetime

def get_date_time_stamp():
    date_time = datetime.now()
    date_time_stamp = date_time.strftime("%d-%b-%Y-%I%p-%M-%S")

    return date_time_stamp

def get_date_time_stamp_compact():
    date_time = datetime.now()
    # Adjusted date and time format
    date_time_stamp = date_time.strftime("%y%m%d%H%M%S")
    
    return date_time_stamp

# print(get_date_time_stamp())
# print(get_date_time_stamp_compact())