from .base import BaseJobScraper, Job
from .linkedin import LinkedInScraper
from .naukri import NaukriScraper
from .greenhouse import GreenhouseScraper
from .lever import LeverScraper
from .wellfound import WellfoundScraper
from .indeed import IndeedScraper
from .remotive import RemotiveScraper
from .weworkremotely import WeWorkRemotely
from .instahyre import InstahyreScraper
from .hacker_news import HackerNewsScraper
from .hirist import HiristScraper
from .relocateme import RelocateMeScraper
from .thehub import TheHubScraper
from .arbeitnow import ArbeitNowScraper

# Chrome DevTools variants (visible automation for debugging)
from .linkedin_devtools import LinkedInScraperDevTools, LinkedInScraperHybrid

__all__ = [
    "BaseJobScraper",
    "Job",
    "LinkedInScraper",
    "LinkedInScraperDevTools",
    "LinkedInScraperHybrid",
    "NaukriScraper",
    "GreenhouseScraper",
    "LeverScraper",
    "WellfoundScraper",
    "IndeedScraper",
    "RemotiveScraper",
    "WeWorkRemotely",
    "InstahyreScraper",
    "HackerNewsScraper",
    "HiristScraper",
    "RelocateMeScraper",
    "TheHubScraper",
    "ArbeitNowScraper",
]

# To use visible LinkedIn automation, uncomment:
# LinkedInScraper = LinkedInScraperHybrid  # Playwright with visible browser
