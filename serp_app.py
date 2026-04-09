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
/* Base */
html, body, [class*="css"] { font-family: system-ui, sans-serif; }
.stApp { background-color: #0a0f1e; color: #e8eaf0; }

/* Sidebar & main bg */
section[data-testid="stSidebar"] { background: #0d1426; }

/* Title */
h1 { color: #ffffff !important; font-weight: 800 !important; letter-spacing: -.02em !important; }

/* Labels */
label, .stTextInput label, .stSelectbox label, .stFileUploader label {
    color: #7a8fb0 !important; font-size: .78rem !important;
    font-weight: 700 !important; text-transform: uppercase; letter-spacing: .05em;
}

/* Inputs */
input[type="text"], input[type="password"] {
    background: #111827 !important; border: 1px solid #1e3a5f !important;
    color: #e8eaf0 !important; border-radius: 8px !important;
}
input:focus { border-color: #0080ff !important; box-shadow: 0 0 0 2px rgba(0,128,255,.15) !important; }

/* Select */
.stSelectbox > div > div {
    background: #111827 !important; border: 1px solid #1e3a5f !important;
    color: #e8eaf0 !important; border-radius: 8px !important;
}

/* File uploader */
[data-testid="stFileUploader"] {
    background: #111827 !important; border: 2px dashed #1e3a5f !important;
    border-radius: 10px !important;
}

/* Button */
.stButton > button {
    background: linear-gradient(135deg, #0057b8, #0080ff) !important;
    color: #fff !important; border: none !important;
    border-radius: 9px !important; font-weight: 700 !important;
    font-size: .95rem !important; padding: 10px 0 !important;
    width: 100% !important; transition: opacity .2s !important;
}
.stButton > button:hover { opacity: .88 !important; }

/* Download button */
.stDownloadButton > button {
    background: #0a2e1a !important; color: #4ade80 !important;
    border: 1px solid #166534 !important; border-radius: 9px !important;
    font-weight: 700 !important; width: 100% !important;
}

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid #1e3a5f !important; border-radius: 8px !important; }

/* Progress */
.stProgress > div > div { background: linear-gradient(90deg, #0057b8, #00aaff) !important; }

/* Info / warning */
.stAlert { border-radius: 8px !important; }

/* Company list */
.company-item {
    padding: 5px 12px; background: #111827; border-left: 3px solid #0057b8;
    border-radius: 4px; margin-bottom: 4px; font-size: .85rem; color: #a0b0cc;
}
.company-num { color: #1e3a5f; font-size: .75rem; margin-right: 8px; }
</style>
""", unsafe_allow_html=True)

# Logo + title
col1, col2 = st.columns([1, 6])
with col1:
    st.image("https://cdn.brandfetch.io/idVfYwCqBm/w/400/h/400/theme/dark/logo.png", width=48)
with col2:
    st.markdown("<h1 style='margin-top:4px'>SERP Research</h1>", unsafe_allow_html=True)

st.divider()

api_key = st.text_input("Serper API Key", type="password", placeholder="Enter your serper.dev API key")

uploaded_file = st.file_uploader("Upload CSV (must have a 'Key' column)", type="csv")

if uploaded_file:
    df_preview = pd.read_csv(uploaded_file)
    uploaded_file.seek(0)
    if "Key" in df_preview.columns:
        domains = df_preview["Key"].dropna().tolist()
        st.markdown(f"**{len(domains)} companies loaded**")
        items_html = "".join(
            f'<div class="company-item"><span class="company-num">{i}.</span>{d}</div>'
            for i, d in enumerate(domains[:50], 1)
        )
        if len(domains) > 50:
            items_html += f'<div class="company-item" style="color:#444">+{len(domains)-50} more</div>'
        st.markdown(items_html, unsafe_allow_html=True)
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
        if st.button("Run Lookup", disabled=run_disabled):
            domains = df["Key"].dropna().tolist()
            total = len(domains)
            results = [None] * total
            lock = threading.Lock()
            completed = threading.Value('i', 0)

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
                    resp.raise_for_status()
                    data = resp.json()
                    url = (data.get("organic") or [{}])[0].get("link", "")
                    results[idx] = {"Status": "found" if url else "not_found", "Key": domain, "SERP_Query": query, "URL": url}
                except requests.HTTPError as e:
                    results[idx] = {"Status": f"error_{e.response.status_code}", "Key": domain, "SERP_Query": query, "URL": ""}
                except Exception as e:
                    results[idx] = {"Status": "error", "Key": domain, "SERP_Query": query, "URL": str(e)}

                with lock:
                    completed.value += 1
                    pct = completed.value / total
                    progress_bar.progress(pct)
                    status_text.text(f"Processing {completed.value}/{total}: {domain}")

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

            st.dataframe(result_df, use_container_width=True)

            buf = io.StringIO()
            result_df.to_csv(buf, index=False)
            st.download_button("Download Result CSV", data=buf.getvalue(),
                               file_name="serp_results.csv", mime="text/csv")

elif uploaded_file and not api_key:
    st.warning("Please enter your Serper API key.")
elif api_key and not uploaded_file:
    st.info("Please upload a CSV file.")
