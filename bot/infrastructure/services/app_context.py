import asyncio
from typing import Optional, TYPE_CHECKING
from aiogram import Bot, Dispatcher
from infrastructure.services.localization_service import LocalizationService
from core.interfaces.repositories import IRepositoryFactory
from core.interfaces.services import (
    IEncryptionService,
    IStellarSealedBoxService,
    IStellarService,
    ITonService,
)
from infrastructure.factories.use_case_factory import IUseCaseFactory
from db.db_pool import DatabasePool

if TYPE_CHECKING:
    from infrastructure.services.notification_coordinator import NotificationCoordinator
    from infrastructure.services.notification_redis_store import NotificationRedisStore
    from infrastructure.services.notification_badge_service import (
        NotificationBadgeService,
    )
    from infrastructure.services.notification_history_service import (
        NotificationHistoryService,
    )
    from infrastructure.services.notification_service import NotificationService
    from infrastructure.services.bot_health_service import BotHealthService
    from infrastructure.workers.notification_delivery_worker import (
        NotificationDeliveryWorker,
    )
    from redis.asyncio import Redis


class AppContext:
    """
    Application-wide context container.
    Replaces GlobalData singleton for Dependency Injection.
    """

    def __init__(
        self,
        bot: Bot,
        db_pool: DatabasePool,
        admin_id: int,
        cheque_queue: asyncio.Queue,
        log_queue: asyncio.Queue,
        repository_factory: IRepositoryFactory,
        stellar_service: IStellarService,
        encryption_service: IEncryptionService,
        use_case_factory: IUseCaseFactory,
        ton_service: Optional["ITonService"] = None,
        localization_service: Optional[LocalizationService] = None,
        dispatcher: Optional[Dispatcher] = None,
        notification_service: Optional["NotificationService"] = None,
        notification_history: Optional["NotificationHistoryService"] = None,
        notification_coordinator: Optional["NotificationCoordinator"] = None,
        notification_redis: Optional["Redis"] = None,
        notification_store: Optional["NotificationRedisStore"] = None,
        notification_delivery_worker: Optional["NotificationDeliveryWorker"] = None,
        notification_badge_service: Optional["NotificationBadgeService"] = None,
        bot_health_service: Optional["BotHealthService"] = None,
        stellar_sealedbox_service: Optional[IStellarSealedBoxService] = None,
    ):
        self.bot = bot
        self.db_pool = db_pool
        self.admin_id = admin_id
        self.cheque_queue = cheque_queue
        self.log_queue = log_queue
        self.repository_factory = repository_factory
        self.stellar_service = stellar_service
        self.encryption_service = encryption_service
        self.use_case_factory = use_case_factory
        self.ton_service = ton_service
        self.localization_service = localization_service
        self.dispatcher = dispatcher
        self.notification_service = notification_service
        self.notification_history = notification_history
        self.notification_coordinator = notification_coordinator
        self.notification_redis = notification_redis
        self.notification_store = notification_store
        self.notification_delivery_worker = notification_delivery_worker
        self.notification_badge_service = notification_badge_service
        self.bot_health_service = bot_health_service
        self.stellar_sealedbox_service = stellar_sealedbox_service
