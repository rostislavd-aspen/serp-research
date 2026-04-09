import streamlit as st
import pandas as pd
import requests
import time
import io

PLATFORMS = {
    "ZoomInfo":   "site:zoominfo.com/c",
    "Crunchbase": "site:crunchbase.com/organization",
}

st.set_page_config(page_title="SERP Research", page_icon="🔍", layout="centered")

st.markdown("""
    <style>
    body, .stApp { background: #0d0d0d; color: #e8e8e8; }
    </style>
""", unsafe_allow_html=True)

st.title("SERP Research")

api_key = st.text_input("Serper API Key", type="password", placeholder="Enter your serper.dev API key")

uploaded_file = st.file_uploader("Upload CSV (must have a 'Key' column)", type="csv")

if uploaded_file:
    df_preview = pd.read_csv(uploaded_file)
    uploaded_file.seek(0)
    if "Key" in df_preview.columns:
        st.markdown("**Companies loaded:**")
        for i, val in enumerate(df_preview["Key"].dropna().tolist(), 1):
            st.markdown(f"{i}. {val}")
    else:
        st.error("CSV must contain a 'Key' column.")

platform = st.selectbox("Platform", list(PLATFORMS.keys()) + ["Custom..."])

custom_prefix = None
if platform == "Custom...":
    custom_prefix = st.text_input(
        "Custom platform prefix",
        placeholder="site:example.com/path",
        help="e.g. site:apollo.io/companies"
    )

active_prefix = PLATFORMS.get(platform) if platform != "Custom..." else (custom_prefix or "").strip()

if uploaded_file and api_key:
    uploaded_file.seek(0)
    df = pd.read_csv(uploaded_file)

    if "Key" not in df.columns:
        st.error("CSV must contain a 'Key' column.")
    else:
        run_disabled = platform == "Custom..." and not active_prefix
        if st.button("Run Lookup", disabled=run_disabled):
            results = []
            progress = st.progress(0)
            status = st.empty()
            total = len(df)

            for i, row in df.iterrows():
                domain = str(row["Key"]).strip()
                query = f'{active_prefix} "{domain}"'
                status.text(f"Processing {i+1}/{total}: {domain}")

                try:
                    resp = requests.post(
                        "https://google.serper.dev/search",
                        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                        json={"q": query, "location": "United States", "autocorrect": False},
                        timeout=15
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    url = (data.get("organic") or [{}])[0].get("link", "")
                    results.append({"Status": "found" if url else "not_found", "Key": domain, "SERP_Query": query, "URL": url})
                except requests.HTTPError as e:
                    results.append({"Status": f"error_{e.response.status_code}", "Key": domain, "SERP_Query": query, "URL": ""})
                except Exception as e:
                    results.append({"Status": "error", "Key": domain, "SERP_Query": query, "URL": str(e)})

                progress.progress((i + 1) / total)
                time.sleep(0.3)

            status.text(f"Done — {len(results)} rows processed.")
            result_df = pd.DataFrame(results)
            st.dataframe(result_df)

            buf = io.StringIO()
            result_df.to_csv(buf, index=False)
            st.download_button("Download Result CSV", data=buf.getvalue(), file_name="serp_results.csv", mime="text/csv")

elif uploaded_file and not api_key:
    st.warning("Please enter your Serper API key.")
elif api_key and not uploaded_file:
    st.info("Please upload a CSV file.")