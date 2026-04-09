import streamlit as st
import pandas as pd
import requests
import io
import concurrent.futures
import threading

PLATFORMS = {
    "ZoomInfo":   "site:zoominfo.com/c",
    "Crunchbase": "site:crunchbase.com/organization",
}

WORKERS = 10

st.set_page_config(page_title="SERP Research", page_icon="🔍", layout="centered")

st.markdown("""
<style>
h1 { font-weight: 800 !important; }
h1 { color: #ffffff !important; }
h1 span { color: #0080ff; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1>SERP <span>Research</span></h1>", unsafe_allow_html=True)
st.divider()

api_key = st.text_input("Serper API Key", type="password", placeholder="Enter your serper.dev API key")

uploaded_file = st.file_uploader("Upload CSV (must have a 'Key' column)", type="csv")

if uploaded_file:
    df_preview = pd.read_csv(uploaded_file)
    uploaded_file.seek(0)
    if "Key" in df_preview.columns:
        domains = df_preview["Key"].dropna().tolist()
        st.caption(f"{len(domains)} companies loaded")
        st.dataframe(
            pd.DataFrame({"#": range(1, len(domains)+1), "Domain": domains}),
            use_container_width=True, hide_index=True,
            column_config={"#": st.column_config.NumberColumn(width="small"), "Domain": st.column_config.TextColumn(width="large")}
        )
    else:
        st.error("CSV must contain a 'Key' column.")

st.divider()

platform = st.selectbox("Platform", list(PLATFORMS.keys()) + ["Custom..."])
custom_prefix = None
if platform == "Custom...":
    custom_prefix = st.text_input("Custom platform prefix", placeholder="site:example.com/path",
                                   help="e.g. site:apollo.io/companies")

active_prefix = PLATFORMS.get(platform) if platform != "Custom..." else (custom_prefix or "").strip()

st.divider()

if uploaded_file and api_key:
    uploaded_file.seek(0)
    df = pd.read_csv(uploaded_file)

    if "Key" not in df.columns:
        st.error("CSV must contain a 'Key' column.")
    else:
        run_disabled = platform == "Custom..." and not active_prefix
        if st.button("Run Lookup", disabled=run_disabled, use_container_width=True):
            domains = df["Key"].dropna().tolist()
            total = len(domains)
            results = [None] * total
            lock = threading.Lock()
            completed = [0]

            progress_bar = st.progress(0)
            status_text = st.empty()

            def lookup(idx, domain):
                query = f'{active_prefix} "{domain}"'
                try:
                    resp = requests.post(
                        "https://google.serper.dev/search",
                        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                        json={"q": query, "location": "United States", "autocorrect": False},
                        timeout=15
                    )
                    data = resp.json()
                    if not resp.ok:
                        message = data.get("message", "Unknown error")
                        status_label = f"{resp.status_code} — {message}"
                        results[idx] = {"Status": status_label, "Key": domain, "SERP_Query": query, "URL": ""}
                    else:
                        url = (data.get("organic") or [{}])[0].get("link", "")
                        results[idx] = {"Status": "found" if url else "not_found", "Key": domain, "SERP_Query": query, "URL": url}
                except Exception as e:
                    results[idx] = {"Status": str(e), "Key": domain, "SERP_Query": query, "URL": ""}

                with lock:
                    completed[0] += 1
                    progress_bar.progress(completed[0] / total)
                    status_text.text(f"Processing {completed[0]}/{total}: {domain}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
                ex.map(lambda x: lookup(*x), enumerate(domains))

            status_text.text(f"Done — {total} rows processed.")
            result_df = pd.DataFrame(results)

            found = (result_df["Status"] == "found").sum()
            not_found = (result_df["Status"] == "not_found").sum()
            errors = total - found - not_found

            c1, c2, c3 = st.columns(3)
            c1.metric("Found", found)
            c2.metric("Not found", not_found)
            c3.metric("Errors", errors)

            st.dataframe(result_df, use_container_width=True,
                         height=min(500, 60 + len(result_df) * 35))

            buf = io.StringIO()
            result_df.to_csv(buf, index=False)
            st.download_button("Download Result CSV", data=buf.getvalue(),
                               file_name="serp_results.csv", mime="text/csv",
                               use_container_width=True)

elif uploaded_file and not api_key:
    st.warning("Please enter your Serper API key.")
elif api_key and not uploaded_file:
    st.info("Please upload a CSV file.")
