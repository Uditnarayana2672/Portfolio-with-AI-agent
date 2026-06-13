import sys
import getpass
import urllib.request
import urllib.error
import json
import subprocess

SUPABASE_URL = "https://waddmljfjyushobocukr.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_4TLpZHmrXssF4--ZjtGKuQ_85QuOI-0"


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["clip"], input=text.encode(), check=True)


def get_token(email: str, password: str) -> str:
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    payload = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_ANON_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data["access_token"]
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        msg = body.get("error_description") or body.get("msg") or body.get("error") or str(e)
        print(f"Auth failed: {msg}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    print("=== Supabase Auth Token ===")
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    token = get_token(email, password)
    copy_to_clipboard(token)
    print(f"\nToken copied to clipboard.")
    print(f"Preview: {token[:40]}...")


if __name__ == "__main__":
    main()
