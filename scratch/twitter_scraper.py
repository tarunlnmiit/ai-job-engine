import asyncio
import json
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def scrape_twitter_tweets(username, limit=50):
    # Ensure data directory exists
    data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(data_dir, exist_ok=True)
    output_file = os.path.join(data_dir, f"twitter_{username}_tweets.json")
    
    # Load existing tweets for delta scraping
    existing_tweets = []
    seen_tweet_ids = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                existing_tweets = json.load(f)
                seen_tweet_ids = {t["id"] for t in existing_tweets}
            print(f"STATUS: Loaded {len(existing_tweets)} existing tweets from {output_file}")
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
            user_data_dir = os.path.join(os.getcwd(), "twitter_user_data")
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
        
        print(f"STATUS: Navigating to Twitter/X profile: {username}")
        await page.goto(f"https://x.com/{username}")
        
        # Wait for either tweets or login wall
        try:
            await page.wait_for_selector('[data-testid="tweet"]', timeout=30000)
        except:
            print("STATUS: Profile not loading or login required. Please check the browser window.")
            # If not logged in, we might need to navigate to login first
            if "login" in page.url or await page.query_selector('a[href="/login"]'):
                print("STATUS: Redirecting to login...")
                await page.goto("https://x.com/login")
                print("STATUS: PLEASE LOG IN MANUALLY IN THE BROWSER WINDOW.")
                await page.wait_for_selector('[data-testid="tweet"]', timeout=120000)

        tweets_data = []
        print(f"STATUS: Starting incremental scrape for @{username}...")
        
        consecutive_no_new_tweets = 0
        max_consecutive = 8
        found_existing_delta = False
        
        while consecutive_no_new_tweets < max_consecutive and not found_existing_delta:
            # Scroll a bit
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(2.5)
            
            tweet_elements = await page.query_selector_all('[data-testid="tweet"]')
            initial_count = len(tweets_data)
            
            for tweet in tweet_elements:
                try:
                    link_element = await tweet.query_selector('a[href*="/status/"]')
                    if not link_element: continue
                    
                    tweet_url = await link_element.get_attribute("href")
                    tweet_id = tweet_url.split("/")[-1]
                    
                    # DELTA CHECK: If we see a tweet we've already exported, we stop (assuming timeline is chronological)
                    if tweet_id in seen_tweet_ids:
                        print(f"STATUS: Encountered existing tweet {tweet_id}. Delta reached!")
                        found_existing_delta = True
                        break
                    
                    if any(t["id"] == tweet_id for t in tweets_data):
                        continue
                    
                    # Extract Content
                    content_element = await tweet.query_selector('[data-testid="tweetText"]')
                    content = await content_element.inner_text() if content_element else ""
                    
                    # Extract Images
                    images = []
                    image_elements = await tweet.query_selector_all('[data-testid="tweetPhoto"] img')
                    for img in image_elements:
                        src = await img.get_attribute("src")
                        if src: images.append(src)
                    
                    # Extract Analytics
                    analytics = {"replies": "0", "retweets": "0", "likes": "0", "views": "0"}
                    for key in ["reply", "retweet", "like"]:
                        btn = await tweet.query_selector(f'[data-testid="{key}"]')
                        if btn:
                            val = await btn.get_attribute("aria-label")
                            analytics[f"{key}s"] = val.split()[0] if val else "0"

                    views_element = await tweet.query_selector('a[href*="/analytics"]')
                    if views_element:
                        val = await views_element.get_attribute("aria-label")
                        analytics["views"] = val.split()[0] if val else "0"

                    tweets_data.append({
                        "id": tweet_id,
                        "url": f"https://x.com{tweet_url}",
                        "content": content,
                        "images": images,
                        "analytics": analytics,
                        "scraped_at": datetime.now().isoformat()
                    })
                    
                    if len(tweets_data) % 5 == 0:
                        print(f"PROGRESS: Scraped {len(tweets_data)} new tweets...")
                        
                except: continue

            if len(tweets_data) == initial_count:
                consecutive_no_new_tweets += 1
            else:
                consecutive_no_new_tweets = 0
            
            if len(tweets_data) >= limit:
                print(f"STATUS: Reached limit of {limit} tweets.")
                break

        # Merge and Save
        print(f"STATUS: Merging {len(tweets_data)} new tweets with {len(existing_tweets)} existing ones...")
        all_tweets = tweets_data + existing_tweets
        
        # Final deduplication by ID
        unique_tweets = []
        seen = set()
        for t in all_tweets:
            if t["id"] not in seen:
                unique_tweets.append(t)
                seen.add(t["id"])
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(unique_tweets, f, indent=4, ensure_ascii=False)
            
        print(f"STATUS: Successfully saved {len(unique_tweets)} total tweets to {output_file}")
        print("DONE")
        await context.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python twitter_scraper.py <username> [limit]")
    else:
        user = sys.argv[1]
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        asyncio.run(scrape_twitter_tweets(user, lim))
