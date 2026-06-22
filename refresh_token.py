"""Refresh Google OAuth token locally and upload fresh token.json to EC2."""
import paramiko
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from pathlib import Path
import json

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
TOKEN_PATH = "config/token.json"
CREDS_PATH = "config/credentials.json"

creds = None
if Path(TOKEN_PATH).exists():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        print("Trying refresh...")
        try:
            creds.refresh(Request())
            print("Refreshed OK")
        except Exception as e:
            print(f"Refresh failed: {e}")
            creds = None

    if not creds:
        print("Need full re-auth — browser will open...")
        flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
        creds = flow.run_local_server(port=0)
        print("Auth complete")

    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"Token saved to {TOKEN_PATH}")
else:
    print("Token valid, no refresh needed")

# Upload fresh token to EC2
print("\nUploading to EC2...")
key_ec2 = paramiko.RSAKey.from_private_key_file('montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key_ec2, timeout=30)
sftp = ssh.open_sftp()
sftp.put(TOKEN_PATH, '/home/ubuntu/scraper/config/token.json')
sftp.close()
ssh.close()
print("Token uploaded to EC2 - done")
