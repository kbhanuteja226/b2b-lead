
import streamlit as st
import requests
import pandas as pd
import re
import os

SERPAPI_KEY = st.secrets.get("SERPAPI_KEY", os.getenv("SERPAPI_KEY", ""))

EMAIL_REGEX = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
PHONE_REGEX = r"(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?:\s*x\d+)?"

def extract_email_from_text(text):
    emails = re.findall(EMAIL_REGEX, text)
    return emails[0] if emails else ""

def extract_phone_from_text(text):
    phones = re.findall(PHONE_REGEX, text)
    return phones[0] if phones else ""

def fetch_emails_and_phone_from_url(url):
    if "linkedin.com" in url:
        return ("", "")
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }
    try:
        response = requests.get(url, timeout=5, headers=headers)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' not in content_type:
            return ("", "")
        text = response.text
        return (extract_email_from_text(text), extract_phone_from_text(text))
    except:
        return ("", "")

def extract_name(title):
    if not title:
        return ""
    name_match = re.search(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})", title)
    if name_match:
        potential_name = name_match.group(1)
        if not any(role in potential_name for role in ["Manager", "Director", "Engineer", "Head", "Consultant", "Specialist"]):
            return potential_name.strip()
    parts = title.split(" at ")[0].split()
    name_parts = [w for w in parts if w.istitle() and len(w) > 2 and w.lower() not in ["manager", "engineer", "head", "director", "consultant"]]
    return " ".join(name_parts[:2]) if name_parts else ""

def clean_role(text):
    if not isinstance(text, str):
        return ""
    role_keywords = [
        r"\b(?:sr\.|senior\s)?manager\b", r"\b(?:vp|vice president)\b", r"\bexecutive\b",
        r"\bspecialist\b", r"\brecruiter\b", r"\bhead\b", r"\blead\b",
        r"\bofficer\b", r"\banalyst\b", r"\bdirector\b", r"\bcoordinator\b",
        r"\bconsultant\b", r"\brcm\b", r"\bengineer\b", r"\bdeveloper\b",
        r"\b(?:hr|human resources)\b", r"\bassociate\b", r"\bassistant\b"
    ]
    for pattern in role_keywords:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0).title()
    return ""

def clean_company(text):
    if not isinstance(text, str):
        return ""
    company_match = re.search(r"at\s+([^\-]+(?:Pvt|Private|Solutions|Technologies|Services|Inc|Ltd|LLP|Consulting|Systems|Enterprises|Group)\b.*)", text, re.I)
    if company_match:
        return company_match.group(1).strip()
    company_keywords_regex = [
        r"\b(?:Pvt|Private)\b", r"\bSolutions\b", r"\bTechnologies\b", r"\bServices\b",
        r"\bInc(?:orporated)?\b", r"\bLtd(?:d)?\b", r"\bLLP\b", r"\bConsulting\b",
        r"\bSystems\b", r"\bEnterprises\b", r"\bGroup\b", r"\bCorp(?:oration)?\b",
        r"\b(?:Co\.|Company)\b", r"\b(?:Ag|Gmbh|S.A\.|S.P.A)\b"
    ]
    for pattern in company_keywords_regex:
        match = re.search(pattern, text, re.I)
        if match:
            pre_match_text = text[:match.start()].strip()
            parts = re.split(r"[-,\(]", pre_match_text)
            if parts:
                return parts[-1].strip() + " " + match.group(0).strip()
            else:
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
    if not name_parts:
        return ""
    first_name = name_parts[0]
    last_name = name_parts[-1] if len(name_parts) > 1 else ""
    patterns = []
    if first_name and last_name:
        patterns.append(f"{first_name}.{last_name}@{domain}")
        patterns.append(f"{first_name[0]}{last_name}@{domain}")
        patterns.append(f"{first_name}{last_name}@{domain}")
        patterns.append(f"{last_name}.{first_name}@{domain}")
    patterns.append(f"{first_name}@{domain}")
    return patterns[0] if patterns else ""

def get_leads_from_serpapi(query, num_results=10):
    if not SERPAPI_KEY:
        st.error("SerpAPI key not found.")
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
        email_from_page, phone_from_page = "", ""
        if not email_from_snippet and not phone_from_snippet:
            email_from_page, phone_from_page = fetch_emails_and_phone_from_url(link)
        domain = extract_domain_from_url(link)
        guessed_email = guess_email(name, domain) if name and domain else ""
        final_email = email_from_snippet or email_from_page or guessed_email
        phone = phone_from_snippet or phone_from_page
        if "linkedin.com" in final_email.lower():
            final_email = ""
        leads.append({
            "Name": name,
            "Role": role,
            "Company": company,
            "LinkedIn URL": link,
            "Email": final_email,
            "Phone": phone,
            "Domain": domain,
            "Guessed Email": guessed_email,
            "Raw Title": title
        })
    return leads

st.set_page_config(page_title="B2B Lead Generator", layout="centered")
st.title("Prompt-Based B2B Lead Generator")
st.markdown("Enter a natural prompt like: _'Get leads for vendor onboarding at MNCs for SURG'_")

prompt = st.text_input("Enter your prompt", value="Give me all the leads for vendor onboarding of SURG to different MNCs")

if st.button("Generate Leads"):
    with st.spinner("Searching the web..."):
        query = prompt
        if "site:linkedin.com/in/" not in query.lower():
            query += " site:linkedin.com/in/"
        leads = get_leads_from_serpapi(query)
        df = pd.DataFrame(leads)
        st.write("Raw Extracted Leads:", df)
        if not df.empty:
            df["Verified"] = df["Email"].apply(lambda x: "✅" if x and "@" in x else "")
            st.success(f"{len(df)} leads found.")
            st.markdown(f"**Companies found:** {df['Company'].nunique()}")
            st.markdown(f"**Unique names:** {df['Name'].nunique()}")
            df["LinkedIn"] = df["LinkedIn URL"].apply(lambda x: f"[View Profile]({x})")
            df["Summary"] = df["Role"].fillna("") + " at " + df["Company"].fillna("")
            
            # Display markdown version with clickable links in UI
            df_display_markdown = df[["Name", "Summary", "Email", "Phone", "LinkedIn", "Verified"]]
            st.markdown("### 🧑‍💼 Leads Table")
            st.markdown(df_display_markdown.to_markdown(index=False), unsafe_allow_html=True)
            
            # CSV version with raw URL
            df_csv = df[["Name", "Summary", "Email", "Phone", "LinkedIn URL", "Verified"]]
            csv = df_csv.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download as CSV", data=csv, file_name="leads.csv", mime="text/csv")

        else:
            st.warning("No leads found. Try modifying your prompt.")
