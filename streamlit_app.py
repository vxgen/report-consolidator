import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import time

# --- 0. GLOBAL CONFIGURATION ---
USER_SHEET_URL = "https://docs.google.com/spreadsheets/d/1KG8qWTYLa6GEWByYIg2vz3bHrGdW3gvqD_detwhyj7k/edit"

# --- 1. IMPORT CHECK ---
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    st.error("Missing libraries. Ensure 'requirements.txt' includes: st-gsheets-connection, pytz")
    st.stop()

def get_sydney_time():
    sydney_tz = pytz.timezone('Australia/Sydney')
    return datetime.now(sydney_tz).strftime("%Y-%m-%d %H:%M:%S")

# --- 2. PAGE CONFIGURATION ---
st.set_page_config(page_title="Cloud Inventory Manager", layout="wide")

# --- 3. AUTHENTICATION & SIDEBAR ---
def check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    
    if st.session_state["password_correct"]:
        with st.sidebar:
            st.title("👤 User Profile")
            st.write(f"Logged in as: **{st.session_state.get('current_user', 'User')}**")
            if st.button("Log Out"):
                st.session_state["password_correct"] = False
                st.rerun()
        return True

    st.title("🔐 Inventory System Access")
    with st.form("login_form"):
        user = st.text_input("Username").strip()
        pw = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Login"):
            try:
                user_db = conn.read(spreadsheet=USER_SHEET_URL, worksheet="users", ttl="30s")
                user_db.columns = user_db.columns.str.strip()
                match = user_db[(user_db['username'].astype(str) == user) & (user_db['password'].astype(str) == pw)]
                if not match.empty and str(match.iloc[0]['approved']).strip().upper() == "YES":
                    st.session_state["password_correct"] = True
                    st.session_state["current_user"] = user
                    st.rerun()
                else: st.error("Access Denied.")
            except: st.error("Connection error.")
    return False

if check_password():
    conn_cloud = st.connection("gsheets", type=GSheetsConnection)
    
    if 'target_columns' not in st.session_state:
        st.session_state.target_columns = ["Category", "SKU", "Product Name", "Product Description", "Stock on Hand", "Sold QTY", "Sell In"]
    
    st.title("☁️ Cloud Inventory Consolidator")
    main_tab, preset_tab, archive_tab = st.tabs(["🚀 Active Dashboard", "🗺️ Mapping Presets", "📁 Historical Archive"])

    # --- TAB 2: MAPPING PRESETS (WITH SAMPLE UPLOAD) ---
    with preset_tab:
        st.header("🗺️ Manage Mapping Presets")
        try:
            presets_db = conn_cloud.read(worksheet="presets", ttl="0s")
        except:
            presets_db = pd.DataFrame(columns=["preset_id", "client_name", "rule_name"] + st.session_state.target_columns)

        with st.expander("➕ Add New Mapping Rule", expanded=True):
            st.subheader("Step A: (Optional) Upload Sample File to use Dropdowns")
            sample_file = st.file_uploader("Upload client report to see their headers:", type=["csv", "xlsx"], key="sample_up")
            
            sample_headers = []
            if sample_file:
                df_sample = pd.read_csv(sample_file) if sample_file.name.endswith('.csv') else pd.read_excel(sample_file)
                sample_headers = [str(c) for c in df_sample.columns]
                st.success(f"Loaded {len(sample_headers)} headers from {sample_file.name}")

            st.divider()
            st.subheader("Step B: Define Rule Details")
            with st.form("add_preset_form"):
                col_left, col_right = st.columns(2)
                p_client = col_left.text_input("Client Name (e.g., Umart)")
                p_rule = col_right.text_input("Rule Category (e.g., Laptops)")
                
                new_mapping = {"preset_id": f"PR_{int(time.time())}", "client_name": p_client, "rule_name": p_rule}
                
                st.write("**Map Target Columns to Source Headers:**")
                grid = st.columns(2)
                for idx, t_col in enumerate(st.session_state.target_columns):
                    with grid[idx % 2]:
                        if sample_headers:
                            # Use dropdown if sample is uploaded
                            new_mapping[t_col] = st.selectbox(f"Source Header for '{t_col}':", [None] + sample_headers, key=f"pre_drop_{t_col}")
                        else:
                            # Use text input if no sample
                            new_mapping[t_col] = st.text_input(f"Source Header for '{t_col}':", key=f"pre_txt_{t_col}")
                
                if st.form_submit_button("Save Rule"):
                    if p_client and p_rule:
                        updated_presets = pd.concat([presets_db, pd.DataFrame([new_mapping])], ignore_index=True)
                        conn_cloud.update(worksheet="presets", data=updated_presets)
                        st.success("New Rule Added to Database!")
                        time.sleep(1)
                        st.rerun()

        st.divider()
        # Search and Management logic...
        search = st.text_input("🔍 Search existing rules:").lower()
        if not presets_db.empty:
            for idx, row in presets_db.iterrows():
                if search in str(row['client_name']).lower() or search in str(row['rule_name']).lower():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([4, 1, 1])
                        c1.write(f"**{row['client_name']}** - {row['rule_name']}")
                        if c3.button("🗑️ Delete", key=f"del_{row['preset_id']}"):
                            conn_cloud.update(worksheet="presets", data=presets_db.drop(idx))
                            st.rerun()
                        with c2.expander("✏️ Edit"):
                            with st.form(key=f"ed_{row['preset_id']}"):
                                updated_row = {"preset_id": row['preset_id'], "client_name": row['client_name'], "rule_name": row['rule_name']}
                                for t_col in st.session_state.target_columns:
                                    val = row[t_col] if t_col in row else ""
                                    updated_row[t_col] = st.text_input(f"{t_col}:", value=val)
                                if st.form_submit_button("Update"):
                                    presets_db.iloc[idx] = pd.Series(updated_row)
                                    conn_cloud.update(worksheet="presets", data=presets_db)
                                    st.rerun()

    # --- TAB 1: ACTIVE DASHBOARD ---
    with main_tab:
        # Step 1: Target Columns (unchanged)
        with st.expander("⚙️ Step 1: Configure Target Format"):
            pass 

        # Step 2: Upload & Map (Applying saved rules)
        st.header("📤 Step 2: Upload & Map")
        uploaded_files = st.file_uploader("Upload Files", type=["csv", "xlsx"], accept_multiple_files=True, key="main_up")
        
        if uploaded_files:
            try: rules_data = conn_cloud.read(worksheet="presets", ttl="0s")
            except: rules_data = pd.DataFrame()

            for i, file in enumerate(uploaded_files):
                with st.container(border=True):
                    st.subheader(f"📄 {file.name}")
                    
                    # Rule Selection
                    preset_options = ["Manual / Smart Match"]
                    if not rules_data.empty:
                        rules_data['full_label'] = rules_data['client_name'].astype(str) + " - " + rules_data['rule_name'].astype(str)
                        preset_options += rules_data['full_label'].tolist()
                    
                    selected_label = st.selectbox("Apply Saved Rule:", preset_options, key=f"rsel_{i}")
                    
                    df_source = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                    source_cols = [str(c) for c in df_source.columns]
                    
                    active_rule = None
                    if selected_label != "Manual / Smart Match":
                        match = rules_data[rules_data['full_label'] == selected_label]
                        if not match.empty: active_rule = match.iloc[0]

                    mapping_dict = {}
                    m_cols = st.columns(3)
                    for idx, t_col in enumerate(st.session_state.target_columns):
                        default_idx = 0
                        if active_rule is not None and t_col in active_rule and str(active_rule[t_col]) in source_cols:
                            default_idx = source_cols.index(str(active_rule[t_col])) + 1
                        
                        mapping_dict[t_col] = m_cols[idx % 3].selectbox(
                            f"Map {t_col}", [None] + source_cols, index=default_idx, key=f"main_map_{file.name}_{t_col}_{selected_label}"
                        )

                    if st.button(f"Confirm & Save {file.name}", key=f"msave_{i}"):
                        # Save logic...
                        pass

        # Step 3 logic...
