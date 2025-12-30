import streamlit as st  # <--- THE WEB FRAMEWORK
import requests
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# --- CONFIGURATION ---
import os

try:
    # 1. Try to get the token from Streamlit Cloud Secrets
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
except FileNotFoundError:
    # 2. If running locally, you can set it manually or show an error
    # You can temporarily uncomment the next line for local testing, BUT DON'T COMMIT IT:
    # GITHUB_TOKEN = "YOUR_REAL_TOKEN_HERE" 
    st.error("Secrets not found. Please configure .streamlit/secrets.toml or Streamlit Cloud Secrets.")
    st.stop()

# 3. Define HEADERS *after* we successfully have the token
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

# --- PAGE SETUP ---
st.set_page_config(page_title="GitHub Health Check", page_icon="🏥", layout="wide")

# --- SIDEBAR (INPUTS) ---
st.sidebar.title("🔍 Configuration")
st.sidebar.write("Enter the repository details below:")

owner_name = st.sidebar.text_input("Repo Owner", placeholder="Repo Owner")
repo_name = st.sidebar.text_input("Repo Name", placeholder="Repo Name")
searched_dev = st.sidebar.text_input("Compare Developer (Optional)", value="")

# <--- NEW ADDITION STARTS HERE --->
st.sidebar.divider()
view_mode = st.sidebar.radio("Chart View Mode:", ["Top 5 Developers", "Show All (Detailed)"])
# <--- NEW ADDITION ENDS HERE --->

btn_scan = st.sidebar.button("Run Health Check")

# --- THE LOGIC (REFACTORED FOR WEB) ---
def fetch_data(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=100"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        return None, f"Error: {response.status_code}"
    
    data = response.json()
    if not data:
        return None, "Repository is empty."
        
    # Parse
    commit_list = []
    for item in data:
        if item['commit']['author']:
            name = item['commit']['author']['name']
            date_str = item['commit']['author']['date']
            dt_obj = pd.to_datetime(date_str)
            commit_list.append({"author": name, "date": dt_obj})
            
    return pd.DataFrame(commit_list), None

def fetch_issues(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=closed&per_page=100"
    res = requests.get(url, headers=HEADERS)
    
    if res.status_code != 200: return 0, 0
    
    data = res.json()
    wait_times = []
    for item in data:
        if 'pull_request' in item: continue # Skip PRs
        created = pd.to_datetime(item['created_at'])
        closed = pd.to_datetime(item['closed_at'])
        diff = (closed - created).total_seconds() / 3600
        wait_times.append(diff)
        
    if not wait_times: return 0, 0
    return np.mean(wait_times), len(wait_times)

# --- MAIN APP UI ---
st.title(f"🏥 GitHub Health Dashboard")

if btn_scan:
    with st.spinner(f"Spying on {owner_name}/{repo_name}..."):
        df, error = fetch_data(owner_name, repo_name)
        
        if error:
            st.error(error)
        else:
            # 1. CALCULATIONS
            total_commits = len(df)
            last_commit_date = df.iloc[0]['date']
            today = pd.Timestamp.now(tz='UTC')
            days_inactive = (today - last_commit_date).days
            
            author_counts = df['author'].value_counts()
            lead_name = author_counts.index[0]
            lead_count = author_counts.iloc[0]
            lead_dominance = (lead_count / total_commits) * 100
            
            # Weekend Logic
            df['day_of_week'] = df['date'].dt.dayofweek
            weekend_percent = (len(df[df['day_of_week'] >= 5]) / total_commits) * 100
            
            # Issues Logic
            avg_hours, issue_count = fetch_issues(owner_name, repo_name)
            avg_days = avg_hours / 24

            # ------------------------------------------------
            # UI SECTION 1: KEY METRICS (Big Numbers)
            # ------------------------------------------------
            st.markdown("### 📊 Key Vitals")
            col1, col2, col3, col4 = st.columns(4)
            
            # Status
            status_label = "ALIVE" if days_inactive < 30 else "ZOMBIE"
            status_color = "normal" if days_inactive < 30 else "off"
            col1.metric("Activity Status", status_label, f"{days_inactive} days inactive", delta_color=status_color)
            
            # Risk
            risk_label = "HIGH" if lead_dominance > 50 else "LOW"
            col2.metric("Bus Factor Risk", risk_label, f"{lead_dominance:.1f}% Dominance", delta_color="inverse")
            
            # Burnout
            burnout_label = "High" if weekend_percent > 30 else "Healthy"
            col3.metric("Weekend Work", f"{weekend_percent:.1f}%", burnout_label, delta_color="inverse")
            
            # Support
            col4.metric("Avg Issue Fix Time", f"{avg_days:.1f} Days", f"{issue_count} analyzed")

            st.divider()

            # ------------------------------------------------
            # UI SECTION 2: VISUALIZATION
            # ------------------------------------------------
            st.markdown("### 👁️ Deep Dive Visualization")
            
            # Create two separate columns in Streamlit
            col_viz1, col_viz2 = st.columns(2)

           # --- LEFT COLUMN: BAR CHART (LEADERBOARD) ---
            with col_viz1:
                fig1, ax1 = plt.subplots(figsize=(6, 8))
                
                # Data Prep
                if view_mode == "Top 5 (Clean)":
                    data_slice = author_counts.head(5)
                    # We reverse it so the #1 author is at the TOP of the chart
                    data_slice = data_slice.iloc
                    labels = list(data_slice.index)
                    values = list(data_slice.values)
                else:
                    # Show All (Reversed)
                    data_slice = author_counts
                    labels = list(data_slice.index)
                    values = list(data_slice.values)

                # Plotting Horizontal Bars
                bars = ax1.bar(labels, values, color="#4CAF50") # Google Green color
                
                # Formatting
                ax1.set_title(f"Commit Leaderboard ({view_mode})")
                ax1.set_xlabel("Number of Commits")

                # --- THE FIX: Rotate 90 degrees ---
                ax1.set_xticks(range(len(labels)))
                # rotation=90 makes them vertical. ha='center' aligns them perfectly under the tick marks.
                ax1.set_xticklabels(labels, rotation=90, ha='center', fontsize=9)
                
                # Add the numbers inside the bars (Data Labels)
                for bar in bars:
                    height = bar.get_height()
                    ax1.text(
                        bar.get_x() + bar.get_width()/2, # X center of bar
                        height,                          # Y (top of bar)
                        f'{int(height)}',                # The Label
                        ha='center', va='bottom',        # Alignment
                        fontweight='bold', fontsize=9
                    )
                
                # Remove ugly borders
                ax1.spines['top'].set_visible(False)
                ax1.spines['right'].set_visible(False)
                plt.tight_layout()
                st.pyplot(fig1)

            # --- RIGHT COLUMN: HEATMAP ---
            with col_viz2:
                # Create a new, dedicated figure for the heatmap
                fig2, ax2 = plt.subplots(figsize=(8, 6))
                
                # Data prep
                df['hour'] = df['date'].dt.hour
                df['day_name'] = df['date'].dt.day_name()
                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                df['day_index'] = pd.Categorical(df['day_name'], categories=day_order, ordered=True).codes
                heatmap_data = df.groupby(['day_index', 'hour']).size().reset_index(name='count')
                
                # Plotting
                sc = ax2.scatter(
                    heatmap_data['hour'], 
                    heatmap_data['day_index'], 
                    s=heatmap_data['count']*50, 
                    c=heatmap_data['count'], 
                    cmap='Reds', 
                    alpha=0.7, 
                    edgecolors='grey'
                )
                ax2.set_title("Work Culture Map")
                ax2.set_yticks(range(7))
                ax2.set_yticklabels(day_order)
                ax2.set_xticks(range(0, 24, 2))
                ax2.grid(True, linestyle='--', alpha=0.5)
                # Add a colorbar for context
                plt.colorbar(sc, ax=ax2, label="Commits")
                
                # Display this figure in the right column
                st.pyplot(fig2)

            # ------------------------------------------------
            # UI SECTION 3: INSIGHTS
            # ------------------------------------------------
            st.divider()
            col_insight_1, col_insight_2 = st.columns(2)
            
            with col_insight_1:
                st.subheader("🧠 Behavior Analysis")
                if weekend_percent > 30:
                    st.warning("🚜 **The Weekend Warrior:** High weekend activity detected.")
                elif weekend_percent < 5:
                    st.success("👔 **The 9-to-5 Pro:** Professional weekday schedule.")
                else:
                    st.info("⚖️ **Balanced Schedule:** Standard mix of work.")

            with col_insight_2:
                st.subheader("⚔️ Team Battle")
                if searched_dev:
                    if searched_dev in author_counts:
                        user_commits = author_counts[searched_dev]
                        gap = lead_count - user_commits
                        st.info(f"**{searched_dev}** has {user_commits} commits.")
                        if gap > 0:
                            st.write(f"📉 Trailing Lead ({lead_name}) by **{gap}** commits.")
                        else:
                            st.write("👑 You are the Lead!")
                    else:
                        st.error(f"Developer '{searched_dev}' not found in recent history.")
                else:
                    st.write("Enter a name in the sidebar to compare vs the Lead Dev.")