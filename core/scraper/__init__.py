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
from .uplers import UplersScraper
from .braintrust import BraintrustScraper
from .andela import AndelaScraper
from .arc_dev import ArcDevScraper
from .mercor import MercorScraper
from .turing import TuringScraper
from .workinluxembourg import WorkInLuxembourgScraper
# from .make_it_in_germany import MakeItInGermanyScraper
# from .work_in_denmark import WorkInDenmarkScraper
# from .eures import EURESScraper


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
    "UplersScraper",
    "BraintrustScraper",
    "AndelaScraper",
    "ArcDevScraper",
    "MercorScraper",
    "TuringScraper",
    "WorkInLuxembourgScraper",
    "MakeItInGermanyScraper",
    "WorkInDenmarkScraper",
    "EURESScraper",
]

# To use visible LinkedIn automation, uncomment:
# LinkedInScraper = LinkedInScraperHybrid  # Playwright with visible browser
