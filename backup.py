import requests
import json
import os
import argparse
import webbrowser
from datetime import datetime
import sys
import shutil
import subprocess
import tempfile
import uuid

CONFIG_FILE = "config.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)


def send_discord(cfg, msg, status="info"):
    # always print to CLI so user sees progress locally
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[Backup {status.upper()}] {timestamp} - {msg}"
    print(formatted)

    url = cfg.get("discord_webhook", "").strip()
    if not url:
        return
    # also send to Discord using embed
    # choose embed color based on status
    colors = {
        "info": 0x3498db,    # blue
        "success": 0x2ecc71, # green
        "failure": 0xe74c3c, # red
    }
    color = colors.get(status, colors["info"])

    payload = {
        "embeds": [
            {
                "description": f":floppy_disk: **Backup** `{timestamp}` - {msg}",
                "color": color,
            }
        ]
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass


class GoogleDriveUploader:
    SCOPES = "https://www.googleapis.com/auth/drive"

    def __init__(self):
        self.config = self.load_or_create_config()
        self.access_token = None

    def load_or_create_config(self):
        cfg = load_config()
        if cfg:
            print("[*] Loading existing config")
            return cfg

        print("[*] First time setup")
        parser = argparse.ArgumentParser()
        parser.add_argument("--client-id", required=True)
        parser.add_argument("--client-secret", required=True)
        parser.add_argument("--folder-id", required=True)
        parser.add_argument("--max-files", type=int, default=3)
        parser.add_argument("--local-dir", required=True)
        parser.add_argument("--db-host", required=True)
        parser.add_argument("--db-user", required=True)
        parser.add_argument("--db-pass", required=True)
        parser.add_argument("--db-name", required=True)
        parser.add_argument("--discord-webhook", default="")
        args = parser.parse_args()

        cfg = {
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "folder_id": args.folder_id,
            "max_files": args.max_files,
            "local_dir": args.local_dir,
            "db_host": args.db_host,
            "db_user": args.db_user,
            "db_pass": args.db_pass,
            "db_name": args.db_name,
            "discord_webhook": args.discord_webhook,
            "refresh_token": ""
        }

        save_config(cfg)
        print("[+] Config saved")
        send_discord(cfg, "config initialized", "success")
        return cfg

    def save(self):
        save_config(self.config)

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
            send_discord(self.config, "auth exchange failed", "failure")
            sys.exit(1)
        return r.json()

    def ensure_refresh_token(self):
        if self.config.get("refresh_token"):
            return self.config["refresh_token"]

        url = self.generate_auth_url()
        print(url)
        webbrowser.open(url)
        auth_code = input("Authorization code: ").strip()
        tokens = self.exchange_code(auth_code)

        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            send_discord(self.config, "no refresh token", "failure")
            sys.exit(1)

        self.config["refresh_token"] = refresh_token
        self.save()
        send_discord(self.config, "refresh token stored", "success")
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
            send_discord(self.config, "access token failed", "failure")
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
            send_discord(self.config, "list files failed", "failure")
            sys.exit(1)

        return r.json().get("files", [])

    def delete_file(self, file_id):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        r = requests.delete(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=headers,
        )
        if r.status_code != 204:
            send_discord(self.config, "delete remote failed " + file_id, "failure")
            sys.exit(1)
        send_discord(self.config, "deleted remote " + file_id, "success")

    def rotate_files(self):
        files = self.list_files()
        if len(files) >= self.config["max_files"]:
            self.delete_file(files[0]["id"])

    def rotate_local(self):
        local_dir = self.config["local_dir"]
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
        files = sorted(os.listdir(local_dir), key=lambda x: os.path.getctime(os.path.join(local_dir, x)))
        while len(files) >= self.config["max_files"]:
            os.remove(os.path.join(local_dir, files[0]))
            send_discord(self.config, "deleted local " + files[0], "success")
            files.pop(0)

    def save_local(self, file_path):
        local_dir = self.config["local_dir"]
        _, ext = os.path.splitext(file_path)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        new_filename = f"{timestamp}{ext}"
        dest_path = os.path.join(local_dir, new_filename)
        shutil.copy2(file_path, dest_path)
        send_discord(self.config, "saved local " + new_filename, "success")

    def dump_mysql(self):
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.sql', delete=False) as temp_file:
            dump_path = temp_file.name
        cmd = [
            "mysqldump",
            "-h", self.config["db_host"],
            "-u", self.config["db_user"],
            f"-p{self.config['db_pass']}",
            self.config["db_name"]
        ]
        with open(dump_path, 'w') as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
        if result.returncode != 0:
            send_discord(self.config, "mysql dump failed", "failure")
            os.unlink(dump_path)
            sys.exit(1)
        send_discord(self.config, "mysql dump success", "success")
        return dump_path

    def check_sql_integrity(self, dump_path):
        temp_db = f"temp_check_{uuid.uuid4().hex[:8]}"
        host = self.config["db_host"]
        user = self.config["db_user"]
        passwd = self.config["db_pass"]

        create_cmd = ["mysql", "-h", host, "-u", user, f"-p{passwd}", "-e", f"CREATE DATABASE {temp_db};"]
        result = subprocess.run(create_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            send_discord(self.config, "temp db create failed", "failure")
            return

        import_cmd = ["mysql", "-h", host, "-u", user, f"-p{passwd}", temp_db]
        with open(dump_path, 'r') as f:
            result = subprocess.run(import_cmd, stdin=f, capture_output=True, text=True)
        if result.returncode != 0:
            send_discord(self.config, "sql integrity failed", "failure")
            sys.exit(1)
        else:
            send_discord(self.config, "sql integrity ok", "success")

        drop_cmd = ["mysql", "-h", host, "-u", user, f"-p{passwd}", "-e", f"DROP DATABASE {temp_db};"]
        subprocess.run(drop_cmd)

    def upload_file(self, file_path):
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
            send_discord(self.config, "upload failed", "failure")
            sys.exit(1)

        send_discord(self.config, "upload success " + new_filename, "success")

    def run(self):
        send_discord(self.config, "backup job started", "info")
        self.ensure_refresh_token()
        dump_path = self.dump_mysql()
        self.check_sql_integrity(dump_path)
        self.rotate_local()
        self.save_local(dump_path)
        self.access_token = self.get_access_token()
        self.rotate_files()
        self.upload_file(dump_path)
        os.unlink(dump_path)
        send_discord(self.config, "backup pipeline success", "success")


if __name__ == "__main__":
    uploader = GoogleDriveUploader()
    uploader.run()
