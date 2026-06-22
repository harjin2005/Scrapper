from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file("config/token.json")
svc = build("sheets", "v4", credentials=creds)
meta = svc.spreadsheets().get(spreadsheetId="1PE534MXnwlRqQoiukX8fCvtwamiKnT4JaiRsbBOb3DM").execute()
for s in meta.get("sheets", []):
    p = s["properties"]
    print(f"  gid={p['sheetId']}  name={p['title']!r}")
