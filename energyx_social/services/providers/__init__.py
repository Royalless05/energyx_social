from energyx_social.services.providers.meta import MetaProvider
from energyx_social.services.providers.tiktok import TikTokProvider
from energyx_social.services.providers.youtube import YouTubeProvider

PROVIDERS = {
    "Instagram": MetaProvider,
    "Facebook Page": MetaProvider,
    "YouTube": YouTubeProvider,
    "TikTok": TikTokProvider,
}


def get_provider(account):
    return PROVIDERS[account.channel](account)
