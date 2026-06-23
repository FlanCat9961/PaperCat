from __future__ import annotations

import builtins

from papercat.core.subscription import Subscription, SubscriptionStore


class SubscriptionController:
    def __init__(self, store: SubscriptionStore) -> None:
        self.store = store

    def list(self, enabled_only: bool = False) -> builtins.list[Subscription]:
        return self.store.list(enabled_only=enabled_only)

    def create(self, subscription: Subscription) -> Subscription:
        return self.store.create(subscription)

    def update(self, subscription: Subscription) -> Subscription:
        return self.store.update(subscription)

    def delete(self, subscription_id: int) -> None:
        self.store.delete(subscription_id)

    def set_enabled(self, subscription_id: int, flag: bool) -> None:
        self.store.set_enabled(subscription_id, flag)

    def reorder(self, ordered_ids: builtins.list[int]) -> None:
        self.store.reorder(ordered_ids)
