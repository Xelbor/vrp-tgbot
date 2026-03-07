from app.users.db.repositories import UserRepository, SubscriptionRepository
import app.common.utils as utils
from datetime import datetime
from logger import get_logger
log = get_logger(__name__)

class referral_service:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def parse_ref(self, message: str):
        args = message.split()
        ref_code = args[1] if len(args) > 1 else None
        log.info("parse_ref message=%s ref_code=%s", message, ref_code)
        return ref_code

    def registered_by_referral(self, user_id: int, ref_code: str | None):
        log.info(
            "registered_by_referral user_id=%s ref_code=%s",
            user_id, ref_code
        )
    
        self.user_repo.create_user_if_not_exists(user_id)
    
        if ref_code and ref_code.startswith("ref_"):
            code = ref_code.replace("ref_", "")
            ref_owner = self.user_repo.get_user_by_reffer_code(code)

            if ref_owner and ref_owner[0] != user_id:
                new_code = utils.generate_username(6)
                self.user_repo.set_referrer(user_id, new_code)
                if self.user_repo.set_referrer_on_user(user_id, ref_owner[0]) == 1:
                    log.info("Referral success: inviter=%s invited=%s", ref_owner[0], user_id)

    def register_refferal(self, user_id: int, ref_code: str | None):
        row = self.user_repo.get_referrer_code_by_user(user_id)
        if not row:
            return None
        
        ref_code = row[0]
        if ref_code is None:
            ref_code = utils.generate_username(6)
            self.user_repo.set_referrer(user_id, ref_code)
            self.user_repo.set_referrer_on_user(user_id, ref_code)

        link = f"{utils.BOT_LINK}?start=ref_{ref_code}"
        return link

class subscription_service:
    def __init__(self, sub_repo: SubscriptionRepository):
        self.sub_repo = sub_repo

    async def buy_subscription(self, user_id: int, days: int):
        active_paid = self.sub_repo.get_active_paid(user_id)

        if active_paid:
            link = active_paid[0]
            await utils.expand_subscribe_link(user_id, link, days)

            return link
        
        #active_trial = self.sub_repo.get_active_trial(user_id)
        #total_days = days

        #if active_trial:
        #    trial_id, trial_end = active_trial

        #    remaining_days = 0
        #    if trial_end > datetime.now():
        #        remaining_days = (trial_end - datetime.now()).days

        #    total_days += remaining_days
        #    
        #    await utils.expand_subscribe_link(user_id, total_days)
        #    self.sub_repo.extend_subscription(user_id, days)
        #    self.sub_repo.change_type_sub_link(user_id)

        #    subs = self.sub_repo.get_active_subscriptions(user_id)
        #    vpn_keys = [sub[0] for sub in subs]
        #    return vpn_keys[0]

        subscribe_link = await utils.create_a_subscribe_link(user_id, days)
        
        if (subscribe_link):
            sub = await self.sub_repo.add_subscription(user_id, 'paid', subscribe_link, days)
            if sub:
                return subscribe_link

    async def give_trial(self, user_id: int, days: int):
        subscribe_link = await utils.create_a_subscribe_link(user_id, days, "trial")
        
        if isinstance(subscribe_link, str):
            sub = await self.sub_repo.add_subscription(user_id, 'trial', subscribe_link, days)
            if sub != False:
                return subscribe_link
        else:
            log.error(f"Failed to create link for {user_id}. Got: {subscribe_link}")
            return None
        
    async def sync_subscriptions(self, user_id: int):
        remote_links = await utils.get_user_links(str(user_id))

        if remote_links is None:
            return

        db_subscriptions = self.sub_repo.get_active_subscriptions(user_id)

        if not db_subscriptions:
            return

        for sub in db_subscriptions:
            db_link = sub[0]

            if db_link not in remote_links:
                self.sub_repo.delete_sub_link(db_link)