import multiprocessing
import logging
import time

from queue_manager import init_queue, get_progress, get_failed_trains, get_true_total
from worker import run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(processName)-14s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scraper.log"),
    ]
)
logger = logging.getLogger(__name__)

NUM_WORKERS = 3


def _monitor(interval: int = 60):
    """Daemon process: prints queue progress every N seconds."""
    while True:
        time.sleep(interval)
        try:
            p = get_progress()
            total   = get_true_total()
            done    = p.get("done", 0)
            pending = p.get("pending", 0)
            active  = p.get("in_progress", 0)
            failed  = p.get("failed", 0)
            pct     = round(done / total * 100, 1) if total else 0
            logger.info(
                f"Progress: {done}/{total} ({pct}%) | "
                f"pending={pending} active={active} failed={failed}"
            )
        except Exception as e:
            logger.warning(f"Monitor error: {e}")


def main(train_numbers: list):
    # Step 1: populate queue (idempotent — safe to re-run after crash)
    init_queue(train_numbers)

    logger.info(f"Starting {NUM_WORKERS} workers for {len(train_numbers)} trains")

    # Step 2: start progress monitor as daemon
    monitor = multiprocessing.Process(target=_monitor, args=(60,), daemon=True)
    monitor.start()

    # Step 3: spawn workers with staggered starts
    # Stagger prevents all workers hitting Ixigo simultaneously on boot
    workers = []
    for i in range(NUM_WORKERS):
        p = multiprocessing.Process(
            target=run_worker,
            args=(i,),
            name=f"Worker-{i}"
        )
        p.start()
        workers.append(p)
        logger.info(f"Worker-{i} launched (PID {p.pid})")
        time.sleep(3)  # 3-second gap between each worker start

    # Step 4: wait for all workers to finish
    for p in workers:
        p.join()

    monitor.terminate()

    # Step 5: final summary
    progress = get_progress()
    failed   = get_failed_trains()
    logger.info(f"Scraping complete — {progress}")
    if failed:
        logger.warning(f"{len(failed)} trains failed after max attempts:")
        for train_no, error in failed[:20]:
            logger.warning(f"  {train_no}: {error}")
        if len(failed) > 20:
            logger.warning(f"  ... and {len(failed) - 20} more (check state.db)")
    

if __name__ == "__main__":

    # ── Your train list ──────────────────────────────────────────────────────
    
    with open(r"D:\\Shashwat\\DaisyChain\\scraper\\train_numbers.txt","r") as f:
        TRAIN_LIST = [line.strip() for line in f if line.strip()]

    main(TRAIN_LIST)