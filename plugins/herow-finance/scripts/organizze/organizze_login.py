#!/usr/bin/env python3
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import HOME, AUTH, chromium_executable_path

SESSION = HOME / ".session"

ORGANIZZE_URL = "https://app.organizze.com.br"


def load_email() -> str:
    if not AUTH.exists():
        print(f"err|credentials-missing|{AUTH} not found")
        sys.exit(1)
    for line in AUTH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "ORGANIZZE_EMAIL":
            return v.strip().strip('"').strip("'")
    print("err|credentials-missing|ORGANIZZE_EMAIL not found in .auth")
    sys.exit(1)


def load_password(email: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-a", email, "-s", "organizze-login", "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"err|credentials-missing|password not found in Keychain for {email}")
        sys.exit(1)
    pw = result.stdout.strip()
    if not pw:
        print(f"err|credentials-missing|empty password in Keychain for {email}")
        sys.exit(1)
    return pw


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("err|playwright-not-installed|run: pip3 install playwright && python3 -m playwright install chromium")
        sys.exit(1)

    email = load_email()
    password = load_password(email)

    with sync_playwright() as p:
        exe = chromium_executable_path()
        browser = p.chromium.launch(headless=True, **({"executable_path": exe} if exe else {}))
        context_kwargs: dict = {}
        if SESSION.exists():
            context_kwargs["storage_state"] = str(SESSION)

        ctx = browser.new_context(**context_kwargs)
        page = ctx.new_page()
        page.set_default_navigation_timeout(15000)

        page.goto(f"{ORGANIZZE_URL}/")
        page.wait_for_load_state("networkidle")

        if "/login" not in page.url:
            browser.close()
            print(f"ok|session-valid|{SESSION}")
            return

        # Fill login form (auth.organizze.com.br). The form has several submit
        # buttons (Google, Facebook, Entrar, …) — target "Entrar" by exact text,
        # otherwise the first submit (Google OAuth) is clicked instead.
        page.fill('input[type="email"], #form_email, input[name="form[email]"]', email)
        page.fill('input[type="password"], #form_password, input[name="form[password]"]', password)
        page.get_by_role("button", name="Entrar", exact=True).click()
        try:
            page.wait_for_url("**app.organizze.com.br/**", timeout=15000)
        except Exception:
            pass

        current_url = page.url

        if "/home" in current_url or "/login" not in current_url:
            ctx.storage_state(path=str(SESSION))
            os.chmod(SESSION, 0o600)
            browser.close()
            print(f"ok|session-saved|{SESSION}")
            return

        # Still on /login — check why
        body_text = page.inner_text("body")
        if "duas etapas" in body_text.lower() or "two-factor" in body_text.lower() or "código" in body_text.lower():
            browser.close()
            print("err|2fa-detected|2FA required")
            return

        browser.close()
        print("err|bad-credentials|login form rejected credentials")


if __name__ == "__main__":
    main()
