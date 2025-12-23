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

    # --- TAB 2: MAPPING PRESETS ---
    with preset_tab:
        st.header("🗺️ Manage Mapping Presets")
        try:
            presets_db = conn_cloud.read(worksheet="presets", ttl="0s")
        except:
            presets_db = pd.DataFrame(columns=["preset_id", "client_name", "rule_name"] + st.session_state.target_columns)

        with st.expander("➕ Add New Mapping Rule"):
            sample_file = st.file_uploader("Upload sample to see headers:", type=["csv", "xlsx"], key="pre_up")
            sample_headers = []
            if sample_file:
                df_s = pd.read_csv(sample_file) if sample_file.name.endswith('.csv') else pd.read_excel(sample_file)
                sample_headers = [str(c) for c in df_s.columns]

            with st.form("add_preset_form"):
                p_client = st.text_input("Client Name")
                p_rule = st.text_input("Rule Category")
                new_mapping = {"preset_id": f"PR_{int(time.time())}", "client_name": p_client, "rule_name": p_rule}
                for t_col in st.session_state.target_columns:
                    if sample_headers:
                        new_mapping[t_col] = st.selectbox(f"Header for {t_col}", [None] + sample_headers)
                    else:
                        new_mapping[t_col] = st.text_input(f"Header for {t_col}")
                
                if st.form_submit_button("Save Rule"):
                    updated_presets = pd.concat([presets_db, pd.DataFrame([new_mapping])], ignore_index=True)
                    conn_cloud.update(worksheet="presets", data=updated_presets)
                    st.success("Rule Saved!")
                    st.rerun()

    # --- TAB 1: ACTIVE DASHBOARD ---
    with main_tab:
        with st.expander("⚙️ Step 1: Configure Target Format"):
            cols_to_remove = []
            for i, col in enumerate(st.session_state.target_columns):
                c1, c2 = st.columns([5,1])
                st.session_state.target_columns[i] = c1.text_input(f"Col {i+1}", value=col, key=f"t_{i}")
                if c2.button("🗑️", key=f"d_{i}"): cols_to_remove.append(col)
            if cols_to_remove:
                st.session_state.target_columns = [c for c in st.session_state.target_columns if c not in cols_to_remove]
                st.rerun()

        st.header("📤 Step 2: Upload & Map")
        uploaded_files = st.file_uploader("Upload Files", type=["csv", "xlsx"], accept_multiple_files=True)
        
        if uploaded_files:
            try: rules = conn_cloud.read(worksheet="presets", ttl="0s")
            except: rules = pd.DataFrame()

            for i, file in enumerate(uploaded_files):
                with st.container(border=True):
                    st.subheader(f"📄 {file.name}")
                    preset_opts = ["Manual"] + (rules['client_name'] + " - " + rules['rule_name']).tolist() if not rules.empty else ["Manual"]
                    sel_rule = st.selectbox("Apply Rule:", preset_opts, key=f"r_{i}")
                    
                    df_source = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                    source_cols = [str(c) for c in df_source.columns]
                    
                    mapping_dict = {}
                    active_rule = rules[rules['client_name'] + " - " + rules['rule_name'] == sel_rule].iloc[0] if sel_rule != "Manual" else None
                    
                    m_cols = st.columns(3)
                    for idx, t_col in enumerate(st.session_state.target_columns):
                        def_idx = 0
                        if active_rule is not None and t_col in active_rule and active_rule[t_col] in source_cols:
                            def_idx = source_cols.index(active_rule[t_col]) + 1
                        mapping_dict[t_col] = m_cols[idx%3].selectbox(f"Map {t_col}", [None]+source_cols, index=def_idx, key=f"m_{file.name}_{t_col}_{sel_rule}")

                    if st.button(f"Save {file.name}", key=f"s_{i}"):
                        v_maps = {v: k for k, v in mapping_dict.items() if v}
                        new_df = df_source[list(v_maps.keys())].rename(columns=v_maps)
                        new_df['batch_id'], new_df['upload_time'], new_df['file_display_name'] = f"B_{int(time.time())}", get_sydney_time(), file.name
                        master = conn_cloud.read(worksheet="Sheet1", ttl="0s")
                        conn_cloud.update(worksheet="Sheet1", data=pd.concat([master, new_df], ignore_index=True))
                        st.success("Uploaded!")
                        st.rerun()

        st.divider()
        st.header("📋 Step 3: Manage Cloud Segments")
        try:
            master_data = conn_cloud.read(worksheet="Sheet1", ttl="0s")
            if not master_data.empty:
                unique_batches = master_data[['batch_id', 'file_display_name', 'upload_time']].drop_duplicates()
                selected_ids = []
                for _, row in unique_batches.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([0.5, 4, 1])
                        if c1.checkbox("", key=f"cb_{row['batch_id']}"): selected_ids.append(row['batch_id'])
                        c2.write(f"**{row['file_display_name']}** ({row['upload_time']})")
                        if c3.button("🗑️", key=f"ds_{row['batch_id']}"):
                            conn_cloud.update(worksheet="Sheet1", data=master_data[master_data['batch_id'] != row['batch_id']])
                            st.rerun()

                # RESTORED STEP 4: CONSOLIDATION
                if selected_ids:
                    st.divider()
                    st.subheader("📊 Step 4: Consolidated Report")
                    combined = master_data[master_data['batch_id'].isin(selected_ids)]
                    st.dataframe(combined[st.session_state.target_columns], use_container_width=True)
                    
                    c_down, c_arch = st.columns(2)
                    c_down.download_button("📥 Download Combined CSV", combined.to_csv(index=False), "consolidated.csv")
                    
                    if c_arch.button("📁 Archive Selected Segments"):
                        archive_db = conn_cloud.read(worksheet="archive", ttl="0s")
                        conn_cloud.update(worksheet="archive", data=pd.concat([archive_db, combined], ignore_index=True))
                        conn_cloud.update(worksheet="Sheet1", data=master_data[~master_data['batch_id'].isin(selected_ids)])
                        st.success("Segments moved to Archive!")
                        st.rerun()
            else: st.info("No segments in cloud.")
        except: pass

    with archive_tab:
        st.header("📁 Historical Archive")
        try:
            arc = conn_cloud.read(worksheet="archive", ttl="0s")
            st.dataframe(arc, use_container_width=True) if not arc.empty else st.write("Archive is empty.")
        except: pass
