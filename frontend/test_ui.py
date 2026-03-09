import asyncio
from playwright.async_api import async_playwright
import os

async def run_test():
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await browser.new_page()
        
        url = "http://localhost:7860"
        print(f"Navigating to {url}...")
        
        try:
            # Wait for the page to load
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Wait for the main title to appear to ensure Gradio is rendered
            await page.wait_for_selector("h1", timeout=10000)
            
            # Take a screenshot of the full dashboard
            screenshot_path = os.path.join(os.getcwd(), "frontend_dashboard.png")
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot saved to {screenshot_path}")
            
            # Verify status message
            status_text = await page.inner_text("div.prose >> p") # Adjust selector based on actual render
            print(f"UI Content preview: {status_text[:100]}...")
            
        except Exception as e:
            print(f"Error during UI test: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_test())
