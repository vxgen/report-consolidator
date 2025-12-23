import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import time

# --- 0. GLOBAL CONFIGURATION ---
USER_SHEET_URL = "https://docs.google.com/spreadsheets/d/1KG8qWTYLa6GEWByYIg2vz3bHrGdW3gv?gid=522749285#gid=522749285"

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
        # Sidebar UI - Restored
        with st.sidebar:
            st.title("👤 User Profile")
            st.write(f"Logged in as: **{st.session_state.get('current_user', 'Unknown')}**")
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
                else: st.error("Access Denied or Pending Approval.")
            except: st.error("Connection error with Cloud.")
    return False

if check_password():
    conn_cloud = st.connection("gsheets", type=GSheetsConnection)
    
    if 'target_columns' not in st.session_state:
        st.session_state.target_columns = ["Category", "SKU", "Product Name", "Product Description", "Stock on Hand", "Sold QTY"]
    
    st.title("☁️ Cloud Inventory Consolidator")
    main_tab, preset_tab, archive_tab = st.tabs(["🚀 Active Dashboard", "🗺️ Mapping Presets", "📁 Historical Archive"])

    # --- TAB 2: MAPPING PRESETS ---
    with preset_tab:
        st.header("🗺️ Manage Mapping Presets")
        try:
            presets_db = conn_cloud.read(worksheet="presets", ttl="0s")
        except:
            presets_db = pd.DataFrame(columns=["preset_id", "client_name", "rule_name"] + st.session_state.target_columns)

        with st.expander("➕ Add New Mapping Rule"):
            with st.form("add_preset_form"):
                p_client = st.text_input("Client Name")
                p_rule = st.text_input("Rule/Report Category")
                new_mapping = {"preset_id": f"PR_{int(time.time())}", "client_name": p_client, "rule_name": p_rule}
                for t_col in st.session_state.target_columns:
                    new_mapping[t_col] = st.text_input(f"CSV Header for '{t_col}':")
                
                if st.form_submit_button("Save Rule"):
                    if p_client and p_rule:
                        updated_presets = pd.concat([presets_db, pd.DataFrame([new_mapping])], ignore_index=True)
                        conn_cloud.update(worksheet="presets", data=updated_presets)
                        st.success("Rule Saved!")
                        st.rerun()

        st.divider()
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

    # --- TAB 1: ACTIVE DASHBOARD ---
    with main_tab:
        with st.expander("⚙️ Step 1: Configure Target Format"):
            # Target Column configuration logic remains here...
            pass

        st.header("📤 Step 2: Upload & Map")
        uploaded_files = st.file_uploader("Upload Files", type=["csv", "xlsx"], accept_multiple_files=True)
        
        if uploaded_files:
            try: rules = conn_cloud.read(worksheet="presets", ttl="5s")
            except: rules = pd.DataFrame()

            for i, file in enumerate(uploaded_files):
                with st.container(border=True):
                    st.subheader(f"📄 {file.name}")
                    
                    # Fix: Robust Preset selection strings
                    preset_options = ["Manual / Smart Match"]
                    if not rules.empty:
                        # Create unique strings for selection
                        rules['display_label'] = rules['client_name'].astype(str) + " - " + rules['rule_name'].astype(str)
                        preset_options += rules['display_label'].tolist()
                    
                    sel_rule_label = st.selectbox("Apply Saved Rule:", preset_options, key=f"rs_{i}")
                    
                    df_source = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                    source_cols = df_source.columns.tolist()
                    
                    mapping_dict = {}
                    m_cols = st.columns(3)
                    
                    # Fix: Robust Preset lookup
                    active_rule = None
                    if sel_rule_label != "Manual / Smart Match":
                        match = rules[rules['display_label'] == sel_rule_label]
                        if not match.empty:
                            active_rule = match.iloc[0]

                    for idx, t_col in enumerate(st.session_state.target_columns):
                        default_idx = 0
                        # 1. Check Preset
                        if active_rule is not None and t_col in active_rule and active_rule[t_col]:
                            preset_val = str(active_rule[t_col]).strip()
                            if preset_val in source_cols:
                                default_idx = source_cols.index(preset_val) + 1
                        
                        # 2. Smart Match Fallback
                        if default_idx == 0:
                            for s_col in source_cols:
                                if t_col.lower() in str(s_col).lower():
                                    default_idx = source_cols.index(s_col) + 1
                                    break
                        
                        mapping_dict[t_col] = m_cols[idx % 3].selectbox(
                            f"Map {t_col}", 
                            [None] + source_cols, 
                            index=default_idx, 
                            key=f"m_{file.name}_{t_col}_{sel_rule_label}" # Key includes rule for refresh
                        )

                    if st.button(f"Confirm & Save {file.name}", key=f"b_{file.name}"):
                        # Processing and Saving logic...
                        pass

        # Step 3 logic...
        st.header("📋 Step 3: Manage Cloud Segments")
