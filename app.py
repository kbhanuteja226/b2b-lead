import streamlit as st
import requests
import pandas as pd
import re
import os

# --- CONFIG ---
SERPAPI_KEY = st.secrets.get("SERPAPI_KEY", os.getenv("SERPAPI_KEY", ""))

EMAIL_REGEX = r"[\w\.-]+@[\w\.-]+\.\w+"
PHONE_REGEX = r"\+?\d[\d\s\-\(\)]{8,}\d"

# --- Extraction ---
def extract_email_from_text(text):
    emails = re.findall(EMAIL_REGEX, text)
    return emails[0] if emails else ""

def extract_phone_from_text(text):
    phones = re.findall(PHONE_REGEX, text)
    return phones[0] if phones else ""

def fetch_emails_and_phone_from_url(url):
    if "linkedin.com" in url:
        return ("", "")  # Skip LinkedIn URLs
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            text = response.text
            return (extract_email_from_text(text), extract_phone_from_text(text))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return ("", "")

# --- Lead Extraction from SerpAPI ---
def get_leads_from_serpapi(query, num_results=10):
    if not SERPAPI_KEY:
        st.error("SerpAPI key not found. Please set it in Streamlit secrets or environment variables.")
        st.stop()

    url = "https://serpapi.com/search.json"
    params = {
        "q": query,
        "engine": "google",
        "num": num_results,
        "api_key": SERPAPI_KEY
    }
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

        email_from_snippet = extract_email_from_text(snippet)
        phone_from_snippet = extract_phone_from_text(snippet)
        email_from_page, phone_from_page = fetch_emails_and_phone_from_url(link)

        domain = extract_domain_from_url(link)
        guessed_email = guess_email(name, domain) if name and domain else ""

        final_email = email_from_snippet or email_from_page or guessed_email
        phone = phone_from_snippet or phone_from_page

        if "linkedin.com" in final_email:
            final_email = ""

        leads.append({
            "Name": name,
            "Role": role,
            "Company": company,
            "LinkedIn URL": link,
            "Email": final_email,
            "Phone": phone
        })
    return leads

# --- Helpers ---
def extract_name(title):
    if not title: return ""
    parts = title.split(" at ")[0].split()
    name_parts = [w for w in parts if w.istitle() and len(w) > 2 and w.lower() not in ["manager", "engineer", "head"]]
    return " ".join(name_parts[:2]) if name_parts else ""

def clean_role(text):
    if not isinstance(text, str): return ""
    role_keywords = [
        "manager", "executive", "specialist", "recruiter", "head", "lead",
        "officer", "analyst", "director", "coordinator", "consultant", "rcm",
        "engineer", "developer", "hr", "human resources"
    ]
    for word in role_keywords:
        match = re.search(rf"\b\w*{word}\w*\b", text, re.I)
        if match:
            return match.group(0).title()
    return ""

def clean_company(text):
    if not isinstance(text, str): return ""
    company_keywords = [
        "pvt", "private", "solutions", "technologies", "services", "inc",
        "ltd", "llp", "consulting", "systems", "enterprises", "group"
    ]
    for word in company_keywords:
        if word.lower() in text.lower():
            return text
    return ""

def extract_domain_from_url(url):
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    if match:
        return match.group(1)
    return ""

def guess_email(name, domain):
    if not name or not domain:
        return ""
    name_parts = name.lower().split()
    if len(name_parts) >= 2:
        first, last = name_parts[0], name_parts[-1]
        return f"{first}.{last}@{domain}"
    elif len(name_parts) == 1:
        return f"{name_parts[0]}@{domain}"
    return ""

# --- STREAMLIT UI ---
st.set_page_config(page_title="B2B Lead Generator", layout="centered")
st.title("Prompt-Based B2B Lead Generator")
st.markdown("Enter a natural prompt like: _'Get leads for vendor onboarding at MNCs for SURG'_")

prompt = st.text_input("Enter your prompt", value="Give me all the leads for vendor onboarding of SURG to different MNCs")


if st.button("Generate Leads"):
    with st.spinner("Searching the web..."):
        query = prompt
        if "linkedin.com" not in prompt:
            query += " site:linkedin.com/in/"

        leads = get_leads_from_serpapi(query)
        df = pd.DataFrame(leads)

        if not df.empty:
            

            df["Verified"] = df["Email"].apply(lambda x: "✅" if x and "@" in x else "")

            st.success(f" {len(df)} leads found.")
            st.markdown(f" **Companies found:** {df['Company'].nunique()}")
            st.markdown(f"**Unique names:** {df['Name'].nunique()}")

            st.dataframe(df)
            csv = df.drop(columns=["Verified"]).to_csv(index=False).encode('utf-8')
            st.download_button(" Download as CSV", data=csv, file_name="leads.csv", mime="text/csv")
        else:
            st.warning("No leads found. Try modifying your prompt or filters.")
