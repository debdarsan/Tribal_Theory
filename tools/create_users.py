# Generate keys for authentication
import pickle
from pathlib import Path
import streamlit_authenticator as stauth
import pandas as pd

user_file = "users.xlsx"

df = pd.read_excel(user_file)

# Assuming the Excel file has columns 'Role', 'Username', 'Password'
roles = df['Role'].tolist()
usernames = df['User ID'].tolist()
passwords = df['Password'].tolist()

# Hashing passwords
hashed_passwords = stauth.Hasher(passwords).generate()

# Saving to auth.pkl
file_path =  "auth.pkl"
with open(file_path, "wb") as file:
    pickle.dump(hashed_passwords, file)