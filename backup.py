import requests
import json
import os
import argparse
import webbrowser
from datetime import datetime
import sys

CONFIG_FILE = "google_api.json"


class GoogleDriveUploader:
    SCOPES = "https://www.googleapis.com/auth/drive"

    def __init__(self):
        self.config = self.load_or_create_config()
        self.access_token = None

    def load_or_create_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                print("[*] Loading existing config")
                return json.load(f)

        print("[*] First time setup")

        parser = argparse.ArgumentParser()
        parser.add_argument("--client-id", required=True)
        parser.add_argument("--client-secret", required=True)
        parser.add_argument("--folder-id", required=True)
        parser.add_argument("--max-files", type=int, default=3)

        args = parser.parse_args()

        config = {
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "folder_id": args.folder_id,
            "max_files": args.max_files,
            "refresh_token": ""
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)

        print("[+] Config saved to google_api.json")
        return config

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)

    def generate_auth_url(self):
        return (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={self.config['client_id']}"
            f"&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
            f"&response_type=code"
            f"&scope={self.SCOPES}"
            f"&access_type=offline"
            f"&prompt=consent"
        )

    def exchange_code(self, auth_code):
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": auth_code,
                "client_id": self.config["client_id"],
                "client_secret": self.config["client_secret"],
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "grant_type": "authorization_code",
            },
        )
        if r.status_code != 200:
            print("[-] Failed to exchange authorization code")
            sys.exit(1)
        return r.json()

    def ensure_refresh_token(self):
        if self.config.get("refresh_token"):
            return self.config["refresh_token"]

        print("[*] No refresh token found")
        url = self.generate_auth_url()
        print("[*] Open this URL in browser:")
        print(url)
        webbrowser.open(url)

        auth_code = input("Authorization code: ").strip()
        tokens = self.exchange_code(auth_code)

        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            print("[-] No refresh token received")
            sys.exit(1)

        self.config["refresh_token"] = refresh_token
        self.save_config()
        print("[+] Refresh token saved")
        return refresh_token

    def get_access_token(self):
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self.config["client_id"],
                "client_secret": self.config["client_secret"],
                "refresh_token": self.config["refresh_token"],
                "grant_type": "refresh_token",
            },
        )
        if r.status_code != 200:
            print("[-] Failed to obtain access token")
            sys.exit(1)
        return r.json()["access_token"]

    def list_files(self):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        query = f"'{self.config['folder_id']}' in parents and trashed=false"

        params = {
            "q": query,
            "orderBy": "createdTime asc",
            "fields": "files(id,name)",
            "pageSize": self.config["max_files"],
        }

        r = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            headers=headers,
            params=params,
        )

        if r.status_code != 200:
            print("[-] Failed to list files")
            sys.exit(1)

        return r.json().get("files", [])

    def delete_file(self, file_id):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        r = requests.delete(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=headers,
        )
        if r.status_code != 204:
            print("[-] Failed to delete file:", file_id)
            sys.exit(1)
        print("[+] Deleted:", file_id)

    def rotate_files(self):
        files = self.list_files()
        if len(files) >= self.config["max_files"]:
            self.delete_file(files[0]["id"])

    def upload_file(self, file_path):
        if not os.path.exists(file_path):
            print("[-] File not found:", file_path)
            sys.exit(1)

        headers = {"Authorization": f"Bearer {self.access_token}"}

        _, ext = os.path.splitext(file_path)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        new_filename = f"{timestamp}{ext}"

        metadata = {
            "name": new_filename,
            "parents": [self.config["folder_id"]],
        }

        with open(file_path, "rb") as f:
            files = {
                "data": (
                    "metadata",
                    json.dumps(metadata),
                    "application/json; charset=UTF-8",
                ),
                "file": f,
            }

            r = requests.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                headers=headers,
                files=files,
            )

        if r.status_code != 200:
            print("[-] Upload failed")
            sys.exit(1)

        print("[+] Upload success:", new_filename)

    def run(self, file_path):
        self.ensure_refresh_token()
        self.access_token = self.get_access_token()
        self.rotate_files()
        self.upload_file(file_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args, unknown = parser.parse_known_args()

    uploader = GoogleDriveUploader()
    uploader.run(args.file)
