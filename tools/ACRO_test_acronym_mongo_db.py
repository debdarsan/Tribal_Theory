import csv
from pymongo import MongoClient
from rich.console import Console

# MongoDB setup
client = MongoClient("mongodb://mongo:27017/")
db = client.acronyms  # Using the database 'acronyms'
acronyms_collection = db.acronyms

file_name = "NR Static Simulations"
# Path to CSV file
csv_file_path = './BIDA-Acronyms.csv'
c = Console()
    
# Function to read acronyms from CSV and return as a dictionary
def read_acronyms_from_csv(csv_file_path):
    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header row
        return {rows[0]: rows[1] for rows in reader}

# Populate MongoDB with acronyms from CSV
def save_acronyms_to_mongodb(file_name, acronyms):
    client = MongoClient("mongodb://mongo:27017/")
    db = client.acronyms  # Database name is 'acronyms'
    acronyms_collection = db.acronyms
    acronyms_collection.update_one(
        {"file_name": file_name},
        {"$set": {"acronyms": acronyms}},
        upsert=True
    )

# Read and display acronyms from MongoDB
def display_acronyms_from_mongodb(file_name):
    client = MongoClient("mongodb://localhost:27017/")
    db = client.acronyms
    acronyms_collection = db.acronyms
    document = acronyms_collection.find_one({"file_name": file_name})

    if document:
        c.print("Acronyms for file:", file_name, style="bold green")
        for acronym, meaning in document["acronyms"].items():
            c.print(f"{acronym}: {meaning}", style="yellow")

# Read acronyms from CSV
acronym_meanings = read_acronyms_from_csv(csv_file_path)
save_acronyms_to_mongodb(file_name, acronym_meanings)
display_acronyms_from_mongodb(file_name)
