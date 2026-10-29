import io
import streamlit as st
import pandas as pd
from rapidfuzz import fuzz

# Import your scraper function
try:
    from openrice_daily import main as run_openrice_scraper
except ImportError:
    run_openrice_scraper = None

st.set_page_config(page_title="OpenRice Data Matching Portal", layout="wide")
st.title("Data Matching & Reconciliation Portal")

# Initialize Session State variables
if "uploaded_df" not in st.session_state:
    st.session_state.uploaded_df = None
if "scraped_df" not in st.session_state:
    st.session_state.scraped_df = None
if "results_ready" not in st.session_state:
    st.session_state.results_ready = False

# -------------------------------------------------------------
# STEP 1: Download report from a link (stored in a button)
# -------------------------------------------------------------
st.subheader("Step 1: Download Internal Report")
REPORT_URL = "https://deliveryhero.lightning.force.com/lightning/r/Report/00ObO000008F6tJUAS/view?queryScope=userFolders"  # Replace with your actual URL

col1, col2 = st.columns([1, 3])
with col1:
    # Opens the URL directly in a new tab
    st.link_button("Download Source Report", url=REPORT_URL, help="Opens the download link in a new browser tab")
with col2:
    st.caption("Click to download the latest account CSV report from sf.")

st.divider()

# -------------------------------------------------------------
# STEP 2: Upload the report for later use
# -------------------------------------------------------------
st.subheader("Step 2: Upload Account Report")
uploaded_file = st.file_uploader("Select the downloaded CSV report", type=["csv"])

if st.button("Upload All Account Data", type="primary"):
    if uploaded_file is not None:
        try:
            st.session_state.uploaded_df = pd.read_csv(uploaded_file)
            st.success(f"Successfully loaded {len(st.session_state.uploaded_df)} account records.")
        except Exception as e:
            st.error(f"Failed to read CSV: {e}")
    else:
        st.warning("Please choose a CSV file first before clicking upload.")

if st.session_state.uploaded_df is not None:
    with st.expander("Preview Uploaded Accounts"):
        st.dataframe(st.session_state.uploaded_df.head())

st.divider()

# -------------------------------------------------------------
# STEP 3: Run daily OpenRice scraping script
# -------------------------------------------------------------
st.subheader("Step 3: Run Daily OpenRice Scraping")

if st.button("Run OpenRice Scraper"):
    if run_openrice_scraper is None:
        st.error("`run_openrice_scraper` function not found in `openrice_daily.py`.")
    else:
        with st.spinner("Scraping Openrice... This may take a few moments."):
            try:
                st.session_state.scraped_df = run_openrice_scraper()
                st.success(f"Scraping complete. Retrieved {len(st.session_state.scraped_df)} records.")
            except Exception as e:
                st.error(f"Scraper encountered an error: {e}")

if st.session_state.scraped_df is not None:
    with st.expander("Preview Scraped Openrice Data"):
        st.dataframe(st.session_state.scraped_df.head())

st.divider()

# -------------------------------------------------------------
# STEP 4: Similarity check (Name & Address)
# -------------------------------------------------------------
st.subheader("Step 4: Run Similarity Check")

if st.session_state.uploaded_df is not None and st.session_state.scraped_df is not None:
    # Column mapping controls
    col_up_name, col_up_addr = st.columns(2)
    with col_up_name:
        name_up_col = st.selectbox("Uploaded File: Name Column", st.session_state.uploaded_df.columns)
    with col_up_addr:
        addr_up_col = st.selectbox("Uploaded File: Address Column", st.session_state.uploaded_df.columns)

    col_sc_name, col_sc_addr = st.columns(2)
    with col_sc_name:
        name_sc_col = st.selectbox("Scraped Data: Name Column", st.session_state.scraped_df.columns)
    with col_sc_addr:
        addr_sc_col = st.selectbox("Scraped Data: Address Column", st.session_state.scraped_df.columns)

    if st.button("Compute Similarities"):
        with st.spinner("Calculating similarity scores across records..."):
            matched_records = []
            uploaded_data = st.session_state.uploaded_df.to_dict("records")
            scraped_data = st.session_state.scraped_df.to_dict("records")

            for up_row in uploaded_data:
                up_name = str(up_row.get(name_up_col, "")).strip()
                up_addr = str(up_row.get(addr_up_col, "")).strip()

                best_match = None
                best_combined_score = -1.0

                for sc_row in scraped_data:
                    sc_name = str(sc_row.get(name_sc_col, "")).strip()
                    sc_addr = str(sc_row.get(addr_sc_col, "")).strip()

                    # Token sort ratio handles variations in word order
                    name_sim = fuzz.token_sort_ratio(up_name.lower(), sc_name.lower())
                    addr_sim = fuzz.token_set_ratio(up_addr.lower(), sc_addr.lower())

                    # Weighted score: 60% name, 40% address (adjust weight as preferred)
                    combined_score = round(0.6 * name_sim + 0.4 * addr_sim, 2)

                    if combined_score > best_combined_score:
                        best_combined_score = combined_score
                        best_match = {
                            "Uploaded_Name": up_name,
                            "Uploaded_Address": up_addr,
                            "Scraped_Name": sc_name,
                            "Scraped_Address": sc_addr,
                            "Name_Similarity_%": round(name_sim, 2),
                            "Address_Similarity_%": round(addr_sim, 2),
                            "Overall_Similarity_%": combined_score
                        }

                if best_match:
                    matched_records.append(best_match)

            st.session_state.master_df = pd.DataFrame(matched_records)
            st.session_state.results_ready = True
            st.success("Similarity check completed.")
else:
    st.info("Complete Steps 2 and 3 above to proceed with the similarity check.")

# -------------------------------------------------------------
# STEP 5: Multi-sheet Export (Excel)
# -------------------------------------------------------------
if st.session_state.results_ready:
    st.divider()
    st.subheader("Step 5: Review & Download Results")

    master_df = st.session_state.master_df
    high_sim_df = master_df[master_df["Overall_Similarity_%"] >= 90.0]
    low_sim_df = master_df[master_df["Overall_Similarity_%"] < 90.0]

    # Display tab previews in UI
    tab1, tab2, tab3 = st.tabs([
        f"Master (All {len(master_df)})",
        f"Similarity >= 90% ({len(high_sim_df)})",
        f"Similarity < 90% ({len(low_sim_df)})"
    ])

    with tab1:
        st.dataframe(master_df)
    with tab2:
        st.dataframe(high_sim_df)
    with tab3:
        st.dataframe(low_sim_df)

    # Build 3-sheet Excel workbook in-memory
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        master_df.to_excel(writer, sheet_name="Master", index=False)
        high_sim_df.to_excel(writer, sheet_name="Similarity_GTE_90", index=False)
        low_sim_df.to_excel(writer, sheet_name="Similarity_LT_90", index=False)
    excel_buffer.seek(0)

    st.download_button(
        label="Download Matched Results (.xlsx)",
        data=excel_buffer,
        file_name="matched_openrice_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
