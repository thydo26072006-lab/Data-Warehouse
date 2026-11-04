"""Optional real-browser smoke test; requires playwright and installed Microsoft Edge."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "results/dashboard"
OUTPUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=True)
    page = browser.new_page(viewport={"width": 1536, "height": 1050}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8501", wait_until="domcontentloaded")
    page.get_by_text("12.642.905", exact=True).wait_for(timeout=45000)
    page.get_by_text("-9,39%", exact=True).wait_for(timeout=45000)
    page.locator("canvas:visible, svg.marks").first.wait_for(timeout=30000)
    page.get_by_text("Xem bảng dữ liệu", exact=True).wait_for(timeout=30000)
    page.evaluate("document.fonts.ready")
    page.screenshot(path=str(OUTPUT / "overview.png"), full_page=True)
    visited = ["Tổng quan"]
    for name in ["Sản phẩm & thị trường", "Khách hàng & đơn hàng", "Khám phá OLAP", "Dự báo doanh thu"]:
        page.get_by_text(name, exact=True).first.click()
        page.get_by_role("heading", name=name, exact=True).wait_for(timeout=30000)
        if name == "Dự báo doanh thu":
            page.get_by_text("352.375,83", exact=True).wait_for(timeout=30000)
            page.locator("canvas:visible, svg.marks").first.wait_for(timeout=30000)
            page.get_by_text("Mô hình được xây dựng và đánh giá thế nào?", exact=True).wait_for(timeout=30000)
            page.get_by_text("Phạm vi phân tích", exact=True).wait_for(state="hidden", timeout=30000)
            page.screenshot(path=str(OUTPUT / "forecast.png"), full_page=True)
        else:
            # Wait for the page to finish beyond its initial heading.
            page.get_by_test_id("stDataFrame").first.wait_for(timeout=30000) if name == "Khám phá OLAP" else page.locator("canvas:visible, svg.marks").first.wait_for(timeout=30000)
        visited.append(name)
    assert not errors, errors
    (OUTPUT / "browser_checks.json").write_text(json.dumps({
        "status": "passed", "pages_visited": visited, "javascript_errors": errors,
        "server": "http://127.0.0.1:8501", "browser": "Microsoft Edge headless"}, ensure_ascii=False, indent=2), encoding="utf-8")
    browser.close()
    print("Browser smoke test passed; screenshots saved in results/dashboard")
