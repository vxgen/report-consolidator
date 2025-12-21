import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
import io

# --- Configuration & Database ---
DB_NAME = "consolidated_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS upload_registry 
                 (batch_id TEXT PRIMARY KEY, file_name TEXT, display_name TEXT, upload_time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS master_report 
                 (batch_id TEXT, upload_time TEXT)''')
    conn.commit()
    conn.close()

def sync_db_schema(df):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(master_report)")
    existing_cols = [info[1] for info in cursor.fetchall()]
    for col in df.columns:
        if col not in existing_cols:
            cursor.execute(f'ALTER TABLE master_report ADD COLUMN "{col}" TEXT')
    conn.commit()
    conn.close()

init_db()

st.set_page_config(page_title="Segmented Report Manager", layout="wide")
st.title("📂 Segmented Report Consolidator")

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
        if new_name: st.session_state.target_columns.append(new_name); st.rerun()

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

            if st.button(f"Process {d_name}", key=f"b_{file.name}"):
                valid_maps = {v: k for k, v in mapping_dict.items() if v is not None}
                if valid_maps:
                    proc_df = df_source[list(valid_maps.keys())].rename(columns=valid_maps)
                    batch_id = f"ID_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    proc_df['batch_id'], proc_df['upload_time'] = batch_id, now
                    sync_db_schema(proc_df)
                    conn = sqlite3.connect(DB_NAME)
                    proc_df.to_sql("master_report", conn, if_exists='append', index=False)
                    conn.execute("INSERT INTO upload_registry VALUES (?, ?, ?, ?)", (batch_id, file.name, d_name, now))
                    conn.commit(); conn.close()
                    st.success("Imported!"); st.rerun()

st.divider()

# --- STEP 3: SEGMENTED VIEW & SELECTIVE COMBINE ---
st.header("📋 Step 3: Manage Segments & Combine")
conn = sqlite3.connect(DB_NAME)
try:
    registry = pd.read_sql("SELECT * FROM upload_registry", conn)
    if not registry.empty:
        selected_batches = []
        
        st.subheader("Select Reports to Combine")
        # Grid for segments
        for _, row in registry.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([0.5, 4, 2])
                
                # 1. Selection Checkbox for Combining
                is_selected = c1.checkbox("", key=f"sel_{row['batch_id']}")
                if is_selected: selected_batches.append(row['batch_id'])
                
                # 2. Segment Info & Preview
                c2.write(f"**{row['display_name']}** ({row['file_name']})")
                c2.caption(f"Imported: {row['upload_time']}")
                
                # 3. Individual Download/Delete
                seg_df = pd.read_sql(f"SELECT * FROM master_report WHERE batch_id='{row['batch_id']}'", conn)
                # Filter to current target columns for download
                clean_seg = seg_df[[c for c in st.session_state.target_columns if c in seg_df.columns]]
                
                csv_data = clean_seg.to_csv(index=False).encode('utf-8')
                c3.download_button("📥 Download This Segment", data=csv_data, file_name=f"{row['display_name']}.csv", key=f"dl_{row['batch_id']}")
                
                if c3.button("🗑️ Delete", key=f"del_btn_{row['batch_id']}"):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM master_report WHERE batch_id=?", (row['batch_id'],))
                    cursor.execute("DELETE FROM upload_registry WHERE batch_id=?", (row['batch_id'],))
                    conn.commit(); st.rerun()

        st.divider()
        
        # --- COMBINE SECTION ---
        st.subheader("🔗 Combined Export")
        if selected_batches:
            st.info(f"Selected {len(selected_batches)} report(s) for consolidation.")
            if st.button("Generate Combined Report"):
                # Fetch only selected batches
                placeholders = ','.join(['?'] * len(selected_batches))
                combined_df = pd.read_sql(f"SELECT * FROM master_report WHERE batch_id IN ({placeholders})", conn, params=selected_batches)
                
                # Clean columns to current format
                final_cols = [c for c in st.session_state.target_columns if c in combined_df.columns]
                display_df = combined_df[final_cols]
                
                st.dataframe(display_df)
                csv_comb = display_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Combined Report", data=csv_comb, file_name="combined_report.csv")
        else:
            st.warning("Check the boxes next to the reports above to combine them.")

    else:
        st.info("No reports imported yet.")
except Exception as e:
    st.error(f"Error: {e}")

st.divider()

# --- STEP 4: GLOBAL CONTROLS ---
if st.button("🔥 HARD RESET (Clear Everything)"):
    conn.close()
    if os.path.exists(DB_NAME): os.remove(DB_NAME)
    st.rerun()

conn.close()


