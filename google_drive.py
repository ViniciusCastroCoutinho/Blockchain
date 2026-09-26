"""
Code from https://gist.github.com/prasathmani/5d78a6126c3e1920ffb6fd591a759edb
"""
import json
import os
import requests

from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, "credentials.env")

load_dotenv(ENV_FILE)

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
FOLDER_ID = os.getenv("FOLDER_ID")

TOKEN_URL = "https://oauth2.googleapis.com/token"

UPLOAD_URL = (
    "https://www.googleapis.com/upload/drive/v3/files"
    "?uploadType=multipart"
    "&fields=id,name,webViewLink"
)


# ============================================================
# Get a new access token using the refresh token
# ============================================================

def get_access_token():
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }

    response = requests.post(TOKEN_URL, data=data)

    if response.status_code != 200:
        raise Exception(
            f"Failed to get access token: {response.text}"
        )

    token_data = response.json()

    access_token = token_data.get("access_token")

    if not access_token:
        raise Exception(
            f"No access token returned: {token_data}"
        )

    return access_token


# ============================================================
# Upload file to Google Drive
# ============================================================

def upload_to_drive(access_token, file_path, folder_id):

    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"Backup file does not exist: {file_path}"
        )

    file_name = os.path.basename(file_path)

    metadata = {
        "name": file_name,
        "parents": [folder_id],
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    # Keep the file open while requests.post() is running.
    # This fixes the "read of closed file" error from the original Gist.
    with open(file_path, "rb") as backup_file:

        files = {
            "data": (
                "metadata",
                json.dumps(metadata),
                "application/json; charset=UTF-8",
            ),
            "file": (
                file_name,
                backup_file,
                "application/pdf",
            ),
        }

        response = requests.post(
            UPLOAD_URL,
            headers=headers,
            files=files,
            timeout=3600,
        )

    if response.status_code not in (200, 201):
        raise Exception(
            f"Google Drive upload failed "
            f"(HTTP {response.status_code}):\n"
            f"{response.text}"
        )

    result = response.json()

    print("Upload successful!")
    print(f"File name: {result.get('name')}")
    print(f"Google Drive file ID: {result.get('id')}")
    print(f"Google Drive link: {result.get('webViewLink')}")

    return result.get("webViewLink")


# ============================================================
# Main
# ============================================================

def upload(filepath):
    print("Starting upload...")
    try:
        print("Getting Google access token...")
        access_token = get_access_token()

        print(f"Uploading: {filepath}")

        file_link =upload_to_drive(
            access_token,
            filepath,
            FOLDER_ID,
        )

        print("Upload completed.")

        os.remove(filepath)

        return file_link
    except Exception as e:
        print(f"Error: {e}")
        raise e
