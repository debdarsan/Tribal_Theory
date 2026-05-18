from langchain_community.vectorstores import Chroma
import chromadb
from chromadb import Settings
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
import pandas as pd
import datetime

load_dotenv()

PERSIST_VECTORDB_DIR = "Chroma_VectorStore"

def load_vectorstore(PERSIST_VECTORDB_DIR):
    vdb = None
    record_count = 0
    # define an empty list of ids
    existing_ids = []
    CHROMA_SETTINGS = Settings(
                    persist_directory=PERSIST_VECTORDB_DIR,
                    # Prevent anonymous data collection by Chroma
                    anonymized_telemetry=False,
                )
    chroma_client = chromadb.PersistentClient(
        settings=CHROMA_SETTINGS, path=PERSIST_VECTORDB_DIR,   
    )
    embeddings = OpenAIEmbeddings()
    # define Chroma Vector DB
    vdb = Chroma(
        persist_directory=PERSIST_VECTORDB_DIR,
        embedding_function=embeddings,
        client_settings=CHROMA_SETTINGS,
        client=chroma_client,
    )
    try:
        record_count = vdb._collection.count()
        if record_count > 0:
            existing_ids = [str(id) for id in vdb._collection.get()["ids"]]
            metadata = [m for m in vdb._collection.get()["metadatas"]]
            record_count = vdb._collection.count()
        else:
            print(f"... New Chroma VDB is to be created at directory: {PERSIST_VECTORDB_DIR}",)
    except Exception as e:
        raise
    return vdb, existing_ids, metadata, record_count

vdb, existing_ids, metadata, record_count = load_vectorstore(PERSIST_VECTORDB_DIR)
# Create an empty set to store the unique file names
file_names = set()

# Loop through the metadata
for item in metadata:
    # Get the file name of the item
    file_name = item["File"]
    file_names.add(file_name)
    
# Create a dataframe to store the file names
df = pd.DataFrame({"File Name": sorted(list(file_names))})
df.index = df.index + 1
df.index.name = "No."
# Generate the current date in the format "dd-mon-yy"
current_date = datetime.datetime.now().strftime("%d-%b-%y")
file_name = f"Docs in Chroma on {current_date}.xlsx"

# Save the dataframe as an xlsx file with the modified file name
df.to_excel(file_name, index=True)

# Print the number and list of unique file names
print(f"There are {len(file_names)} unique file names in the database.")
print("The file names are:")
for i, file_name in enumerate(file_names, 1):
    print(f"{i}. {file_name}")
