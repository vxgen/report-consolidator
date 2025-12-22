import streamlit as st
import pandas as pd
from datetime import datetime

# --- 0. GLOBAL CONFIGURATION ---
# The specific sheet for User Registration/Login
USER_SHEET_URL = "https://docs.google.com/spreadsheets/d/1KG8qWTYLa6GEWByYIg2vz3bHrGdW3gvqD_detwhyj7k/edit?gid=522749285#gid=522749285"

# --- 1. ROBUST IMPORT CHECK ---
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    st.error("The 'st-gsheets-connection' library is not installed correctly. Please check requirements.txt.")
    st.stop()

# --- 2. PAGE CONFIGURATION ---
st.set_page_config(page_title="Cloud Inventory Manager", layout="wide")

# --- 3. AUTHENTICATION & REGISTRATION SYSTEM ---
def check_password():
    """Returns True if the user has a valid login."""
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("🔐 Inventory System Access")
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Register New User"])

    with tab1:
        with st.form("login_form"):
            user = st.text_input("Username").strip() # Auto-trim spaces
            pw = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Login"):
                try:
                    user_db = conn.read(spreadsheet=USER_SHEET_URL, worksheet="users", ttl=0)
                    # Case-insensitive username check
                    match = user_db[(user_db['username'].astype(str).str.lower() == user.lower()) & 
                                    (user_db['password'].astype(str) == pw)]
                    if not match.empty:
                        st.session_state["password_correct"] = True
                        st.session_state["current_user"] = user
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
                except Exception as e:
                    st.error(f"Login Error: Ensure the 'users' tab exists and is shared. Error: {e}")

    with tab2:
        st.info("Registration adds your credentials to the cloud database.")
        with st.form("register_form"):
            new_user = st.text_input("Choose a Username").strip()
            new_pw = st.text_input("Choose a Password", type="password").strip()
            confirm_pw = st.text_input("Confirm Password", type="password").strip()
            
            if st.form_submit_button("Create Account"):
                try:
                    user_db = conn.read(spreadsheet=USER_SHEET_URL, worksheet="users", ttl=0)
                    if new_user.lower() in user_db['username'].astype(str).str.lower().values:
                        st.warning("Username already exists!")
                    elif new_pw != confirm_pw:
                        st.error("Passwords do not match")
                    elif len(new_pw) < 4:
                        st.error("Password must be at least 4 characters")
                    else:
                        new_entry = pd.DataFrame([{"username": str(new_user), "password": str(new_pw)}])
                        updated_users = pd.concat([user_db, new_entry], ignore_index=True)
                        conn.update(spreadsheet=USER_SHEET_URL, worksheet="users", data=updated_users)
                        st.success("Account created successfully! Please switch to the Login tab.")
                except Exception as e:
                    st.error(f"Registration Error: {e}")
    return False

# --- 4. MAIN APPLICATION LOGIC ---
if check_password():
    # Connection for report data (Uses default sheet from Secrets)
    conn_reports = st.connection("gsheets", type=GSheetsConnection)
    
    # Sidebar Info
    st.sidebar.title("👤 User Profile")
    st.sidebar.write(f"Logged in as: **{st.session_state.get('current_user', 'User')}**")
    if st.sidebar.button("Log Out"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title("☁️ Cloud Inventory Consolidator")

    # Target Column State
    if 'target_columns' not in st.session_state:
        st.session_state.target_columns = ["Category", "SKU", "Product Name", "Product Description", "Stock on Hand", "Sold QTY"]

    # --- STEP 1: SCHEMA CONFIGURATION ---
    with st.expander("⚙️ Step 1: Configure Target Format"):
        cols_to_remove = []
        for i, col in enumerate(st.session_state.target_columns):
            c1, c2 = st.columns([5, 1])
            st.session_state.target_columns[i] = c1.text_input(f"Col {i+1}", value=col, key=f"edit_{i}")
            if c2.button("🗑️", key=f"del_{i}"): cols_to_remove.append(col)
        
        for col in cols_to_remove: 
            st.session_state.target_columns.remove(col)
            st.rerun()
            
        nc1, nc2 = st.columns([5, 1])
        new_name = nc1.text_input("New Column Name:")
        if nc2.button("➕ Add"):
            if new_name: 
                st.session_state.target_columns.append(new_name)
                st.rerun()

    # --- STEP 2: UPLOAD & MAPPING ---
    st.header("📤 Step 2: Upload & Map")
    uploaded_files = st.file_uploader("Upload Files", type=["csv", "xlsx"], accept_multiple_files=True)

    if uploaded_files:
        for i, file in enumerate(uploaded_files):
            with st.container(border=True):
                st.subheader(f"📄 {file.name}")
                d_name = st.text_input("Friendly Name:", value=f"Import_{i+1}", key=f"d_{file.name}")
                
                df_source = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                
                mapping_dict = {}
                m_cols = st.columns(3)
                for idx, t_col in enumerate(st.session_state.target_columns):
                    mapping_dict[t_col] = m_cols[idx % 3].selectbox(f"Map to {t_col}", [None] + df_source.columns.tolist(), key=f"m_{file.name}_{t_col}")

                if st.button(f"Process & Save {d_name}", key=f"b_{file.name}"):
                    valid_maps = {v: k for k, v in mapping_dict.items() if v is not None}
                    if valid_maps:
                        new_df = df_source[list(valid_maps.keys())].rename(columns=valid_maps)
                        batch_id = f"ID_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                        new_df['batch_id'] = batch_id
                        new_df['upload_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        new_df['file_display_name'] = d_name
                        new_df['uploaded_by'] = st.session_state.get('current_user', 'Unknown')

                        try:
                            # Worksheet="Sheet1" refers to the main DATA sheet from your secrets
                            existing_data = conn_reports.read(worksheet="Sheet1", ttl=0)
                            updated_df = pd.concat([existing_data, new_df], ignore_index=True, sort=False)
                        except:
                            updated_df = new_df
                        
                        conn_reports.update(worksheet="Sheet1", data=updated_df)
                        st.success(f"Successfully saved {d_name} to Cloud!")
                        st.rerun()

    st.divider()

    # --- STEP 3: MANAGE CLOUD SEGMENTS ---
    st.header("📋 Step 3: Manage Cloud Segments")
    try:
        master_data = conn_reports.read(worksheet="Sheet1", ttl=0)
        if not master_data.empty and 'batch_id' in master_data.columns:
            unique_imports = master_data[['batch_id', 'file_display_name', 'upload_time', 'uploaded_by']].drop_duplicates()
            selected_batches = []
            
            for _, row in unique_imports.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([0.5, 4, 2])
                    if c1.checkbox("", key=f"sel_{row['batch_id']}"):
                        selected_batches.append(row['batch_id'])
                    
                    c2.write(f"**{row['file_display_name']}**")
                    c2.caption(f"Uploaded by: {row['uploaded_by']} | {row['upload_time']}")
                    
                    if c3.button("🗑️ Delete Segment", key=f"del_{row['batch_id']}"):
                        remaining = master_data[master_data['batch_id'] != row['batch_id']]
                        conn_reports.update(worksheet="Sheet1", data=remaining)
                        st.success("Segment deleted.")
                        st.rerun()

            if selected_batches:
                st.subheader("🔗 Combined Export")
                if st.button("Generate Combined Report"):
                    combined = master_data[master_data['batch_id'].isin(selected_batches)]
                    display_cols = [c for c in st.session_state.target_columns if c in combined.columns]
                    st.dataframe(combined[display_cols])
                    
                    csv = combined[display_cols].to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download CSV", data=csv, file_name="combined_inventory.csv")
        else:
            st.info("No cloud data available yet.")
    except Exception as e:
        st.error(f"Error accessing Cloud Data: {e}")
