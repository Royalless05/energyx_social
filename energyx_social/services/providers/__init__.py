from energyx_social.services.providers.linkedin import LinkedInProvider
from energyx_social.services.providers.meta import MetaProvider
from energyx_social.services.providers.tiktok import TikTokProvider
from energyx_social.services.providers.youtube import YouTubeProvider

PROVIDERS = {
    "Instagram": MetaProvider,
    "Facebook Page": MetaProvider,
    "YouTube": YouTubeProvider,
    "TikTok": TikTokProvider,
    "LinkedIn": LinkedInProvider,
}


def get_provider(account):
    return PROVIDERS[account.channel](account)
