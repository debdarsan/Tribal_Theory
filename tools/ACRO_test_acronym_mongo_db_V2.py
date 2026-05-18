import csv
import re
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from rich.console import Console
from rich.prompt import Prompt

def setup_variables():
    mongo_uri = Prompt.ask("Enter MongoDB URI", default="mongodb://localhost:27017/")
    file_name = Prompt.ask("Enter file name", default="AD-CHAT docs")
    csv_file_path = Prompt.ask("Enter CSV file path", default='./BIDA-Acronyms.csv')
    collection_name = Prompt.ask("Enter collection name", default="acronyms")
    client = MongoClient(mongo_uri)
    db = client[collection_name]  # Using the database 'acronyms'
    acronyms_collection = db.acronyms
    return mongo_uri, file_name, csv_file_path, db, collection_name, acronyms_collection

def reset_mongodb(db, collection_name):
    confirmation = Prompt.ask("Are you sure you want to reset the database? (yes/no)", default="no")
    if confirmation.lower() == 'yes':
        db[collection_name].drop()
        
def get_acronyms_from_text(source_text):
    if source_text:
        # Regex to find acronyms (Assuming acronyms are all caps, at least 2 letters)
        acronyms = re.findall(r'\b[A-Z]{2,}\b', source_text)
        return list(set(acronyms))
    return []

# Function to read acronyms from CSV and return as a dictionary
def read_acronyms_from_csv(csv_file_path):
    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header row
        return {rows[0]: rows[1] for rows in reader}

# Populate MongoDB with acronyms from CSV
def save_acronyms_to_mongodb(file_name, acronyms, acronyms_collection):
    acronyms_collection.update_one(
        {"file_name": file_name},
        {"$set": {"acronyms": acronyms}},
        upsert=True
    )

# Read and display acronyms from MongoDB
def get_all_acronyms_from_mongodb(file_name, acronyms_collection):
    document = acronyms_collection.find_one({"file_name": file_name})
    acronym_list = []
    if document:
        for acronym, meaning in document["acronyms"].items():
            acronym_list.append(f"{acronym}: {meaning}")
    return acronym_list

# Get acronyms and their meanings from MongoDB
def get_acronyms_meaning_from_mongodb(acronyms_collection, file_name, acronyms, enclose_in_parentheses):

    document = acronyms_collection.find_one({"file_name": file_name})
    additional_info = ""

    if document:
        for acronym in acronyms:
            if acronym in document["acronyms"]:
                meaning = document["acronyms"][acronym]
                if enclose_in_parentheses:
                    additional_info += f"\n({acronym} stands for {meaning})"
                else:
                    additional_info += f"\n{acronym} stands for {meaning}"
            else:
                if enclose_in_parentheses:
                    additional_info += f"\n(Meaning of the {acronym} is not defined in the document)"
                else:
                    additional_info += f"\nMeaning of {acronym} is not defined in the document"

    return additional_info

# Get acronym meaning from Google Search
def get_acronym_meaning_with_context_by_google_search(acronym, context):
    search_query = f"{acronym} meaning in {context}"
    search_url = f"https://www.google.com/search?q={search_query}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    meaning = None
    for g in soup.find_all(class_='BNeawe s3v9rd AP7Wnd'):
        text = g.get_text()
        if acronym in text:
            meaning = text
            break
    
    return meaning

# Integrate acronym meaning in the response
def integrate_acronym_meaning_in_response(
    acronyms_collection,
    acronyms, 
    enclose_in_parentheses,
    context,
    csv_file_path,
    method="from_mongodb", 
    source_document_name="NR Static Simulations",
):
    additional_info = ""

    if method == "from_csv":

        acronym_meanings = read_acronyms_from_csv(csv_file_path)
        for acronym in acronyms:
            meaning = acronym_meanings.get(acronym, "Not defined")
            if enclose_in_parentheses:
                additional_info += f"\n({acronym} stands for {meaning})"
            else:
                additional_info += f"\n{acronym} stands for {meaning}"

    elif method == "google_search":
        for acronym in acronyms:
            meaning = get_acronym_meaning_with_context_by_google_search(acronym, context)
            if meaning:
                # Append the meaning at the end of the response or modify as needed
                additional_info += f"\n({acronym} stands for {meaning})"

    elif method == "from_mongodb":
        additional_info = get_acronyms_meaning_from_mongodb(acronyms_collection, source_document_name, acronyms, enclose_in_parentheses)

    return additional_info

def main_menu():
    options = ["Read from CSV and save to MongoDB", "Display from MongoDB", \
               "Get from Google Search", "Get from CSV", "Get from MongoDB", "Reset MongoDB", "Exit"]
    choice = Prompt.ask("Choose an option", choices=options, show_choices=True)
    return options.index(choice) + 1

if __name__ == "__main__":
    mongo_uri, file_name, csv_file_path, db, collection_name, acronyms_collection = setup_variables()
    c = Console()
    while True:
        choice = main_menu()
        
        if choice == 1:
            csv_file_path = Prompt.ask("Enter CSV file path", default=csv_file_path)
            acronym_meanings = read_acronyms_from_csv(csv_file_path)
            save_acronyms_to_mongodb(file_name, acronym_meanings)
            c.print("Acronyms saved to MongoDB.", style="bold green")

        elif choice == 2:
            acronym_meanings = get_all_acronyms_from_mongodb(acronyms_collection, file_name)
            c.print("Acronyms and meanings from MongoDB:", style="bold green")
            c.print("\n".join(acronym_meanings), style="yellow")
            
        elif choice == 3:
            acronyms_input = Prompt.ask("Enter acronyms separated by commas")
            acronyms = [acronym.strip() for acronym in acronyms_input.split(',')]
            context = Prompt.ask("Enter context", default="5G Technology Telecom")
            response = integrate_acronym_meaning_in_response(acronyms, True, context, "", method="google_search")
            c.print("Acronyms and meanings from Google Search:", style="bold green")
            c.print(response, style="bold blue")
            
        elif choice == 4:
            csv_file_path = Prompt.ask("Enter CSV file path", default=csv_file_path)
            response = integrate_acronym_meaning_in_response(acronyms, True, context, csv_file_path, method="from_csv")
            c.print("Acronyms and meanings from CSV:", style="bold green")
            c.print(response, style="bold blue")
            
        elif choice == 5:
            text_input = Prompt.ask("Enter text with acronyms")
            acronyms = get_acronyms_from_text(text_input)
            if not acronyms:
                c.print("No acronyms found in the text.", style="bold red")
                continue
            response = integrate_acronym_meaning_in_response(acronyms, True, context, csv_file_path, method="from_mongodb")
            c.print("Acronyms and meanings from mongodb:", style="bold green")
            c.print(response, style="bold blue")
        
        elif choice == 6:
            reset_mongodb(db, collection_name)
            c.print("MongoDB has been reset.", style="bold red")
            
        elif choice == 7:
            c.print("Exiting the program.", style="bold red")
            break

        else:
            c.print("Invalid choice. Please try again.", style="bold yellow")