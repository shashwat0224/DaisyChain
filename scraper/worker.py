import time
import random
import logging
from playwright.sync_api import sync_playwright

from scraper import scrape_train, make_context
from db import save_train_data
from queue_manager import claim_next, mark_done, mark_failed, reset_to_pending

logger = logging.getLogger(__name__)


def run_worker(worker_id: int):
    """
    One worker = one browser instance.
    Pulls trains from shared SQLite queue until queue is empty.
    """
    logger.info(f"Worker {worker_id}: starting")

    with sync_playwright() as p:
        browser, context = make_context(p)
        page = context.new_page()
        consecutive_failures = 0

        while True:
            train_no = claim_next(worker_id)
            if not train_no:
                logger.info(f"Worker {worker_id}: queue empty, exiting")
                break

            logger.info(f"Worker {worker_id}: >> {train_no}")

            # Polite delay before every request
            time.sleep(random.uniform(6, 10))

            try:
                result = scrape_train(train_no, page)
            except Exception as e:
                logger.error(f"Worker {worker_id}: unhandled exception on {train_no}: {e}")
                result = None

            # ── Route result to correct handler ──────────────────────────────

            if isinstance(result, dict):
                # Success path
                try:
                    save_train_data(result)
                    mark_done(train_no)
                    consecutive_failures = 0
                    logger.info(
                        f"Worker {worker_id}: [OK] {train_no} "
                        f"({result['train_name']}, {len(result['stops'])} stops)"
                    )
                except Exception as e:
                    logger.error(f"Worker {worker_id}: DB save failed for {train_no}: {e}")
                    mark_failed(train_no, f"db_error: {str(e)[:200]}")

            elif result == "MOBILE":
                # Don't count as failure — just reset context and retry
                logger.warning(f"Worker {worker_id}: mobile layout on {train_no}, resetting context")
                reset_to_pending(train_no)
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass
                time.sleep(random.uniform(5, 10))
                browser, context = make_context(p)
                page = context.new_page()

            elif result == "BLOCKED":
                consecutive_failures += 1
                mark_failed(train_no, "blocked_or_redirected")
                logger.warning(
                    f"Worker {worker_id}: blocked on {train_no} "
                    f"(streak: {consecutive_failures})"
                )
                if consecutive_failures >= 3:
                    logger.warning(f"Worker {worker_id}: 3 consecutive blocks — restarting browser")
                    try:
                        context.close()
                        browser.close()
                    except Exception:
                        pass
                    time.sleep(random.uniform(20, 40))  # longer cooldown
                    browser, context = make_context(p)
                    page = context.new_page()
                    consecutive_failures = 0

            elif result == "WRONG":
                mark_failed(train_no, "parse_error")
                logger.warning(f"Worker {worker_id}: [FAIL] parse error on {train_no}")

            else:
                # None — unexpected exception
                consecutive_failures += 1
                mark_failed(train_no, "unexpected_exception")
                logger.error(f"Worker {worker_id}: None result on {train_no}")

        # Clean shutdown
        try:
            context.close()
            browser.close()
        except Exception:
            pass

    logger.info(f"Worker {worker_id}: finished")