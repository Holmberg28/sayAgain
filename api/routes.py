import asyncio
import logging
import os
from html import escape

from flask import Blueprint, request, jsonify

from .__init__ import user_sessions
from .utils import (save_conversation_history, generate_secret_key,
                    convert_to_json, upload_and_detect,
                    run_handle_conversation, executor)

routes_blueprint = Blueprint('routes', __name__)


@routes_blueprint.route('/upload', methods=['POST'])
async def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:

        file_path = os.path.join("api/uploads", file.filename)
        file.save(file_path)

        loop = asyncio.get_event_loop()

        try:
            file_saved, conversation_file_uri, file_saved_uri, response = await loop.run_in_executor(
                executor, upload_and_detect, file_path
            )
        except FileNotFoundError as e:
            return jsonify({'error': 'File not found: ' + str(e)}), 400
        except Exception as e:
            logging.error(f"Error during upload and detection: {e}")
            return jsonify({'error': 'Error during upload and detection'}), 500

        logging.info(f"Uploaded file as: {conversation_file_uri}")
        logging.info(f"Retrieved file as: {file_saved_uri}")

        # Save the session ID
        session_id = generate_secret_key()
        user_sessions[session_id] = {
            'local_file_path': file_path,
            'file_name': file_saved_uri.split('/')[-1],  # Extract file name from URI
            'history': None
        }

        # Start a history
        history = [
            {"role": "user", "parts": ["👋", file_saved]},
            {"role": "model", "parts": ["👋"]},
        ]

        save_conversation_history(history, session_id, user_sessions)

        # Construct response dictionary
        json_response = {
            "People": response,
            "file_data": {"mime_type": "text/plain", "file_uri": file_saved_uri},
            "session_id": session_id,
        }

        return jsonify(json_response), 200


@routes_blueprint.route('/send_message', methods=['POST'])
async def start_conversation():
    data = request.json
    session_id = data.get('session_id')
    chat = escape(data.get('chat', ''))
    name = escape(data.get('name', ''))
    personality = escape(data.get('personality', ''))

    if not session_id or session_id not in user_sessions:
        logging.error("error: Invalid session")
        return jsonify({"error": "Invalid session"}), 400

    if not chat:
        logging.error("error: No message")
        return jsonify({"error": "No message"}), 400

    if not personality:
        personality = ""
    else:
        personality = "The description of this person is as described: " + personality

    loop = asyncio.get_event_loop()
    history = await loop.run_in_executor(
        executor, run_handle_conversation, chat, name, personality, session_id, user_sessions
    )

    send_data_to_frontend = {
        "history": convert_to_json(str(history)),
        "session_id": session_id,
    }

    return jsonify(send_data_to_frontend)


@routes_blueprint.route('/run_demo', methods=['POST'])
async def run_demo():
    file_path = "api/demo/demo.pdf"

    loop = asyncio.get_event_loop()

    try:
        file_saved, conversation_file_uri, file_saved_uri, response = await loop.run_in_executor(
            executor, upload_and_detect, file_path
        )
    except FileNotFoundError as e:
        return jsonify({'error': 'File not found: ' + str(e)}), 400
    except Exception as e:
        logging.error(f"Error during upload and detection: {e}")
        return jsonify({'error': 'Error during upload and detection'}), 500

    logging.info(f"Uploaded file as: {conversation_file_uri}")
    logging.info(f"Retrieved file as: {file_saved_uri}")

    # Save the session ID
    session_id = generate_secret_key()
    user_sessions[session_id] = {
        'local_file_path': file_path,
        'file_name': file_saved_uri.split('/')[-1],  # Extract file name from URI
        'history': None
    }

    # Start a history
    history = [
        {"role": "user", "parts": ["👋", file_saved]},
        {"role": "model", "parts": ["👋"]},
    ]

    save_conversation_history(history, session_id, user_sessions)

    # Construct response dictionary
    json_response = {
        "People": response,
        "file_data": {"mime_type": "text/plain", "file_uri": file_saved_uri},
        "session_id": session_id,
    }

    return jsonify(json_response), 200


@routes_blueprint.route('/stop', methods=['POST'])
async def stop():
    data = request.json
    session_id = data.get('session_id')

    if not session_id or session_id not in user_sessions:
        return jsonify({"error": "Invalid session"}), 400

    try:
        os.remove(user_sessions[session_id]['local_file_path'])
        logging.info(f"Deleted local file: {user_sessions[session_id]['local_file_path']}")
    except FileNotFoundError:
        logging.info(f"Local file not found: {user_sessions[session_id]['local_file_path']}")

    try:
        os.remove(user_sessions[session_id]['history'])
        logging.info(f"Deleted history file: {user_sessions[session_id]['history']}")
    except FileNotFoundError:
        logging.info(f"History file not found: {user_sessions[session_id]['history']}")

    del user_sessions[session_id]
    return jsonify({'status': 'success'})
