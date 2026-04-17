from multiprocessing import Process,freeze_support
from web_scraping.main import run_worker

def split_list(lst, n):
    k = len(lst) // n
    return [lst[i*k:(i+1)*k] for i in range(n-1)] + [lst[(n-1)*k:]]

def main():
    

    NUM_WORKERS = 3
    chunks = split_list(train_numbers, NUM_WORKERS)

    processes = []

    for i in range(NUM_WORKERS):
        p = Process(target=run_worker, args=(chunks[i], i))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

if __name__ == "__main__":
    freeze_support()
    main()