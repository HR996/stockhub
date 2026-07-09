from app.adapters.tushare_adapter import tushare_session
from app.core.db import session_scope
from app.repositories.sw_repo import SWClassifyRepo, SWMemberRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.services.sw_sync_service import sync_sw_industry
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def run_sw_sync():
    with tushare_session() as pro:
        with session_scope() as db:
            result = sync_sw_industry(
                pro=pro,
                classify_repo=SWClassifyRepo(db),
                member_repo=SWMemberRepo(db),
                task_repo=TaskLogRepo(db),
                triggered_by="manual",
            )
            logger.info(f"SW sync result: {result}")
            return result

if __name__ == "__main__":
    logger.info("Starting SW sync...")
    result = run_sw_sync()
    if result.status == "SUCCESS":
        logger.info("SW sync completed successfully.")
    else:
        logger.error(f"SW sync failed: {result.error_message}")
        sys.exit(1)
