import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

async def scrape_chatgpt_chats():
    # Ensure data directory exists
    data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(data_dir, exist_ok=True)
    output_file = os.path.join(data_dir, "chatgpt_history_export.json")
    
    # Load existing chats for delta scraping
    existing_chats = []
    seen_chat_urls = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                existing_chats = json.load(f)
                seen_chat_urls = {c["url"] for c in existing_chats}
            print(f"STATUS: Loaded {len(existing_chats)} existing chats from {output_file}")
        except Exception as e:
            print(f"STATUS: Error loading existing file: {e}")

    async with async_playwright() as p:
        # Check if we can connect to an existing Chrome instance
        page = None
        cdp_url = "http://127.0.0.1:9222"
        try:
            print(f"STATUS: Connecting to Chrome via CDP at {cdp_url}...")
            browser = await p.chromium.connect_over_cdp(cdp_url)
            if len(browser.contexts) > 0:
                context = browser.contexts[0]
            else:
                context = await browser.new_context()
            page = await context.new_page()
            print("STATUS: Connected to existing Chrome instance!")
        except Exception as e:
            print(f"STATUS: CDP connection failed: {e}")
            print(f"STATUS: Falling back to launching new persistent instance...")
            user_data_dir = os.path.join(os.getcwd(), "chatgpt_user_data")
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                    ignore_default_args=["--enable-automation"]
                )
                page = context.pages[0] if context.pages else await context.new_page()
            except Exception as e2:
                print(f"STATUS: FATAL ERROR: Could not launch browser: {e2}")
                return
        
        if not page:
            print("STATUS: FATAL ERROR: Page object was not created.")
            return
        
        base_url = "https://chatgpt.com"
        print("STATUS: Navigating to ChatGPT...")
        await page.goto(base_url)
        
        # Wait for login
        try:
            await page.wait_for_selector('nav', timeout=60000)
        except:
            print("STATUS: Login required. Please log in manually in the browser window.")
            await page.wait_for_selector('nav', timeout=120000)

        # 1. Collect Project Links
        print("STATUS: Checking for ChatGPT Projects...")
        await page.goto(f"{base_url}/projects")
        await asyncio.sleep(4)
        project_links_explicit = await page.query_selector_all('a[href^="/projects/"]')
        print(f"STATUS: Found {len(project_links_explicit)} Project links.")

        # 2. Collect Sidebar Links
        print("STATUS: Collecting sidebar chat history...")
        await page.goto(base_url)
        await asyncio.sleep(3)
        
        sidebar_selector = 'nav[aria-label="Chat history"]'
        sidebar = await page.query_selector(sidebar_selector) or await page.query_selector('nav')
        if sidebar:
            print("STATUS: Scrolling history to find new chats...")
            for _ in range(10): # Scroll history
                try:
                    await page.hover(sidebar_selector if await page.query_selector(sidebar_selector) else 'nav')
                    await page.mouse.wheel(0, 5000)
                    await asyncio.sleep(1)
                except: break

        chat_links_elements = await page.query_selector_all('nav a[href^="/c/"]')
        if not chat_links_elements:
            chat_links_elements = await page.query_selector_all('[data-testid^="history-item"]')
            
        all_link_elements = chat_links_elements + project_links_explicit
        
        # Extract unique URLs and titles
        target_links = []
        for el in all_link_elements:
            try:
                title = await el.inner_text()
                url = await el.get_attribute("href")
                if url and (url.startswith("/c/") or url.startswith("/projects/")):
                    full_url = f"{base_url}{url}"
                    # DELTA CHECK: Skip if already in export
                    if full_url in seen_chat_urls:
                        continue
                    target_links.append({"title": title.split("\n")[0], "url": full_url})
            except: continue
        
        # Deduplicate
        unique_targets = []
        seen = set()
        for t in target_links:
            if t["url"] not in seen:
                unique_targets.append(t)
                seen.add(t["url"])
                
        print(f"STATUS: Found {len(unique_targets)} NEW conversations/projects to scrape.")
        
        new_chats_data = []
        for i, target in enumerate(unique_targets):
            try:
                print(f"PROGRESS: Scraping {i+1}/{len(unique_targets)}: {target['title']}")
                
                # NAVIGATION UPGRADE: Instead of goto (which crashes the tab), try to CLICK the sidebar link
                # This is much safer and avoids 'Aw Snap' errors.
                chat_url = target["url"].replace(base_url, "")
                link_selector = f'nav a[href="{chat_url}"]'
                
                # Check if link is visible in sidebar, if not, then we might have to use goto as fallback
                link_element = await page.query_selector(link_selector)
                if link_element:
                    print(f"STATUS: Clicking sidebar link for {target['title']}...")
                    await link_element.click()
                else:
                    print(f"STATUS: Link not in sidebar, using direct navigation for {target['title']}...")
                    await page.goto(target["url"], wait_until="domcontentloaded")
                
                # Wait for content with a slightly longer timeout and check for crashes
                try:
                    await page.wait_for_selector('[data-testid^="conversation-turn-"]', timeout=20000)
                except Exception as e:
                    # Check if the page is still responsive
                    if page.is_closed():
                        print("STATUS: Tab crashed or closed! Attempting to recover...")
                        page = await context.new_page()
                        await page.goto(base_url)
                        continue
                    print(f"STATUS: Content didn't load for {target['title']}, skipping...")
                    continue
                
                turns = await page.query_selector_all('[data-testid^="conversation-turn-"]')
                messages = []
                for turn in turns:
                    content_element = await turn.query_selector('.markdown, .prose, [data-message-author-role]')
                    content = await content_element.inner_text() if content_element else ""
                    role_attr = await turn.get_attribute("data-message-author-role")
                    if not role_attr:
                        role = "user" if await turn.query_selector('[data-testid="user-message"]') else "assistant"
                    else:
                        role = role_attr
                    messages.append({"role": role, "content": content.strip()})
                
                new_chats_data.append({
                    "title": target["title"],
                    "url": target["url"],
                    "date_scraped": datetime.now().isoformat(),
                    "messages": messages
                })
            except Exception as e:
                print(f"STATUS: Error scraping {target['title']}: {e}")

        # Merge and Save
        if new_chats_data:
            print(f"STATUS: Merging {len(new_chats_data)} new chats with {len(existing_chats)} existing ones...")
            all_chats = new_chats_data + existing_chats
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(all_chats, f, indent=4, ensure_ascii=False)
            print(f"STATUS: Successfully saved {len(all_chats)} total chats to {output_file}")
        else:
            print("STATUS: No new chats found to scrape.")
            
        print("DONE")
        await context.close()

if __name__ == "__main__":
    asyncio.run(scrape_chatgpt_chats())
