from frappe.model.document import Document


def compute_engagement_rate(likes=0, comments=0, shares=0, reach=0, impressions=0) -> float:
    """(likes + comments + shares) / reach x 100; fallback ke impressions bila reach kosong."""
    base = reach or impressions
    if not base:
        return 0.0
    return round(((likes or 0) + (comments or 0) + (shares or 0)) / base * 100, 2)


class SocialPostMetric(Document):
    def validate(self):
        self.engagement_rate = compute_engagement_rate(
            self.likes, self.comments, self.shares, self.reach, self.impressions
        )
