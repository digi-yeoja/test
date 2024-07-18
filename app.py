import streamlit as st
import os
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import tempfile
import fitz 
import docx
import mimetypes
import anthropic

# Constants
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DATABASE_URL = os.environ['DATABASE_URL']

# Helper Functions
def extract_file_size(size_info):
    """Extracts file size from formatted string."""
    size, unit = size_info.split()
    size = float(size)
    if unit.lower() == 'ko':
        return size / 1024
    elif unit.lower() == 'mo':
        return size 
    else:
        print(f"Unrecognized size unit: {unit}")
        return None

def download_and_extract_content(url):
    """Downloads a file from the given URL and extracts its content."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_name = 'downloaded_file'
        file_path = os.path.join(temp_dir, file_name)
        
        response = requests.get(url)
        if response.status_code == 200:
            with open(file_path, 'wb') as file:
                file.write(response.content)
            print(f"File downloaded and saved to {file_path}")
            
            file_type = detect_file_type(file_path)
            
            return extract_content(file_path, file_type)
        else:
            print(f"Failed to download file. Status code: {response.status_code}")
            return None

def detect_file_type(file_path):
    """Detects the MIME type of a file."""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"

def extract_content(file_path, file_type):
    """Extracts content from different types of files."""
    if 'pdf' in file_type:
        return extract_pdf(file_path)
    elif 'msword' in file_type or 'officedocument' in file_type:
        return extract_word(file_path)
    elif 'excel' in file_type or 'spreadsheet' in file_type:
        return f"Excel file detected: {os.path.basename(file_path)}"
    else:
        return extract_generic_text(file_path)

def extract_pdf(file_path):
    """Extracts text content from a PDF file."""
    try:
        doc = fitz.open(file_path)
        full_text = []
        for page in doc:
            full_text.append(page.get_text())
        return "\n\n".join(full_text)
    except Exception as e:
        return f"Error extracting PDF: {e}"

def extract_word(file_path):
    """Extracts text content from a Word document."""
    try:
        doc = docx.Document(file_path)
        return " ".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        return f"Error extracting Word file: {e}"

def extract_generic_text(file_path):
    """Extracts text content from a generic file."""
    try:
        with open(file_path, 'rb') as file:
            content = file.read()
        return content.decode('utf-8', errors='ignore')
    except Exception as e:
        return f"Error extracting generic text: {e}"

# Initialize the client with your API key
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def summarize_text(text):
    """Summarizes text using the Anthropi API."""
    try:
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1000,
            temperature=0.3,
            messages=[
                {"role": "user", 
                "content": f"""Summarize the following text even if it's in arabic as a bullet point list in French. Capture all main ideas and key information, organizing points by themes if possible. 
                            Text to summarize:\n\n{text}\n\nExample summary:
                            Original text: The new iPhone 13 Pro features a redesigned camera system, longer battery life, and a faster A15 Bionic chip. It also includes new software features like Photographic Styles and Cinematic mode.
                            Example summary:
                                L'iPhone 13 Pro présente plusieurs améliorations notables par rapport à son prédécesseur :
                                    • Système de caméra repensé
                                    • Durée de vie de la batterie améliorée
                                    • Puce A15 Bionic plus rapide
                                    • Nouvelles fonctionnalités logicielles :
                                        - Styles photographiques
                                        - Mode cinématique

                            Additional instructions:
                                - Start each main point with a bullet point symbol (•) and bold
                                - Retain important figures and percentages
                                - Include all key information and ideas
                                - Do not add external information
                                - Ensure the summary captures the essence of the entire text, regardless of the length, prioritizing the most important information
                                """}
            ]
        )
        return response.content[0].text  
    except anthropic.APIError as e:
        print(f"An error occurred while calling the API: {e}")
        return None

def parse_date(date_string):
    """Parses date from string format."""
    cleaned_date = date_string.strip()
    return datetime.strptime(cleaned_date, "%d/%m/%Y")

def init_db():
    """Initializes the connection to the PostgreSQL database."""
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    with conn.cursor() as cur:
        cur.execute('''CREATE TABLE IF NOT EXISTS users
                       (username TEXT PRIMARY KEY, last_run_date TIMESTAMP)''')
    conn.commit()
    return conn

def upsert_user(conn, username):
    """Inserts or updates a user in the database."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (username) VALUES (%s) ON CONFLICT (username) DO NOTHING", (username,))
    conn.commit()

def get_last_run_date(conn, username):
    """Retrieves the last run date for a user from the database."""
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute("SELECT last_run_date FROM users WHERE username = %s", (username,))
        result = cur.fetchone()
    return result['last_run_date'] if result else None

def update_last_run_date(conn, username, date):
    """Updates the last run date for a user in the database."""
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET last_run_date = %s WHERE username = %s", (date, username))
    conn.commit()

# Initialize database connection if not already done
if 'db_conn' not in st.session_state:
    st.session_state.db_conn = init_db()  

# Streamlit App
st.title("HCP Publications Extractor")

# User Input: Username
username = st.text_input("Enter your username")

# Handle user interaction
if username:
    upsert_user(st.session_state.db_conn, username) 
    st.success(f"Welcome {username}!")

    last_run_date = get_last_run_date(st.session_state.db_conn, username)

    if last_run_date:
        st.write(f"Last run date:", last_run_date)  
    else:
        st.write("First run - all publications available will be extracted.")
        
######################################################################
    # Button to reset last run date
    if st.button("Reset last run date"):
        update_last_run_date(st.session_state.db_conn, username, None) 
        st.success("Last run date reset.")
        st.rerun() 
#######################################################################

    # Button to extract and summarize new publications
    if st.button("Extract and summarize new publications"):
        url = "https://www.hcp.ma/"
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find link to latest publications
        publications_link = soup.find('a', href="https://www.wmaker.net/testhcp/downloads/?tag=Derni%C3%A8res+parutions")
        if publications_link:
            publications_url = publications_link['href']
            publications_response = requests.get(publications_url)
            publications_soup = BeautifulSoup(publications_response.content, 'html.parser')

            data = []
            publications = publications_soup.find_all(class_="delimiter")
            processed_titles = set()

            # Iterate through each publication
            for pub in publications:
                title = pub.find('div', class_='titre_fichier').text.strip() if pub.find('div', class_='titre_fichier') else ""
                date_info = pub.find('div', class_='information').text.split('Publié le : ')[1].split('\n')[0].strip() if pub.find('div', class_='information') else ""
                size_info = pub.find('div', class_='information').text.split('Taille : ')[1].split(' | ')[0] if pub.find('div', class_='information') else ""
                download_link = pub.find('div', class_='information').find('a')['href'] if pub.find('div', class_='information') else ""
                download_link = url + download_link

                # Check if it's an Arabic version of a title already processed
                base_title = title.split('(version')[0].strip()
                if base_title in processed_titles:
                    continue

                # Process only French or non-Arabic versions of titles
                if '(version Fr)' in title or '(version Ar)' not in title:
                    try:
                        pub_date = parse_date(date_info)
                        if last_run_date and pub_date <= last_run_date:
                            continue  # Skip if publication date is before last run date
                    except ValueError as e:
                        st.write(f"Error processing date '{date_info}': {e}")
                        continue  # Skip to next publication on date processing error

                    size = extract_file_size(size_info)
                    if size is not None and size > 10:  
                        st.write(f"File too large to download: {title} ({size:.2f} MB)")
                    elif download_link:
                        content = download_and_extract_content(download_link)
                        if content:
                            #summary = summarize_text(content)
                            summary = True 
                            if summary:
                                data.append({
                                    "Title": title,
                                    "Date": date_info,
                                    "Download link": download_link,
                                    "Summary": summary
                                })
                            else:
                                st.write("Unable to generate a summary for this content.")

                    processed_titles.add(base_title)

            # Display detected new publications
            st.write("### Detected new publications:")
            for item in data:
                st.write(f"**{item['Title']}**")
                st.write(f"Publication Date: {item['Date']}")
                st.markdown(item['Summary'], unsafe_allow_html=True)  # Render summary as markdown
                st.write("---")

            st.write(f"**Total : {len(data)} new publications.**")

            # Update last run date after processing
            update_last_run_date(st.session_state.db_conn, username, datetime.now())
        else:
            st.warning("Please enter a username to continue.")


