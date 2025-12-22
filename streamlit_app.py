import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import time

# --- 0. GLOBAL CONFIGURATION ---
USER_SHEET_URL = "https://docs.google.com/spreadsheets/d/1KG8qWTYLa6GEWByYIg2vz3bHrGdW3gvqD_detwhyj7k/edit?gid=522749285#gid=522749285"

# --- 1. IMPORT CHECK ---
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    st.error("Missing libraries. Ensure 'requirements.txt' contains: st-gsheets-connection, pytz")
    st.stop()

# Helper for Sydney Time
def get_sydney_time():
    sydney_tz = pytz.timezone('Australia/Sydney')
    return datetime.now(sydney_tz).strftime("%Y-%m-%d %I:%M %p")

# --- 2. PAGE CONFIGURATION ---
st.set_page_config(page_title="Cloud Inventory Manager", layout="wide")

# --- 3. SECURE AUTHENTICATION SYSTEM ---
def check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("🔐 Inventory System Access")
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Register"])

    with tab1:
        with st.form("login_form"):
            user = st.text_input("Username").strip()
            pw = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Login"):
                try:
                    user_db = conn.read(spreadsheet=USER_SHEET_URL, worksheet="users", ttl="10s")
                    user_db.columns = user_db.columns.str.strip()
                    match = user_db[(user_db['username'].astype(str) == user) & 
                                    (user_db['password'].astype(str) == pw)]
                    
                    if not match.empty:
                        status = str(match.iloc[0]['approved']).strip().upper()
                        if status == "YES":
                            st.session_state["password_correct"] = True
                            st.session_state["current_user"] = user
                            st.rerun()
                        else:
                            st.warning("⚠️ Account pending approval.")
                    else:
                        st.error("❌ Invalid credentials")
                except Exception as e:
                    st.error(f"Login Error: {e}")
    
    with tab2:
        with st.form("register_form"):
            new_user = st.text_input("Choose Username").strip()
            new_pw = st.text_input("Choose Password", type="password").strip()
            confirm_pw = st.text_input("Confirm Password", type="password").strip()
            if st.form_submit_button("Create Account"):
                try:
                    user_db = conn.read(spreadsheet=USER_SHEET_URL, worksheet="users", ttl=0)
                    new_entry = pd.DataFrame([{"username": str(new_user), "password": str(new_pw), "approved": "NO"}])
                    updated_users = pd.concat([user_db, new_entry], ignore_index=True)
                    conn.update(spreadsheet=USER_SHEET_URL, worksheet="users", data=updated_users)
                    st.success("✅ Submitted! Wait for admin approval.")
                except Exception as e:
                    st.error(f"Registration Error: {e}")
    return False

# --- 4. MAIN APPLICATION LOGIC ---
if check_password():
    conn_reports = st.connection("gsheets", type=GSheetsConnection)
    
    st.sidebar.title("👤 User Profile")
    st.sidebar.write(f"Logged in: **{st.session_state['current_user']}**")
    st.sidebar.caption(f"Sydney Time: {get_sydney_time()}")
    if st.sidebar.button("Log Out"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title("☁️ Cloud Inventory Consolidator")
    
    main_tab, archive_tab = st.tabs(["🚀 Active Dashboard", "📁 Historical Archive"])

    with main_tab:
        if 'target_columns' not in st.session_state:
            st.session_state.target_columns = ["Category", "SKU", "Product Name", "Product Description", "Stock on Hand", "Sold QTY"]

        # --- RESTORED STEP 1: SCHEMA CONFIGURATION ---
        with st.expander("⚙️ Step 1: Configure Target Format"):
            st.write("Modify the columns you want in your final consolidated report:")
            cols_to_remove = []
            for i, col in enumerate(st.session_state.target_columns):
                c1, c2 = st.columns([5, 1])
                st.session_state.target_columns[i] = c1.text_input(f"Column {i+1}", value=col, key=f"edit_col_{i}")
                if c2.button("🗑️", key=f"del_col_{i}"):
                    cols_to_remove.append(col)
            
            for col in cols_to_remove:
                st.session_state.target_columns.remove(col)
                st.rerun()
                
            st.markdown("---")
            nc1, nc2 = st.columns([5, 1])
            new_col_name = nc1.text_input("Add New Column Name:", key="new_col_input")
            if nc2.button("➕ Add", key="add_col_btn"):
                if new_col_name and new_col_name not in st.session_state.target_columns:
                    st.session_state.target_columns.append(new_col_name)
                    st.rerun()

        # --- STEP 2: UPLOAD & MAP ---
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
                        mapping_dict[t_col] = m_cols[idx % 3].selectbox(f"Map {t_col}", [None] + df_source.columns.tolist(), key=f"m_{file.name}_{t_col}")

                    if st.button(f"Process & Save {d_name}", key=f"b_{file.name}"):
                        valid_maps = {v: k for k, v in mapping_dict.items() if v is not None}
                        if valid_maps:
                            new_df = df_source[list(valid_maps.keys())].rename(columns=valid_maps)
                            new_df['batch_id'] = f"ID_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                            new_df['upload_time'] = get_sydney_time()
                            new_df['file_display_name'] = d_name
                            new_df['uploaded_by'] = st.session_state['current_user']

                            try:
                                existing_data = conn_reports.read(worksheet="Sheet1", ttl=0)
                                updated_df = pd.concat([existing_data, new_df], ignore_index=True, sort=False)
                                conn_reports.update(worksheet="Sheet1", data=updated_df)
                                st.cache_data.clear()
                                st.success("Saved!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Save Error: {e}")

        st.divider()

        # --- RESTORED STEP 3: MANAGE SEGMENTS ---
        st.header("📋 Step 3: Manage Cloud Segments")
        try:
            master_data = conn_reports.read(worksheet="Sheet1", ttl="5s")
            if not master_data.empty and 'batch_id' in master_data.columns:
                unique_imports = master_data[['batch_id', 'file_display_name', 'upload_time', 'uploaded_by']].drop_duplicates()
                selected_batches = []
                
                for _, row in unique_imports.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([0.5, 4, 2])
                        if c1.checkbox("", key=f"sel_{row['batch_id']}"):
                            selected_batches.append(row['batch_id'])
                        c2.write(f"**{row['file_display_name']}**")
                        c2.caption(f"By: {row['uploaded_by']} | {row['upload_time']}")
                        
                        if c3.button("🗑️ Delete", key=f"del_{row['batch_id']}"):
                            remaining = master_data[master_data['batch_id'] != row['batch_id']]
                            conn_reports.update(worksheet="Sheet1", data=remaining)
                            st.cache_data.clear()
                            st.rerun()

                        # RESTORED: View & Download Expander
                        with st.expander("👁️ View & Download this Individual Report"):
                            individual_df = master_data[master_data['batch_id'] == row['batch_id']]
                            # Ensure we only display columns that exist in the mapping
                            display_cols = [c for c in st.session_state.target_columns if c in individual_df.columns]
                            st.dataframe(individual_df[display_cols], use_container_width=True)
                            
                            csv_ind = individual_df[display_cols].to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="📥 Download as CSV",
                                data=csv_ind,
                                file_name=f"{row['file_display_name']}_export.csv",
                                mime='text/csv',
                                key=f"dl_btn_{row['batch_id']}"
                            )

                if selected_batches:
                    st.markdown("---")
                    b1, b2 = st.columns(2)
                    if b1.button("📂 Archive Selected", key="main_archive_btn"):
                        with st.spinner("Archiving..."):
                            to_archive = master_data[master_data['batch_id'].isin(selected_batches)]
                            remaining = master_data[~master_data['batch_id'].isin(selected_batches)]
                            try:
                                archive_db = conn_reports.read(worksheet="archive", ttl=0)
                                updated_archive = pd.concat([archive_db, to_archive], ignore_index=True)
                                conn_reports.update(worksheet="archive", data=updated_archive)
                                conn_reports.update(worksheet="Sheet1", data=remaining)
                                st.cache_data.clear()
                                st.success("Moved to Archive!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Archive Error: {e}")
                    
                    if b2.button("📊 Generate Combined Report", key="main_combine_btn"):
                        combined = master_data[master_data['batch_id'].isin(selected_batches)]
                        st.dataframe(combined)
            else:
                st.info("No active segments.")
        except Exception as e:
            st.error(f"Data Error: {e}")

    with archive_tab:
        st.header("📁 Archived Data")
        try:
            archived_df = conn_reports.read(worksheet="archive", ttl=0)
            if archived_df is not None and not archived_df.empty:
                st.dataframe(archived_df, use_container_width=True)
                if st.button("🧹 Clear Archive"):
                    empty_df = pd.DataFrame(columns=archived_df.columns)
                    conn_reports.update(worksheet="archive", data=empty_df)
                    st.cache_data.clear()
                    st.success("Archive Cleared!")
                    time.sleep(1)
                    st.rerun()
            else:
                st.info("Archive is empty.")
        except Exception as e:
            st.error(f"Archive Tab Error: Ensure 'archive' tab exists. ({e})")
