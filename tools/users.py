import streamlit as st
import pandas as pd
import pickle
from pathlib import Path
import streamlit_authenticator as stauth
import os

st.set_page_config(page_title="User Management", layout="wide")

# Add custom styling for the page background, text colors, and other elements
st.markdown(
    """
    <style>
    /* Main background color */
    .stApp {
        background-color: #383838; 
    }
    
    /* Header styling */
    .stTitleBlock {
        color: #FFBF00;
    }
    
    /* Text styling */
    p, div, h1, h2, h3, h4, h5, h6 {
        color: #FFBF00;  /* Dark blue text */
    }
    
    /* Button styling */
    .stButton>button {
        background-color: #000000; 
        color: white;
        font-weight: bold;
    }
    
    /* Sidebar styling - if you use it */
    .css-1d391kg {
        background-color: #e6f2ff;  /* Lighter blue for sidebar */
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Initialize session state
if 'users_df' not in st.session_state:
    # Check if file exists, if not create an empty DataFrame with required columns
    if os.path.exists('users.xlsx'):
        st.session_state.users_df = pd.read_excel('users.xlsx')
    else:
        st.session_state.users_df = pd.DataFrame(columns=['Full Name', 'User ID', 'Role', 'Password', 'Profile Image'])

# Function to save DataFrame to Excel
def save_dataframe():
    try:
        st.session_state.users_df.to_excel('users.xlsx', index=False)
        st.success("Users file updated successfully!")
    except Exception as e:
        st.error(f"Error saving users file: {e}")

# Function to generate auth.pkl
def generate_auth():
    try:
        # Read the latest data
        df = st.session_state.users_df
        
        # Extract the required fields
        usernames = df['User ID'].tolist()
        passwords = df['Password'].tolist()
        
        # Hash the passwords
        hashed_passwords = stauth.Hasher(passwords).generate()
        
        # Save to auth.pkl
        with open("auth.pkl", "wb") as file:
            pickle.dump(hashed_passwords, file)
        
        st.success("Authentication file generated successfully!")
    except Exception as e:
        st.error(f"Error generating authentication file: {e}")

# App title
st.title("User Management System")

# Create tabs for different sections
# Create tabs with larger font size
st.markdown(
    """
    <style>
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.5rem;
        font-weight: bold;
    }
    </style>
    """, 
    unsafe_allow_html=True
)
tab1, tab2 = st.tabs(["User List", "Create New User"])

with tab1:
    st.header("Current Users")
    
    # Display users in a dataframe excluding Profile Image column
    display_df = st.session_state.users_df.drop(columns=['Profile Image']) if 'Profile Image' in st.session_state.users_df.columns else st.session_state.users_df
    
    # Add checkboxes to each row
    st.write("Select users to remove:")
    selected_indices = []
    
    # Create a container for the dataframe and checkboxes
    user_container = st.container()
    
    with user_container:
        for idx, row in display_df.iterrows():
            col1, col2 = st.columns([0.1, 0.9])
            with col1:
                if st.checkbox("", key=f"check_{idx}"):
                    selected_indices.append(idx)
            with col2:
                st.write(f"{row['Full Name']} ({row['User ID']}) - Role: {row['Role']}")
    
    # Remove selected users button
    if st.button("Remove Selected Users"):
        if selected_indices:
            st.session_state.users_df = st.session_state.users_df.drop(index=selected_indices).reset_index(drop=True)
            save_dataframe()
            st.rerun()
        else:
            st.warning("No users selected for removal.")

with tab2:
    st.header("Create New User")
    
    # Form for creating a new user
    with st.form("create_user_form"):
        full_name = st.text_input("Full Name")
        user_id = st.text_input("User ID")
        
        # Define available roles (can be expanded)
        roles = ["user", "superuser"] #, "tester", "appraiser"]
        role = st.selectbox("Role", roles)
        
        password = st.text_input("Password", type="password")
        profile_image = "" # st.text_input("Profile Image URL", "https://i.imgur.com/sxFTDIl.gif")
        
        submitted = st.form_submit_button("Create User")
        
        if submitted:
            # Validate all fields are filled
            if all([full_name, user_id, role, password]):
                # Check if user ID already exists
                if user_id in st.session_state.users_df['User ID'].values:
                    st.error(f"User ID '{user_id}' already exists. Please choose a different one.")
                else:
                    # Add new user to DataFrame
                    new_user = pd.DataFrame({
                        'Full Name': [full_name],
                        'User ID': [user_id],
                        'Role': [role],
                        'Password': [password],
                        'Profile Image': [profile_image]
                    })
                    
                    st.session_state.users_df = pd.concat([st.session_state.users_df, new_user], ignore_index=True)
                    save_dataframe()
                    st.success(f"User '{full_name}' created successfully!")
            else:
                st.warning("All fields are required. Please fill in all the information.")

# Display the raw DataFrame at the bottom for verification
st.subheader("User Data (Debug View)")
st.dataframe(display_df)
# Button to generate authentication file
st.button("Generate Encoded Authentication", on_click=generate_auth)
