import streamlit as st
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import chromedriver_autoinstaller
import tempfile
import requests
import fitz
import docx
import mimetypes
import anthropic

# Constants
last_run_file = 'last_run.txt'
ANTHROPIC_API_KEY = st.secrets['ANTHROPIC_API_KEY']

# Helper Functions
def read_last_run_date():
    if os.path.exists(last_run_file):
        with open(last_run_file, 'r') as file:
            last_run_date = file.read().strip()
            return datetime.strptime(last_run_date, '%Y-%m-%d %H:%M:%S')
    return None

def save_current_run_date():
    with open(last_run_file, 'w') as file:
        file.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

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
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,
            temperature=0.3,
            messages=[
                {"role": "user", 
                "content": f"""Summarize the following text as a bullet point list in French. Capture all main ideas and key information, organizing points by themes if possible. Ensure each bullet is concise and informative.
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
                                - Use sub-bullets (-) if necessary for details
                                - Retain important figures and percentages
                                - Include all key information and ideas
                                - Do not add external information
                                - Ensure the summary captures the essence of the entire text, regardless of the length
                                - Aim for completeness within the token limit, prioritizing the most important information
                                - don't start with such sentences: Voici un résumé en français sous forme de liste à puces des principaux points du texte 
                                """}
            ]
        )
        return response.content[0].text  
    except anthropic.APIError as e:
        print(f"An error occurred while calling the API: {e}")
        return None

# Main Streamlit App
st.title("HCP Publications Extractor")

if st.button("Extract and Summarize New Publications"):
    last_run_date = read_last_run_date()
    st.write("Last run date: ", last_run_date)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920x1080')

    chromedriver_autoinstaller.install()

    url = "https://www.hcp.ma/"
    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get(url)

        WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "PUBLICATIONS"))
        ).click()

        data = []

        list_of_results = WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "delimiter"))
        )

        for result in list_of_results:
            text = result.text
            try:
                img = result.find_element(By.CSS_SELECTOR, "a img")
                parent = img.find_element(By.XPATH, '..')
                download_link = parent.get_attribute('href')
            except NoSuchElementException:
                download_link = ""
            
            if '\n\n' in text:
                title, tags_info = text.split('\n\n', 1)
                published_date_info = tags_info.split('Publié le : ')[1].split('\n')[0]
                size_info = tags_info.split('Taille : ')[1].split(' | ')[0]
            else:
                title = text.strip()
                published_date_info = ""
                size_info = ""

            if last_run_date:
                pub_date = datetime.strptime(published_date_info, '%d/%m/%Y')
                if pub_date <= last_run_date:
                    continue

            size = extract_file_size(size_info)
            if size is not None and size > 10:  
                st.write(f"File too large to download: {title} ({size:.2f} MB)")
            elif download_link:
                content = download_and_extract_content(download_link)
                if content:
                    summary = summarize_text(content)
                    if summary:
                        st.markdown(f"#### {title}")
                        st.markdown(summary, unsafe_allow_html=True)
                    else:
                        st.write("Unable to generate a summary for this content.")

                data.append({
                    "Title": title,
                    "Download link": download_link,
                })

        num_new_publications = len(data)

        save_current_run_date()

    except (TimeoutException, NoSuchElementException) as e:
        st.write(f"An error occurred: {e}")
        
    finally:
        driver.quit()

    if data:
        st.write(f"**- {num_new_publications}  new publications detected.**")
    else:
        st.write("**No new publications found.**")
