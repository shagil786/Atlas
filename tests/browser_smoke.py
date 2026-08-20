from pathlib import Path
import tempfile
import uuid

from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:8000"
FIXTURE = Path(__file__).parents[1] / "data/sample_documents/w2_2025_rohan_patel_harbor_finance.pdf"


def run():
    results = []
    review_fixture = Path(tempfile.gettempdir()) / f"atlas-browser-unreadable-{uuid.uuid4().hex}.pdf"
    review_fixture.write_bytes(b"browser smoke unreadable fixture " + uuid.uuid4().bytes)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for viewport in [{"width": 1280, "height": 900}, {"width": 375, "height": 812}]:
            page = browser.new_page(viewport=viewport)
            console_errors = []
            request_failures = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("requestfailed", lambda request: request_failures.append(request.url))
            page.goto(f"{BASE_URL}/login", wait_until="networkidle")
            assert page.get_by_role("heading", name="Document collection workspace").is_visible()
            page.get_by_label("Username").fill("accountant")
            page.get_by_label("Password").fill("accountant-demo")
            page.get_by_role("button", name="Sign in").click()
            page.wait_for_url(f"{BASE_URL}/client")
            assert page.get_by_role("heading", name="Patel household").is_visible()
            assert page.get_by_text("Required documents").is_visible()
            assert page.get_by_role("link", name="Needs review").is_visible()
            with page.expect_navigation(wait_until="networkidle"):
                page.locator("input[type=file]").set_input_files(str(FIXTURE))
            assert page.get_by_text("Document uploaded").is_visible() or page.get_by_text("Duplicate document detected").is_visible()
            if viewport["width"] == 1280:
                with page.expect_navigation(wait_until="networkidle"):
                    page.locator("input[type=file]").set_input_files(str(review_fixture))
                page.goto(f"{BASE_URL}/client/review", wait_until="networkidle")
                assert page.get_by_role("button", name="Approve").is_visible()
                page.get_by_role("button", name="Sign out").click()
                page.wait_for_url(f"{BASE_URL}/login")
                page.get_by_label("Username").fill("reviewer")
                page.get_by_label("Password").fill("reviewer-demo")
                page.get_by_role("button", name="Sign in").click()
                page.wait_for_url(f"{BASE_URL}/client")
                page.goto(f"{BASE_URL}/client/review", wait_until="networkidle")
                assert page.get_by_role("heading", name="Resolve attention items").is_visible()
                page.get_by_role("button", name="Approve").first.click()
                page.wait_for_url(lambda url: "/client/review?message=" in url)
                assert page.get_by_text("Review decision saved").is_visible()
            page.keyboard.press("Tab")
            assert page.locator(":focus").count() == 1
            results.append({"viewport": viewport, "console_errors": console_errors, "request_failures": request_failures, "body_width": page.locator("body").evaluate("el => el.scrollWidth"), "viewport_width": viewport["width"]})
            page.close()
        browser.close()
    review_fixture.unlink(missing_ok=True)
    for result in results:
        assert result["console_errors"] == [], result
        assert result["request_failures"] == [], result
        assert result["body_width"] <= result["viewport_width"], result
    print(results)


if __name__ == "__main__":
    run()
