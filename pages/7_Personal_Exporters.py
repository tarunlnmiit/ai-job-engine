import streamlit as st
import subprocess
import os
import json
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Personal Exporters", page_icon="📊", layout="wide")

# Custom CSS for glassmorphism
st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        color: #e94560;
    }
    .main-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 20px;
    }
    .stButton>button {
        background: linear-gradient(45deg, #e94560, #0f3460);
        color: white;
        border: none;
        padding: 10px 25px;
        border-radius: 8px;
        font-weight: bold;
        transition: 0.3s;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(233, 69, 96, 0.4);
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Personal Data Exporters")
st.markdown("Download your data from Twitter/X and ChatGPT directly into structured JSON.")

col1, col2 = st.columns(2)

import sys

with col1:
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    st.header("🐦 Twitter/X Scraper")
    twitter_user = st.text_input("Twitter Username", value="mistakenlyhuman", placeholder="e.g. elonmusk")
    tweet_limit = st.slider("Max Tweets to Scrape (set high for all)", 10, 5000, 1000)
    
    if st.button("Start Twitter Scraping"):
        if not twitter_user:
            st.error("Please enter a username.")
        else:
            status_container = st.empty()
            log_container = st.empty()
            with st.spinner(f"Scraping tweets for @{twitter_user}..."):
                script_path = os.path.join(os.getcwd(), "scratch", "twitter_scraper.py")
                cmd = [sys.executable, script_path, twitter_user, str(tweet_limit)]
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                
                logs = []
                for line in process.stdout:
                    line = line.strip()
                    if line.startswith("STATUS:"):
                        status_container.info(line.replace("STATUS:", ""))
                    elif line.startswith("PROGRESS:"):
                        status_container.warning(line.replace("PROGRESS:", ""))
                    
                    logs.append(line)
                    log_container.code("\n".join(logs[-10:])) # Show last 10 lines
                
                process.wait()
                
                if process.returncode == 0:
                    st.success("Scraping completed!")
                    json_file = os.path.join("data", f"twitter_{twitter_user}_tweets.json")
                    if os.path.exists(json_file):
                        with open(json_file, "r") as f:
                            data = json.load(f)
                            df = pd.json_normalize(data)
                            st.dataframe(df)
                            
                            with open(json_file, "rb") as f:
                                st.download_button(
                                    label="Download Twitter JSON",
                                    data=f,
                                    file_name=os.path.basename(json_file),
                                    mime="application/json"
                                )
                else:
                    st.error("Scraping failed.")
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    st.header("💬 ChatGPT History Scraper")
    st.markdown("Export all your conversations into a single JSON file.")
    
    if st.button("Start ChatGPT Export"):
        status_container_chat = st.empty()
        log_container_chat = st.empty()
        with st.spinner("Initializing ChatGPT scraper..."):
            script_path = os.path.join(os.getcwd(), "scratch", "chatgpt_scraper.py")
            cmd = [sys.executable, script_path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            
            logs = []
            for line in process.stdout:
                line = line.strip()
                if line.startswith("STATUS:"):
                    status_container_chat.info(line.replace("STATUS:", ""))
                elif line.startswith("PROGRESS:"):
                    status_container_chat.warning(line.replace("PROGRESS:", ""))
                
                logs.append(line)
                log_container_chat.code("\n".join(logs[-10:]))
            
            process.wait()
            
            if process.returncode == 0:
                st.success("Export completed!")
                json_file = os.path.join("data", "chatgpt_history_export.json")
                if os.path.exists(json_file):
                    with open(json_file, "r") as f:
                        data = json.load(f)
                        st.info(f"Found {len(data)} total conversations (including existing).")
                        
                        with open(json_file, "rb") as f:
                            st.download_button(
                                label="Download ChatGPT JSON",
                                data=f,
                                file_name=f"chatgpt_export_{datetime.now().strftime('%Y%m%d')}.json",
                                mime="application/json"
                            )
            else:
                st.error("Export failed.")
    st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("### 🛠 How it works")
st.markdown("""
1. **Login Manually**: When you click 'Start', a browser window will open. You **must** log in to the respective platform.
2. **Persistence**: The scrapers use a local 'user data directory' to store your session, so you might not need to log in every time.
3. **Wait for Completion**: The scraper will scroll and collect data. Keep the browser window open until it closes automatically.
""")
