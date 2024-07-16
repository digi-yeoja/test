!pip install -r requirements.txt
import streamlit as st
import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import tempfile
import fitz
import docx
import mimetypes
import anthropic

# Constants
ANTHROPIC_API_KEY = st.secrets["ANTHROPIC_API_KEY"]

# Helper Functions
def extract_file_size(size_info):
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
    with tempfile.TemporaryDirectory() as temp_dir:
        file_name = 'downloaded_file'
        file_path = os.path.join(temp_dir, file_name)
        
        response = requests.get(url)
        if response.status_code == 200:
            with open(file_path, 'wb') as file:
                file.write(response.content)
            print(f"File downloaded and saved to {file_path}")
            
            file_type = detect_file_type(file_path)
            print(f"Detected file type: {file_type}")
            
            return extract_content(file_path, file_type)
        else:
            print(f"Failed to download file. Status code: {response.status_code}")
            return None

def detect_file_type(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"

def extract_content(file_path, file_type):
    if 'pdf' in file_type:
        return extract_pdf(file_path)
    elif 'msword' in file_type or 'officedocument' in file_type:
        return extract_word(file_path)
    elif 'excel' in file_type or 'spreadsheet' in file_type:
        return f"Excel file detected: {os.path.basename(file_path)}"
    else:
        return extract_generic_text(file_path)

def extract_pdf(file_path):
    try:
        doc = fitz.open(file_path)
        full_text = []
        for page in doc:
            full_text.append(page.get_text())
        return "\n\n".join(full_text)
    except Exception as e:
        return f"Error extracting PDF: {e}"

def extract_word(file_path):
    try:
        doc = docx.Document(file_path)
        return " ".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        return f"Error extracting Word file: {e}"

def extract_generic_text(file_path):
    try:
        with open(file_path, 'rb') as file:
            content = file.read()
        return content.decode('utf-8', errors='ignore')
    except Exception as e:
        return f"Error extracting generic text: {e}"

# Initialize the client with your API key
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def summarize_text(text):
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
    cleaned_date = date_string.strip()
    return datetime.strptime(cleaned_date, "%d/%m/%Y")


# Main Streamlit App
st.title("HCP Publications Extractor")

if st.button("Extract and Summarize New Publications"):
    if 'last_run_date' not in st.session_state:
        st.session_state['last_run_date'] = None

    last_run_date = st.session_state['last_run_date']

    if last_run_date:
        st.write("Last run date: ", last_run_date.strftime("%d/%m/%Y"))
    else:
        st.write("First run - fetching all available publications")

    url = "https://www.hcp.ma/"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    publications_link = soup.find('a', href="https://www.wmaker.net/testhcp/downloads/?tag=Derni%C3%A8res+parutions")
    if publications_link:
        publications_url = publications_link['href']
        publications_response = requests.get(publications_url)
        publications_soup = BeautifulSoup(publications_response.content, 'html.parser')

        data = []
        publications = publications_soup.find_all(class_="delimiter")
        processed_titles = {}

        for pub in publications:
            title = pub.find('div', class_= 'titre_fichier').text.strip() if pub.find('div', class_= 'titre_fichier') else ""
            date_info = pub.find('div', class_='information').text.split('Publié le : ')[1].split('\n')[0].strip() if pub.find('div', class_='information') else ""
            size_info = pub.find('div', class_='information').text.split('Taille : ')[1].split(' | ')[0] if pub.find('div', class_='information') else ""
            download_link = pub.find('div', class_='information').find('a')['href'] if pub.find('div', class_='information') else ""
            download_link = url + download_link

            # Vérifier si c'est une version française ou arabe
            base_title = title.split('(version')[0].strip()
            is_french = '(version Fr)' in title
            is_arabic = '(version Ar)' in title

            # Traiter la publication si c'est une version française ou si aucune version n'est spécifiée
            if is_french or (not is_arabic and base_title not in processed_titles):
                try:
                    pub_date = parse_date(date_info)
                    if last_run_date and pub_date <= last_run_date:
                        continue
                except ValueError as e:
                    st.write(f"Erreur lors du traitement de la date '{date_info}': {e}")
                    continue  # Passer à la publication suivante en cas d'erreur

                st.write(f"Processing: {title} ({date_info})")
                size = extract_file_size(size_info)
                if size is not None and size > 10:  
                    st.write(f"File too large to download: {title} ({size:.2f} MB)")
                    data.append({
                        "Title": title,
                        "Date": date_info,
                        "Download link": download_link,
                        "Summary": "Fichier trop volumineux pour être traité"
                    })
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

                processed_titles[base_title] = True

        st.write("### Nouvelles publications détectées :")
        for item in data:
            st.write(f"**{item['Title']}**")
            st.write(f"Date de publication : {item['Date']}")
            st.markdown(item['Summary'], unsafe_allow_html=True)
            st.write("---")

        st.write(f"**Total : {len(data)} nouvelles publications.**")

        # Mise à jour de la date de dernière exécution
        st.session_state['last_run_date'] = datetime.now()
    else:
        st.write("Unable to find the PUBLICATIONS link on the webpage.")
