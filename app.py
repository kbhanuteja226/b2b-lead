import streamlit as st
import requests
import pandas as pd
import re
import os
import io
from pandas import ExcelWriter

# MUST be the first Streamlit call
st.set_page_config(page_title="B2B Lead Generator", layout="centered")

# --- CONFIG ---
SERPAPI_KEY = st.secrets.get("SERPAPI_KEY", os.getenv("SERPAPI_KEY", ""))

EMAIL_REGEX = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
PHONE_REGEX = r"(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?:\s*x\d+)?"

# Extraction helpers
def extract_email_from_text(text):
    emails = re.findall(EMAIL_REGEX, text)
    return emails[0] if emails else ""

def extract_phone_from_text(text):
    phones = re.findall(PHONE_REGEX, text)
    return phones[0] if phones else ""

def fetch_emails_and_phone_from_url(url):
    if "linkedin.com" in url:
        return ("", "")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, timeout=5, headers=headers)
        response.raise_for_status()
        if 'text/html' not in response.headers.get('Content-Type', ''):
            return ("", "")
        return extract_email_from_text(response.text), extract_phone_from_text(response.text)
    except:
        return ("", "")

def extract_name(title):
    if not title:
        return ""
    match = re.search(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})", title)
    return match.group(1) if match else ""

def clean_role(text):
    if not isinstance(text, str):
        return ""
    role_keywords = [
        r"\b(?:sr\.|senior\s)?manager\b", r"\b(?:vp|vice president)\b", r"\bexecutive\b",
        r"\bspecialist\b", r"\brecruiter\b", r"\bhead\b", r"\blead\b", r"\bofficer\b",
        r"\banalyst\b", r"\bdirector\b", r"\bcoordinator\b", r"\bconsultant\b",
        r"\brcm\b", r"\bengineer\b", r"\bdeveloper\b", r"\b(?:hr|human resources)\b",
        r"\bassociate\b", r"\bassistant\b"
    ]
    for pattern in role_keywords:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0).title()
    return ""

def clean_company(text):
    if not isinstance(text, str):
        return ""
    match = re.search(r"at\s+([^\-]+(?:Pvt|Private|Solutions|Technologies|Services|Inc|Ltd|LLP|Consulting|Systems|Enterprises|Group)\b.*)", text, re.I)
    return match.group(1).strip() if match else ""

def extract_domain_from_url(url):
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else ""

def guess_email(name, domain):
    if not name or not domain:
        return ""
    parts = name.lower().split()
    if not parts:
        return ""
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    return f"{first}.{last}@{domain}" if first and last else f"{first}@{domain}"

# Lead collection
def get_leads_from_serpapi(query, num_results=10):
    if not SERPAPI_KEY:
        st.error("SerpAPI key not found.")
        st.stop()
    url = "https://serpapi.com/search.json"
    params = {"q": query, "engine": "google", "num": num_results, "api_key": SERPAPI_KEY}
    response = requests.get(url, params=params)
    results = response.json()

    leads = []
    for result in results.get("organic_results", []):
        title = result.get("title", "")
        link = result.get("link", "")
        snippet = result.get("snippet", "")
        name = extract_name(title)
        role = clean_role(title)
        company = clean_company(title)
        email_snippet = extract_email_from_text(snippet)
        phone_snippet = extract_phone_from_text(snippet)
        email_page, phone_page = ("", "")
        if not email_snippet and not phone_snippet:
            email_page, phone_page = fetch_emails_and_phone_from_url(link)
        domain = extract_domain_from_url(link)
        guessed_email = guess_email(name, domain)
        final_email = email_snippet or email_page or guessed_email
        phone = phone_snippet or phone_page
        if "linkedin.com" in final_email.lower():
            final_email = ""
        leads.append({
            "Name": name,
            "Role": role,
            "Company": company,
            "LinkedIn URL": link,
            "Email": final_email,
            "Phone": phone,
            "Guessed Email": guessed_email,
            "Raw Title": title
        })
    return leads

# UI
st.title("Prompt-Based B2B Lead Generator")
st.markdown("Enter a natural prompt like: *'Get leads for vendor onboarding at MNCs for SURG'*")

prompt = st.text_input("Enter your prompt", value=" ")

if st.button("Generate Leads"):
    with st.spinner("🔍 Searching the web..."):
        if "site:linkedin.com/in/" not in prompt.lower():
            prompt += " site:linkedin.com/in/"
        leads = get_leads_from_serpapi(prompt)
        df = pd.DataFrame(leads)

        if not df.empty:
            st.success(f"✅ {len(df)} leads found.")
            st.markdown(f"**Companies found:** {df['Company'].nunique()}")
            st.markdown(f"**Unique names:** {df['Name'].nunique()}")

            # Clickable LinkedIn link
            df["LinkedIn"] = df["LinkedIn URL"].apply(lambda x: f"[View Profile]({x})" if pd.notna(x) else "")


            # Display table
            st.markdown("### 🧑‍💼 Leads List (Clickable LinkedIn Links)")

            for index, row in df.iterrows():
                st.markdown(
                    f"""
                    <div style="border:1px solid #e6e6e6; padding:15px; border-radius:10px; margin-bottom:10px;">
                    <strong>Name:</strong> {row['Name']}<br>
                    <strong>Role:</strong> {row['Role']}<br>
                    <strong>Company:</strong> {row['Company']}<br>
                    <strong>LinkedIn:</strong> <a href="{row['LinkedIn URL']}" target="_blank">View Profile</a><br>
                    <strong>Email:</strong> {row['Email']}<br>
                    <strong>Phone:</strong> {row['Phone']}<br>
                    <strong>Guessed Email:</strong> {row['Guessed Email']}<br>
                    <strong>Raw Title:</strong> {row['Raw Title']}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
        else:
            st.warning("❌ No leads found. Try modifying your prompt.")
