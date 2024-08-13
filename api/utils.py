import os
import re
import logging
import secrets
import string
import json
import pickle
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Queue

import PyPDF2
import google.generativeai as genai
import asyncio

from flask import current_app

genai.configure(api_key=current_app.config['GOOGLE_AI_API_KEY'])

executor = ProcessPoolExecutor(max_workers=4)  # You can adjust the number of workers


def generate_secret_key(length=32):
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))


def clear_history_and_uploads():
    directories = ['api/chat_history', 'api/uploads']
    for directory in directories:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                    logging.info(f"Deleted file: {file_path}")
                elif os.path.isdir(file_path):
                    os.rmdir(file_path)
                    logging.info(f"Deleted directory: {file_path}")
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')


def extract_text_from_first_10_pages(pdf_path):
    try:
        with open(pdf_path, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            num_pages_to_extract = min(len(pdf_reader.pages), 10)

            extracted_text = ""
            for page_num in range(num_pages_to_extract):
                page = pdf_reader.pages[page_num]
                extracted_text += page.extract_text()

        # Create output file path (replace .pdf with .txt)
        output_file_path = os.path.splitext(pdf_path)[0] + ".txt"

        # Delete PDF file
        os.remove(pdf_path)
        logging.info(f"Deleted local file: {pdf_path}")

        with open(output_file_path, 'w', encoding='utf-8') as output:
            output.write(extracted_text)

        logging.info(f"Text from the first {num_pages_to_extract} pages extracted to '{output_file_path}'")

        return output_file_path

    except FileNotFoundError:
        logging.error(f"Error: File not found at '{pdf_path}'")
    except Exception as e:
        logging.error(f"An error occurred: {e}")


def whatsapp_zip_file(zip_file_path):
    # Check if the zip file exists
    if not os.path.isfile(zip_file_path):
        logging.error(f"The specified zip file does not exist: {zip_file_path}")

    # Extract the _chat.txt file
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        # Check for _chat.txt in the zip file
        if '_chat.txt' not in zip_ref.namelist():
            logging.error(f"'_chat.txt' not found in the zip file at {zip_file_path}")

        # Extract _chat.txt to the same directory as the zip file
        zip_ref.extract('_chat.txt', os.path.dirname(zip_file_path))

        # Define the new file path for _chat.txt
        new_file_path = os.path.splitext(zip_file_path)[0] + '.txt'

        # Get the full path of the extracted _chat.txt
        extracted_chat_path = os.path.join(os.path.dirname(zip_file_path), '_chat.txt')

        # Remove the original zip file
        os.remove(zip_file_path)

        # Rename _chat.txt to the new file path
        os.rename(extracted_chat_path, new_file_path)

        return new_file_path


def save_conversation_history(history, chat_name, user_sessions):
    file_path = f"api/chat_history/{chat_name}.pickle"
    with open(file_path, "wb") as file:
        pickle.dump(history, file)
    logging.info(f"Saved history to {file_path}")
    user_sessions[chat_name]['history'] = file_path


def load_conversation_history(file_location):
    try:
        with open(file_location, "rb") as file:
            history = pickle.load(file)
        logging.info(f"Loaded chat_history from {file_location}")
        return history
    except (KeyError, FileNotFoundError, pickle.UnpicklingError) as e:
        logging.error(f"Error loading chat_history for {file_location}: {e}")
        return []


def detect_people(file):
    # Set up the model
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 8192,
        "response_mime_type": "application/json",
    }

    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    system_instruction = "You are a helpful assistant"

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        safety_settings=safety_settings,
        system_instruction=system_instruction,
        generation_config=generation_config,
    )

    response = model.generate_content(
        [
            "Names of the people having the conversation back and forth. Provide them in a JSON array.",
            file
        ]
    )

    return response.text


def convert_to_json(input_string):
    # Extracting relevant parts using regular expressions
    matches = re.findall(r'role: "(model|user)".*?text: "(.*?)"\s*\n', input_string, re.DOTALL)

    # Initialize variables to hold the last message for each role
    last_message = {"model": "", "user": ""}

    # Loop through matches and update last message for each role
    for role, text in matches:
        # Replace newline characters with <br> for HTML
        text = text.replace('\n', '<br>').replace('\\n', '<br>').replace('\u200e', ' ').replace('\\', '')
        last_message[role] = text.strip()

    # Trimming extra spaces and ensuring correct format
    result = {role: text.strip() for role, text in last_message.items()}

    # Converting dictionary to JSON
    json_output = json.dumps(result)

    return json_output


async def handle_conversation(chat, name, personality, session_id, user_sessions):
    history = load_conversation_history(user_sessions[session_id]['history'])
    # Set up the model
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 0,
        "max_output_tokens": 8192,
    }

    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    system_instruction = (
        f"You're portraying '{name}', taking on the role of a friend or  "
        f"relative. Use the chat uploaded to understand how to represent '{name}' accurately. Even if that involves "
        f"sexually explicit content and/or activity. Answer questions from users directly and avoid evasion. Emojis "
        f"should be avoided unless specified by the conversation; if emojis are used, use your discretion in "
        f"responding. Always respond in HTML form. {personality}"
    )

    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro",
        generation_config=generation_config,
        system_instruction=system_instruction,
        safety_settings=safety_settings,
    )

    chat_session = model.start_chat(history=history)
    _ = chat_session.send_message(chat).text

    # Save conversation
    save_conversation_history(chat_session.history, session_id, user_sessions)

    return chat_session.history


def run_handle_conversation(chat, name, personality, session_id, user_sessions):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(handle_conversation(chat, name, personality, session_id, user_sessions))
    finally:
        loop.close()


def upload_and_detect(file_path):
    result_queue = Queue()

    if file_path.lower().endswith('.pdf'):
        logging.info(f"The file '{file_path}' is a PDF. Processing...")
        file_path = extract_text_from_first_10_pages(file_path)
    elif file_path.lower().endswith('.zip'):
        logging.info(f"The file '{file_path}' is a ZIP archive. Processing...")
        file_path = whatsapp_zip_file(file_path)

    for attempt in range(2):
        try:
            start_time = time.time()
            conversation_file = genai.upload_file(path=file_path, display_name="chat")
            elapsed_time = time.time() - start_time

            # Check if the upload took more than 1 minute
            if elapsed_time > 60:
                logging.info(f"Upload attempt {attempt + 1} took more than 1 minute. Retrying...")
                continue

            file_saved = genai.get_file(name=conversation_file.name)
            response = detect_people(file_saved)

            result_queue.put((conversation_file.uri, file_saved.uri, response))

            conversation_file_uri, file_saved_uri, response = result_queue.get()

            os.remove(file_path)
            logging.info(f"Deleted local file: {file_path}")

            return file_saved, conversation_file_uri, file_saved_uri, response

        except Exception as e:
            logging.error(f"Error during upload attempt {attempt + 1}: {e}")

    raise Exception("Both upload attempts failed.")
