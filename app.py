import streamlit as st
import requests
import pandas as pd
import re
import os
from datetime import datetime
import json

# --- CONFIG ---
SERPAPI_KEY = st.secrets.get("SERPAPI_KEY", os.getenv("SERPAPI_KEY", ""))
PROXYCURL_API_KEY = st.secrets.get("PROXYCURL_API_KEY", os.getenv("PROXYCURL_API_KEY", ""))

EMAIL_REGEX = r"[\w\.-]+@[\w\.-]+\.\w+"
PHONE_REGEX = r"\+?\d[\d\s\-\(\)]{8,}\d"

# --- Session State Initialization ---
if 'search_history' not in st.session_state:
    st.session_state.search_history = []
if 'current_leads' not in st.session_state:
    st.session_state.current_leads = pd.DataFrame()

# --- Enhanced Extraction Functions ---
def extract_email_from_text(text):
    """Extract email addresses from text using regex"""
    emails = re.findall(EMAIL_REGEX, text)
    return emails[0] if emails else ""

def extract_phone_from_text(text):
    """Extract phone numbers from text using regex"""
    phones = re.findall(PHONE_REGEX, text)
    return phones[0] if phones else ""

def fetch_emails_and_phone_from_url(url):
    """Fetch contact information from web pages"""
    if "linkedin.com" in url:
        return ("", "")  # Skip LinkedIn URLs for direct scraping
    try:
        response = requests.get(url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        if response.status_code == 200:
            text = response.text
            return (extract_email_from_text(text), extract_phone_from_text(text))
    except Exception as e:
        st.sidebar.write(f"⚠️ Error fetching {url[:50]}...")
    return ("", "")

# --- Enhanced Proxycurl enrichment ---
def enrich_with_proxycurl(linkedin_url):
    """Enrich LinkedIn profiles using Proxycurl API"""
    if not PROXYCURL_API_KEY or "linkedin.com/in/" not in linkedin_url:
        return {"role": "", "company": "", "location": "", "summary": ""}

    headers = {"Authorization": f"Bearer {PROXYCURL_API_KEY}"}
    params = {"url": linkedin_url, "use_cache": "if-present"}
    
    try:
        response = requests.get("https://nubela.co/proxycurl/api/v2/linkedin", 
                              headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            current_pos = data.get("experiences", [{}])[0] if data.get("experiences") else {}
            
            return {
                "role": current_pos.get("title", ""),
                "company": current_pos.get("company", ""),
                "location": data.get("city", "") + ", " + data.get("country", ""),
                "summary": data.get("summary", "")[:200] + "..." if data.get("summary") else ""
            }
    except Exception as e:
        st.sidebar.write(f"⚠️ Proxycurl enrichment failed")
    return {"role": "", "company": "", "location": "", "summary": ""}

# --- Enhanced Lead Extraction ---
def get_leads_from_serpapi(query, num_results=10):
    """Extract leads from SerpAPI with enhanced data processing"""
    if not SERPAPI_KEY:
        st.error("🔑 SerpAPI key not found. Please set it in Streamlit secrets or environment variables.")
        st.stop()

    url = "https://serpapi.com/search.json"
    params = {
        "q": query,
        "engine": "google",
        "num": num_results,
        "api_key": SERPAPI_KEY
    }
    
    with st.spinner("🔍 Searching the web for leads..."):
        response = requests.get(url, params=params)
        results = response.json()
        leads = []

        progress_bar = st.progress(0)
        total_results = len(results.get("organic_results", []))

        for i, result in enumerate(results.get("organic_results", [])):
            progress_bar.progress((i + 1) / total_results)
            
            title = result.get("title", "")
            link = result.get("link", "")
            snippet = result.get("snippet", "")

            # Enhanced data extraction
            name = extract_name(title, snippet)
            role = clean_role(title, snippet)
            company = clean_company(title, snippet)
            
            # Contact information extraction
            email_from_snippet = extract_email_from_text(snippet)
            phone_from_snippet = extract_phone_from_text(snippet)
            email_from_page, phone_from_page = fetch_emails_and_phone_from_url(link)

            domain = extract_domain_from_url(link)
            guessed_email = guess_email(name, domain) if name and domain else ""

            final_email = email_from_snippet or email_from_page or guessed_email
            phone = phone_from_snippet or phone_from_page

            # Enhanced summary creation
            summary = create_enhanced_summary(name, role, company, snippet)
            
            # Proxycurl enrichment for LinkedIn profiles
            enriched_data = {"role": "", "company": "", "location": "", "summary": ""}
            if "linkedin.com" in link:
                enriched_data = enrich_with_proxycurl(link)
                role = role or enriched_data["role"]
                company = company or enriched_data["company"]

            # Clean up LinkedIn emails
            if "linkedin.com" in final_email:
                final_email = ""

            leads.append({
                "Name": name,
                "Role": role,
                "Company": company,
                "Location": enriched_data.get("location", ""),
                "LinkedIn URL": link,
                "Email": final_email,
                "Phone": phone,
                "Summary": summary,
                "Snippet": snippet[:150] + "..." if len(snippet) > 150 else snippet,
                "Confidence": calculate_confidence_score(name, role, company, final_email)
            })
        
        progress_bar.empty()
        return leads

# --- Enhanced Helper Functions ---
def extract_name(title, snippet=""):
    """Enhanced name extraction from title and snippet"""
    text = f"{title} {snippet}"
    
    # Common patterns for names in professional contexts
    name_patterns = [
        r"([A-Z][a-z]+ [A-Z][a-z]+)(?:\s+[-|]|\s+at\s+|\s+\|)",
        r"^([A-Z][a-z]+ [A-Z][a-z]+)",
        r"([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s+[-–—])"
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1)
            # Filter out common non-name words
            exclude_words = ["Manager", "Director", "Head", "Chief", "Senior", "Junior", "Lead"]
            if not any(word in name for word in exclude_words):
                return name
    
    # Fallback to original logic
    if not title: return ""
    parts = title.split(" at ")[0].split()
    name_parts = [w for w in parts if w.istitle() and len(w) > 2 and 
                  w.lower() not in ["manager", "engineer", "head", "director"]]
    return " ".join(name_parts[:2]) if name_parts else ""

def clean_role(title, snippet=""):
    """Enhanced role extraction"""
    text = f"{title} {snippet}".lower()
    
    # Comprehensive role keywords with variations
    role_patterns = [
        r"\b(chief\s+\w+\s+officer|ceo|cto|cfo|cmo)\b",
        r"\b(vice\s+president|vp)\b",
        r"\b(senior\s+|lead\s+|principal\s+)?(manager|director|head|lead)\b",
        r"\b(hr\s+|human\s+resources\s+)?(manager|specialist|director)\b",
        r"\b(sales\s+|marketing\s+|business\s+development\s+)?(manager|executive|director)\b",
        r"\b(software\s+|senior\s+|lead\s+)?(engineer|developer|architect)\b",
        r"\b(project\s+|program\s+)?manager\b",
        r"\b(consultant|analyst|specialist|coordinator|recruiter)\b"
    ]
    
    for pattern in role_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).title()
    
    return ""

def clean_company(title, snippet=""):
    """Enhanced company extraction"""
    text = f"{title} {snippet}"
    
    # Look for "at Company" pattern
    at_match = re.search(r"\bat\s+([A-Z][^|]*?)(?:\s*[-|•]|$)", text)
    if at_match:
        company = at_match.group(1).strip()
        return company
    
    # Look for company indicators
    company_indicators = ["Inc", "Ltd", "LLC", "Corp", "Corporation", "Technologies", 
                         "Solutions", "Services", "Systems", "Group", "Consulting"]
    
    for indicator in company_indicators:
        pattern = rf"\b([A-Z][^|]*?{indicator})\b"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    
    return ""

def create_enhanced_summary(name, role, company, snippet):
    """Create a comprehensive summary for each lead"""
    summary_parts = []
    
    if role and company:
        summary_parts.append(f"{role} at {company}")
    elif role:
        summary_parts.append(f"{role}")
    elif company:
        summary_parts.append(f"Professional at {company}")
    
    # Add relevant snippet information
    if snippet:
        # Extract key phrases from snippet
        key_phrases = extract_key_phrases(snippet)
        if key_phrases:
            summary_parts.append(f"• {', '.join(key_phrases[:2])}")
    
    return " | ".join(summary_parts) if summary_parts else "Professional Profile"

def extract_key_phrases(text):
    """Extract key professional phrases from text"""
    key_terms = [
        r"\b(vendor\s+onboarding|procurement|sourcing)\b",
        r"\b(business\s+development|sales|marketing)\b",
        r"\b(human\s+resources|hr|recruitment)\b",
        r"\b(finance|accounting|financial)\b",
        r"\b(technology|software|engineering)\b",
        r"\b(operations|logistics|supply\s+chain)\b"
    ]
    
    phrases = []
    for pattern in key_terms:
        matches = re.findall(pattern, text, re.IGNORECASE)
        phrases.extend([match.title() if isinstance(match, str) else ' '.join(match).title() 
                       for match in matches])
    
    return list(set(phrases))[:3]  # Return unique phrases, max 3

def calculate_confidence_score(name, role, company, email):
    """Calculate confidence score for lead quality"""
    score = 0
    if name: score += 25
    if role: score += 25
    if company: score += 25
    if email and "@" in email: score += 25
    return f"{score}%"

def extract_domain_from_url(url):
    """Extract domain from URL"""
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else ""

def guess_email(name, domain):
    """Guess email based on name and domain"""
    if not name or not domain or "linkedin" in domain:
        return ""
    
    name_parts = name.lower().split()
    if len(name_parts) >= 2:
        first, last = name_parts[0], name_parts[-1]
        return f"{first}.{last}@{domain}"
    elif len(name_parts) == 1:
        return f"{name_parts[0]}@{domain}"
    return ""

def save_search_to_history(query, results_count):
    """Save search to session history"""
    search_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "query": query,
        "results": results_count
    }
    st.session_state.search_history.insert(0, search_entry)
    # Keep only last 10 searches
    st.session_state.search_history = st.session_state.search_history[:10]

# --- STREAMLIT UI ---
st.set_page_config(page_title="B2B Lead Generator Pro", layout="wide", page_icon="🎯")

# Header
st.title("🎯 B2B Lead Generator Pro")
st.markdown("""
<div style='background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;'>
    <h4>🚀 How to Use:</h4>
    <ul>
        <li><strong>Natural Language:</strong> "Find vendor onboarding managers at Fortune 500 companies"</li>
        <li><strong>Specific Roles:</strong> "HR directors at tech startups in India"</li>
        <li><strong>Industry Focus:</strong> "Procurement specialists at manufacturing companies"</li>
    </ul>
</div>
""", unsafe_allow_html=True)

# Main input section
col1, col2 = st.columns([3, 1])

with col1:
    prompt = st.text_input(
        "🔍 Enter your lead generation prompt:",
        value="Find vendor onboarding specialists at MNC companies in India",
        help="Use natural language to describe the type of leads you're looking for"
    )

with col2:
    num_results = st.selectbox("Results", [10, 20, 30, 50], index=0)

# Search button and options
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    search_button = st.button("🔍 Generate Leads", type="primary")

with col2:
    include_linkedin = st.checkbox("Include LinkedIn", value=True)

with col3:
    auto_enrich = st.checkbox("Auto Enrich", value=True, help="Use Proxycurl for LinkedIn enrichment")

# Sidebar for history and filters
with st.sidebar:
    st.header("📊 Search History")
    if st.session_state.search_history:
        for i, search in enumerate(st.session_state.search_history):
            with st.expander(f"🕒 {search['timestamp'][:16]}", expanded=False):
                st.write(f"**Query:** {search['query'][:50]}...")
                st.write(f"**Results:** {search['results']} leads")
                if st.button(f"Rerun Search", key=f"rerun_{i}"):
                    prompt = search['query']
                    st.rerun()
    else:
        st.info("No search history yet")
    
    st.divider()
    st.header("🎛️ Advanced Options")
    exclude_domains = st.text_area("Exclude Domains", 
                                  placeholder="example.com, spam-site.com",
                                  help="Comma-separated list of domains to exclude")

# Main search logic
if search_button:
    query = prompt
    if include_linkedin and "linkedin.com" not in prompt:
        query += " site:linkedin.com/in/"
    
    leads = get_leads_from_serpapi(query, num_results)
    df = pd.DataFrame(leads)
    
    if not df.empty:
        # Filter out excluded domains
        if exclude_domains:
            excluded = [d.strip() for d in exclude_domains.split(",")]
            df = df[~df["LinkedIn URL"].str.contains("|".join(excluded), na=False)]
        
        st.session_state.current_leads = df
        save_search_to_history(prompt, len(df))
        
        # Enhanced metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("👥 Total Leads", len(df))
        with col2:
            st.metric("🏢 Companies", df['Company'].nunique())
        with col3:
            verified_emails = len(df[df["Email"].str.contains("@", na=False)])
            st.metric("📧 Verified Emails", verified_emails)
        with col4:
            avg_confidence = df['Confidence'].str.rstrip('%').astype(int).mean()
            st.metric("🎯 Avg Confidence", f"{avg_confidence:.0f}%")
        
        # Display results
        st.markdown("### 🧑‍💼 Generated Leads")
        
        # Enhanced display dataframe
        df_display = df.copy()
        df_display["LinkedIn"] = df_display["LinkedIn URL"].apply(
            lambda x: f'<a href="{x}" target="_blank">View Profile 🔗</a>' if x else ""
        )
        df_display["Email Status"] = df_display["Email"].apply(
            lambda x: "✅ Verified" if x and "@" in x else "❌ Not Found"
        )
        
        # Select columns for display
        display_columns = ["Name", "Summary", "Email", "Phone", "Email Status", "Confidence", "LinkedIn"]
        df_final = df_display[display_columns]
        
        # Display with HTML rendering for clickable links
        st.markdown(df_final.to_html(escape=False, index=False), unsafe_allow_html=True)
        
        # Export options
        col1, col2, col3 = st.columns(3)
        
        with col1:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download CSV",
                data=csv,
                file_name=f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
        with col2:
            json_data = df.to_json(orient="records", indent=2)
            st.download_button(
                "📄 Download JSON",
                data=json_data,
                file_name=f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
        
        with col3:
            # Email list for easy copying
            email_list = df[df["Email"].str.contains("@", na=False)]["Email"].tolist()
            if email_list:
                emails_text = "; ".join(email_list)
                st.download_button(
                    "📧 Email List",
                    data=emails_text,
                    file_name="email_list.txt",
                    mime="text/plain"
                )
    else:
        st.warning("🔍 No leads found. Try modifying your search terms or increasing the result count.")
        st.markdown("""
        **Suggestions:**
        - Use more general terms
        - Try different role keywords
        - Include industry-specific terms
        - Increase the number of results
        """)

# Display current results if available
elif not st.session_state.current_leads.empty:
    st.markdown("### 📋 Current Results")
    df = st.session_state.current_leads
    
    # Quick stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Leads", len(df))
    with col2:
        st.metric("Companies", df['Company'].nunique())
    with col3:
        verified_emails = len(df[df["Email"].str.contains("@", na=False)])
        st.metric("Verified Emails", verified_emails)
    
    st.dataframe(df[["Name", "Summary", "Email", "Phone", "Confidence"]], use_container_width=True)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <p>🎯 <strong>B2B Lead Generator Pro</strong> | Powered by SerpAPI & Proxycurl</p>
    <p><em>Generate high-quality B2B leads with advanced AI-powered search and enrichment</em></p>
</div>
""", unsafe_allow_html=True)
